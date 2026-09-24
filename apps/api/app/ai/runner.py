"""Runs the agent graph for a thread and turns graph events into persisted rows + SSE events.

Event types yielded (each a dict with a `type`):
  run                → {run_id, thread_id, status}
  token              → {text}                       streamed assistant text
  step               → {call_id, tool, label, status, result_preview?}
  plan               → {goal, steps[{title, kind, tools, status}]}  declared by the agent
  verification       → {call_id, status, detail}   read-back after an approved write
  approval_required  → {approval_id, proposals[]}   run paused; client must call /ai/approve
  message            → {message_id, content, sources[]}  final assistant message
  done               → {run_id, status, usage}
  error              → {code, message}
"""

from __future__ import annotations

import asyncio
import contextlib
import copy
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, cast

from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.agent import AgentContext, build_graph
from app.ai.byo import BYOModel
from app.ai.cancel import CANCEL_TTL, cancel_key
from app.ai.checkpoint import get_checkpointer
from app.ai.llm import get_chat_model, provider_name, resolve_model_alias
from app.ai.pacing import is_transient, slot_key
from app.ai.policy import ToolPolicyEngine
from app.ai.streams import RunChannel, hub, is_alive
from app.ai.tools import build_registry, get_tool_registry
from app.core import metrics
from app.core.config import Settings
from app.core.exceptions import Conflict, NotFound
from app.core.kv import kv
from app.core.logging import get_logger
from app.db.base import utcnow
from app.db.session import get_session_factory
from app.models.ai import (
    OPEN_RUN_STATUSES,
    AIApproval,
    AIRun,
    AIThread,
    AIToolCall,
    ApprovalStatus,
    MessageRole,
    RiskLevel,
    RunStatus,
    ToolCallStatus,
)
from app.models.ai import (
    AIMessage as AIMessageRow,
)
from app.models.user import User
from app.services.ai_settings_service import AISettingsService

log = get_logger(__name__)


DEFAULT_TITLE = "New conversation"


@dataclass
class ThreadSummary:
    """A conversation as the list shows it: the row plus its latest message and open run."""

    thread: AIThread
    last_message: AIMessageRow | None
    open_run: AIRun | None


@dataclass
class PreparedRun:
    """A run that is committed and ready to execute in the background."""

    run: AIRun
    thread: AIThread
    graph_input: Any
    user_message_id: uuid.UUID | None = None


class AIThreadService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_threads(
        self, user: User, *, archived: bool = False, limit: int = 100
    ) -> list[ThreadSummary]:
        archived_filter = (
            AIThread.archived_at.is_not(None) if archived else AIThread.archived_at.is_(None)
        )
        threads = list(
            await self.db.scalars(
                select(AIThread)
                .where(AIThread.user_id == user.id, archived_filter)
                .order_by(AIThread.last_activity_at.desc(), AIThread.id)
                .limit(limit)
            )
        )
        ids = [t.id for t in threads]
        if not ids:
            return []
        ranked = (
            select(
                AIMessageRow.id,
                func.row_number()
                .over(
                    partition_by=AIMessageRow.thread_id,
                    order_by=(AIMessageRow.created_at.desc(), AIMessageRow.id.desc()),
                )
                .label("rank"),
            )
            .where(
                AIMessageRow.thread_id.in_(ids),
                AIMessageRow.user_id == user.id,
                AIMessageRow.role.in_([MessageRole.user, MessageRole.assistant]),
            )
            .subquery()
        )
        latest = {
            m.thread_id: m
            for m in await self.db.scalars(
                select(AIMessageRow)
                .join(ranked, ranked.c.id == AIMessageRow.id)
                .where(ranked.c.rank == 1)
            )
        }
        open_runs = {
            r.thread_id: r
            for r in await self.db.scalars(
                select(AIRun).where(
                    AIRun.thread_id.in_(ids),
                    AIRun.user_id == user.id,
                    AIRun.status.in_(OPEN_RUN_STATUSES),
                )
            )
        }
        return [ThreadSummary(t, latest.get(t.id), open_runs.get(t.id)) for t in threads]

    async def get_thread(
        self, user: User, thread_id: uuid.UUID, *, for_update: bool = False
    ) -> AIThread:
        stmt = select(AIThread).where(AIThread.id == thread_id, AIThread.user_id == user.id)
        if for_update:
            # Serialises sends to one conversation (Postgres row lock until commit); other
            # conversations are unaffected. SQLite ignores it; the unique index still holds.
            stmt = stmt.with_for_update()
        thread = await self.db.scalar(stmt)
        if thread is None:
            raise NotFound("Conversation not found.")
        return thread

    async def create_thread(
        self, user: User, *, title: str | None = None, note_id: uuid.UUID | None = None
    ) -> AIThread:
        now = utcnow()
        thread = AIThread(
            tenant_id=user.tenant_id,
            user_id=user.id,
            title=(title or DEFAULT_TITLE).strip()[:200] or DEFAULT_TITLE,
            note_id=note_id,
            last_activity_at=now,
        )
        self.db.add(thread)
        await self.db.flush()
        return thread

    async def update_thread(
        self,
        user: User,
        thread_id: uuid.UUID,
        *,
        title: str | None = None,
        archived: bool | None = None,
    ) -> AIThread:
        thread = await self.get_thread(user, thread_id)
        if title is not None:
            thread.title = title.strip()[:200] or DEFAULT_TITLE
        if archived is not None:
            thread.archived_at = (thread.archived_at or utcnow()) if archived else None
        await self.db.commit()
        return thread

    async def open_run(self, user: User, thread_id: uuid.UUID) -> AIRun | None:
        return await self.db.scalar(
            select(AIRun).where(
                AIRun.thread_id == thread_id,
                AIRun.user_id == user.id,
                AIRun.status.in_(OPEN_RUN_STATUSES),
            )
        )

    async def last_run(self, user: User, thread_id: uuid.UUID) -> AIRun | None:
        return await self.db.scalar(
            select(AIRun)
            .where(AIRun.thread_id == thread_id, AIRun.user_id == user.id)
            .order_by(AIRun.created_at.desc())
            .limit(1)
        )

    async def settle_orphan(self, run: AIRun) -> bool:
        """Close a run that claims to be executing but no process is running it (a crash or a
        deploy mid-run). True when it was closed. Runs waiting for approval are not orphans."""
        if run.status not in (RunStatus.queued, RunStatus.running) or await is_alive(run.id):
            return False
        run.status = RunStatus.failed
        run.error = "interrupted"
        run.completed_at = utcnow()
        await self.db.commit()
        return True

    async def list_messages(self, user: User, thread_id: uuid.UUID) -> list[AIMessageRow]:
        stmt = (
            select(AIMessageRow)
            .where(AIMessageRow.thread_id == thread_id, AIMessageRow.user_id == user.id)
            .order_by(AIMessageRow.created_at)
        )
        return list(await self.db.scalars(stmt))

    async def delete_thread(self, user: User, thread_id: uuid.UUID) -> None:
        thread = await self.get_thread(user, thread_id)
        await self.db.delete(thread)
        await self.db.commit()
        # The agent's checkpointed context for this conversation goes with it.
        with contextlib.suppress(Exception):
            await get_checkpointer().adelete_thread(str(thread_id))

    async def get_run(self, user: User, run_id: uuid.UUID) -> AIRun:
        run = await self.db.scalar(
            select(AIRun).where(AIRun.id == run_id, AIRun.user_id == user.id)
        )
        if run is None:
            raise NotFound("Run not found.")
        return run

    async def run_message(self, user: User, run_id: uuid.UUID) -> AIMessageRow | None:
        return await self.db.scalar(
            select(AIMessageRow).where(
                AIMessageRow.run_id == run_id,
                AIMessageRow.user_id == user.id,
                AIMessageRow.role == MessageRole.assistant,
            )
        )

    async def list_runs(self, user: User, limit: int = 50) -> list[AIRun]:
        stmt = (
            select(AIRun)
            .where(AIRun.user_id == user.id)
            .order_by(AIRun.created_at.desc())
            .limit(limit)
        )
        return list(await self.db.scalars(stmt))

    async def get_pending_approval(self, user: User, run: AIRun) -> AIApproval | None:
        return await self.db.scalar(
            select(AIApproval).where(
                AIApproval.run_id == run.id,
                AIApproval.user_id == user.id,
                AIApproval.status == ApprovalStatus.pending,
            )
        )


class AIRunner:
    def __init__(self, db: AsyncSession, settings: Settings) -> None:
        self.db = db
        self.settings = settings
        self.threads = AIThreadService(db)
        self.registry = get_tool_registry()
        self.policy = ToolPolicyEngine(self.registry)

    # --- public entry points --------------------------------------------------------------------
    #
    # `prepare_*` validate and commit everything a run needs, inside the request, so conflicts
    # surface as ordinary HTTP errors. `execute_run` (below) then drives the agent in the
    # background, detached from the request.

    async def prepare_chat(
        self,
        user: User,
        *,
        text: str | None,
        thread_id: uuid.UUID | None,
        note_id: uuid.UUID | None,
        retry: bool = False,
    ) -> PreparedRun:
        if thread_id is None:
            if retry or not text:
                raise Conflict("Nothing to retry in a new conversation.", code="NOTHING_TO_RETRY")
            thread = await self.threads.create_thread(
                user, title=_title_from(text), note_id=note_id
            )
        else:
            # Let a run that is being stopped finish first (outside the lock: it may need to
            # write to this thread on its way out).
            existing = await self.threads.open_run(user, thread_id)
            if existing is not None and await kv.get(cancel_key(existing.id)):
                await hub.wait(existing.id, STOP_GRACE_SECONDS)
            thread = await self.threads.get_thread(user, thread_id, for_update=True)
            await self._clear_open_run(user, thread)

        now = utcnow()
        human_text: str
        graph_input: Any
        user_message_id: uuid.UUID | None = None
        if retry:
            last = await self.db.scalar(
                select(AIMessageRow)
                .where(
                    AIMessageRow.thread_id == thread.id,
                    AIMessageRow.user_id == user.id,
                    AIMessageRow.role.in_([MessageRole.user, MessageRole.assistant]),
                )
                .order_by(AIMessageRow.created_at.desc(), AIMessageRow.id.desc())
                .limit(1)
            )
            if last is None or last.role != MessageRole.user:
                raise Conflict("The last request already has an answer.", code="NOTHING_TO_RETRY")
            human_text = last.content
            graph_input = await self._retry_input(thread, human_text, note_id)
        else:
            assert text is not None
            human_text = text
            if thread.title == DEFAULT_TITLE and not await self._has_messages(thread):
                thread.title = _title_from(text)
            message = AIMessageRow(
                tenant_id=user.tenant_id,
                user_id=user.id,
                thread_id=thread.id,
                role=MessageRole.user,
                content=text,
                created_at=now,
            )
            self.db.add(message)
            await self.db.flush()
            user_message_id = message.id
            graph_input = {"messages": [_human(human_text, note_id)]}

        byo = await AISettingsService(self.db, self.settings).resolve(user)
        model_alias = byo.model if byo else resolve_model_alias(self.settings, _pref(user, "model"))
        run = AIRun(
            tenant_id=user.tenant_id,
            user_id=user.id,
            thread_id=thread.id,
            status=RunStatus.running,
            model=model_alias,
            provider=byo.label if byo else provider_name(self.settings),
            created_at=now,
            started_at=now,
        )
        self.db.add(run)
        thread.last_activity_at = now
        try:
            await self.db.commit()
        except IntegrityError:
            # Another request won the race for this conversation (see uq_ai_runs_thread_open).
            await self.db.rollback()
            raise _busy() from None
        return PreparedRun(
            run=run, thread=thread, graph_input=graph_input, user_message_id=user_message_id
        )

    async def prepare_resume(
        self,
        user: User,
        *,
        run_id: uuid.UUID,
        approval_id: uuid.UUID,
        approved: list[str],
        reject_all: bool,
    ) -> PreparedRun:
        run = await self.threads.get_run(user, run_id)
        # Lock the conversation like a send does, so a decision and a new message cannot race.
        thread = await self.threads.get_thread(user, run.thread_id, for_update=True)
        await self.db.refresh(run)
        if run.status != RunStatus.waiting_for_approval:
            raise Conflict("This run is not waiting for approval.", code="RUN_NOT_WAITING")
        approval = await self.db.scalar(
            select(AIApproval).where(AIApproval.id == approval_id, AIApproval.run_id == run.id)
        )
        if approval is None or approval.status != ApprovalStatus.pending:
            raise Conflict("This approval was already decided.", code="APPROVAL_DECIDED")

        allowed = set(approval.tool_call_ids)
        approved_ids = [] if reject_all else [cid for cid in approved if cid in allowed]
        metrics.ai_approvals.labels("approved").inc(len(approved_ids))
        metrics.ai_approvals.labels("rejected").inc(len(allowed) - len(approved_ids))
        approval.status = ApprovalStatus.approved if approved_ids else ApprovalStatus.rejected
        approval.decision = {
            "approved": approved_ids,
            "rejected": sorted(allowed - set(approved_ids)),
        }
        approval.decided_at = utcnow()
        for tc in run.tool_calls:
            if tc.call_id in allowed and tc.status == ToolCallStatus.proposed:
                tc.status = (
                    ToolCallStatus.approved
                    if tc.call_id in approved_ids
                    else ToolCallStatus.rejected
                )
        run.status = RunStatus.running
        thread.last_activity_at = utcnow()
        await self.db.commit()
        return PreparedRun(
            run=run, thread=thread, graph_input=Command(resume={"approved": approved_ids})
        )

    async def cancel(self, user: User, run_id: uuid.UUID) -> AIRun:
        """Stop one run. Only this run's flag is set; other conversations are untouched."""
        run = await self.threads.get_run(user, run_id)
        if run.status in OPEN_RUN_STATUSES:
            await kv.set(cancel_key(run.id), "1", CANCEL_TTL)
            if run.status == RunStatus.waiting_for_approval or not await is_alive(run.id):
                # Nothing is executing (paused for approval, or orphaned): finalise now.
                _expire_approvals(run)
                run.status = RunStatus.cancelled
                run.completed_at = utcnow()
                await self.db.commit()
        return run

    # --- internals ------------------------------------------------------------------------------

    async def _clear_open_run(self, user: User, thread: AIThread) -> None:
        """Make way for a new run in `thread` (whose row the caller has locked)."""
        run = await self.threads.open_run(user, thread.id)
        if run is None:
            return
        await self.db.refresh(run)
        if run.status == RunStatus.waiting_for_approval:
            # The user moved on without deciding: the proposals lapse (nothing was executed).
            _expire_approvals(run)
            run.status = RunStatus.cancelled
            run.error = "superseded"
            run.completed_at = utcnow()
            await self.db.flush()
            return
        if run.status not in OPEN_RUN_STATUSES:
            return
        if not await is_alive(run.id):
            run.status = RunStatus.failed
            run.error = "interrupted"
            run.completed_at = utcnow()
            await self.db.flush()
            return
        raise _busy()

    async def _has_messages(self, thread: AIThread) -> bool:
        first = await self.db.scalar(
            select(AIMessageRow.id).where(AIMessageRow.thread_id == thread.id).limit(1)
        )
        return first is not None

    async def _retry_input(self, thread: AIThread, text: str, note_id: uuid.UUID | None) -> Any:
        """Re-answer the last user message. If the checkpoint stopped right after that message
        (the model call failed or was stopped), continue from it; otherwise the failure came
        before the message reached the graph, so send it again."""
        graph = build_graph(get_checkpointer())
        config = cast(RunnableConfig, {"configurable": {"thread_id": str(thread.id)}})
        snapshot = await graph.aget_state(config)
        messages = (snapshot.values or {}).get("messages") or []
        if messages and isinstance(messages[-1], HumanMessage) and snapshot.next:
            return None
        return {"messages": [_human(text, note_id)]}

    async def _drive(
        self,
        user: User,
        thread: AIThread,
        run: AIRun,
        graph_input: Any,
        intro: dict[str, Any] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        yield {
            "type": "run",
            "run_id": str(run.id),
            "thread_id": str(thread.id),
            "status": run.status.value,
            **(intro or {}),
        }
        byo = await AISettingsService(self.db, self.settings).resolve(user)
        model = get_chat_model(run.model, settings=self.settings, script_key=str(user.id), byo=byo)
        # Tool discovery is dynamic: built-ins plus whatever the user's connections offer today.
        from app.services.connection_service import ConnectionService

        provider_tools = await ConnectionService(self.db, self.settings).tools_for_user(user)
        registry = build_registry(provider_tools)
        budget, budget_width = slot_key(byo)
        ctx = AgentContext(
            user=user,
            db=self.db,
            run_id=run.id,
            model=model,
            registry=registry,
            policy=ToolPolicyEngine(registry),
            max_iterations=self.settings.ai_max_tool_iterations,
            slot_key=budget,
            slot_limit=budget_width,
        )
        graph = build_graph(get_checkpointer())
        config = {"configurable": {"thread_id": str(thread.id)}}

        drive_timer = metrics.Timer().__enter__()
        model_label = run.model or "unknown"
        text_parts: list[str] = []
        final_message: AIMessage | None = None
        sources: list[dict[str, Any]] = []
        usage: dict[str, int] = {}
        interrupted = False
        pending_steps: list[dict[str, Any]] = []

        try:
            stream = graph.astream(
                graph_input,
                config=cast(RunnableConfig, config),
                context=ctx,
                stream_mode=["messages", "updates", "custom"],
                # An approval pause must survive process restarts: persist every step before
                # moving on rather than in the background.
                durability="sync",
            )
            async for part in stream:
                mode, data = cast(tuple[str, Any], part)
                may_stop = mode == "updates"
                if mode == "messages":
                    chunk, meta = cast(tuple[Any, dict[str, Any]], data)
                    if isinstance(chunk, AIMessageChunk) and meta.get("langgraph_node") == "agent":
                        may_stop = True  # between streamed tokens: nothing to record yet
                        text = _text_of(chunk.content)
                        if text:
                            text_parts.append(text)
                            yield {"type": "token", "text": text}
                elif mode == "custom":
                    # A node is still executing here, so never touch the DB session: buffer.
                    if isinstance(data, dict) and data.get("type") == "notice":
                        yield data  # transient status ("retrying in 12s…"), not recorded
                    elif isinstance(data, dict) and data.get("type") in (
                        "step",
                        "plan",
                        "verification",
                    ):
                        _observe_event(data)
                        pending_steps.append(data)
                        yield data
                elif mode == "updates":
                    # Node finished: the session is ours again.
                    if pending_steps:
                        self._record_steps(run, pending_steps)
                        pending_steps = []
                    for node, update in (data or {}).items():
                        if node == "__interrupt__":
                            interrupts = update if isinstance(update, list | tuple) else [update]
                            payload = interrupts[0].value if interrupts else {}
                            approval = await self._persist_proposals(user, run, payload)
                            interrupted = True
                            yield {
                                "type": "approval_required",
                                "approval_id": str(approval.id),
                                "run_id": str(run.id),
                                "proposals": payload.get("proposals", []),
                            }
                        elif node == "agent" and isinstance(update, dict):
                            for m in update.get("messages", []):
                                if isinstance(m, AIMessage):
                                    final_message = m
                                    _accumulate_usage(usage, m)
                        elif node == "tools" and isinstance(update, dict):
                            sources.extend(update.get("sources") or [])
                            run.sources = _merge_sources(run.sources, update.get("sources") or [])
                            await self._mark_executed(run, update)
                if interrupted:
                    break
                # Checked at node boundaries (and between streamed tokens), after bookkeeping,
                # so a node that already ran is recorded (executed tool calls, audit) before the
                # run stops and the next node never starts. Custom/tool-message events arrive
                # while a node is still executing, so they are not a safe place to stop.
                if may_stop and await kv.get(cancel_key(run.id)):
                    raise _Cancelled()
        except _Cancelled:
            _observe_drive(model_label, "cancelled", drive_timer, usage)
            await self._finish(run, RunStatus.cancelled)
            yield {"type": "done", "run_id": str(run.id), "status": "cancelled", "usage": usage}
            return
        except Exception as exc:  # noqa: BLE001
            run_id = run.id  # read before the rollback expires the row
            await self.db.rollback()
            if await kv.get(cancel_key(run_id)):
                # Stopped while waiting out a provider error: that is a cancel, not a failure.
                _observe_drive(model_label, "cancelled", drive_timer, usage)
                await self._finish(run, RunStatus.cancelled)
                yield {"type": "done", "run_id": str(run_id), "status": "cancelled", "usage": usage}
                return
            log.exception("ai_run_failed", extra={"run_id": str(run_id)})
            _observe_drive(model_label, "failed", drive_timer, usage)
            failure = failure_message(exc, byo)
            # The readable reason is kept on the run so a reloaded page can still show it.
            await self._finish(run, RunStatus.failed, error=failure)
            yield {"type": "error", "code": "AI_RUN_FAILED", "message": failure}
            yield {"type": "done", "run_id": str(run_id), "status": "failed", "usage": usage}
            return

        if interrupted:
            _observe_drive(model_label, "waiting_for_approval", drive_timer, usage)
            run.status = RunStatus.waiting_for_approval
            run.token_usage = {**run.token_usage, **usage} if usage else run.token_usage
            if run.plan:
                _mark_plan(run, kind="propose", status="waiting")
            await self.db.commit()
            yield {
                "type": "done",
                "run_id": str(run.id),
                "status": run.status.value,
                "usage": usage,
            }
            return

        content = (
            final_message.text if final_message and final_message.text else "".join(text_parts)
        ).strip()
        message = AIMessageRow(
            tenant_id=user.tenant_id,
            user_id=user.id,
            thread_id=thread.id,
            run_id=run.id,
            role=MessageRole.assistant,
            content=content,
            sources=run.sources or None,
            created_at=utcnow(),
        )
        self.db.add(message)
        thread.last_activity_at = utcnow()
        run.token_usage = {**run.token_usage, **usage} if usage else run.token_usage
        self._close_plan(run)
        _observe_drive(model_label, "completed", drive_timer, usage)
        await self._finish(run, RunStatus.completed)
        yield {
            "type": "message",
            "message_id": str(message.id),
            "content": content,
            "sources": run.sources,
        }
        yield {
            "type": "done",
            "run_id": str(run.id),
            "status": "completed",
            "usage": run.token_usage,
        }

    async def _persist_proposals(
        self, user: User, run: AIRun, payload: dict[str, Any]
    ) -> AIApproval:
        proposals = payload.get("proposals", [])
        now = utcnow()
        ids: list[str] = []
        for p in proposals:
            ids.append(p["call_id"])
            self.db.add(
                AIToolCall(
                    tenant_id=user.tenant_id,
                    user_id=user.id,
                    run_id=run.id,
                    call_id=p["call_id"],
                    tool_name=p["tool_name"],
                    provider=p.get("provider", "notely"),
                    risk_level=RiskLevel(p["risk"]),
                    arguments=p.get("arguments", {}),
                    status=ToolCallStatus.proposed,
                    created_at=now,
                )
            )
        approval = AIApproval(
            tenant_id=user.tenant_id,
            user_id=user.id,
            run_id=run.id,
            tool_call_ids=ids,
            created_at=now,
        )
        self.db.add(approval)
        run.steps = [*run.steps, {"type": "approval", "count": len(ids), "at": now.isoformat()}]
        await self.db.commit()
        await self.db.refresh(run, attribute_names=["tool_calls", "approvals"])
        return approval

    def _record_steps(self, run: AIRun, events: list[dict[str, Any]]) -> None:
        """Fold buffered step/plan/verification events into the run (committed with the next
        node update)."""
        # Deep copies throughout: SQLAlchemy only emits an UPDATE for a JSON column when the new
        # value compares unequal to the loaded one, so in-place mutation would be lost.
        recorded = copy.deepcopy(list(run.steps))
        for event in events:
            kind = event.get("type")
            if kind == "plan":
                run.plan = {"goal": event.get("goal", ""), "steps": list(event.get("steps", []))}
                continue
            if kind == "verification":
                for s in recorded:
                    if s.get("call_id") == event.get("call_id"):
                        s["verification"] = {
                            "status": event.get("status"),
                            "detail": event.get("detail"),
                        }
                if run.plan:
                    _mark_plan(run, kind="verify", status="done")
                continue
            if event.get("status") == "running":
                recorded.append(
                    {k: event[k] for k in ("call_id", "tool", "label", "status") if k in event}
                )
                if run.plan:
                    _mark_plan(run, tool=str(event.get("tool")), status="active")
            else:
                for s in recorded:
                    if s.get("call_id") == event.get("call_id"):
                        s["status"] = event.get("status")
                if run.plan and event.get("status") == "completed":
                    _mark_plan(run, tool=str(event.get("tool")), status="done")
        run.steps = recorded

    def _close_plan(self, run: AIRun) -> None:
        """Plan progress is derived from execution metadata, never from model claims: a step is
        done when one of its tools completed; whatever is left when the run finishes is marked
        done for the `answer` step and skipped otherwise."""
        if not run.plan:
            return
        steps = [dict(step) for step in run.plan.get("steps", [])]
        for step in steps:
            if step.get("status") != "done":
                step["status"] = "done" if step.get("kind") == "answer" else "skipped"
        run.plan = {**run.plan, "steps": steps}

    async def _mark_executed(self, run: AIRun, update: dict[str, Any]) -> None:
        """Reflect tool outcomes on persisted tool-call rows (approved ones only exist as rows)."""
        await self.db.refresh(run, attribute_names=["tool_calls"])
        by_call = {tc.call_id: tc for tc in run.tool_calls}
        for m in update.get("messages", []):
            tc = by_call.get(getattr(m, "tool_call_id", ""))
            if tc is None or tc.status not in (ToolCallStatus.approved,):
                continue
            try:
                import json

                body = json.loads(m.content) if isinstance(m.content, str) else {}
            except ValueError:
                body = {}
            if body.get("cancelled"):
                tc.error = "Stopped before execution"  # stays `approved`: it never ran
                continue
            tc.executed_at = utcnow()
            tc.status = ToolCallStatus.failed if "error" in body else ToolCallStatus.executed
            tc.result = {"preview": str(body)[:500]}
            tc.error = body.get("error")
            if isinstance(body.get("verification"), dict):
                tc.verification = body["verification"]
        await self.db.commit()

    async def _finish(self, run: AIRun, status: RunStatus, *, error: str | None = None) -> None:
        run.status = status
        run.error = error
        run.completed_at = utcnow()
        await self.db.commit()


class _Cancelled(Exception):
    pass


STOP_GRACE_SECONDS = 5.0


def failure_message(exc: BaseException, byo: BYOModel | None) -> str:
    """Why a run failed, for the user: categorised, never raw vendor text or the key."""
    if byo is not None:
        from app.ai.byo import classify_error

        reason = classify_error(exc) if isinstance(exc, Exception) else ""
        if is_transient(exc):
            return (
                f"Your own model ({byo.model}) is rate-limiting or overloaded and kept refusing "
                "after several retries. Wait a minute and retry, or use a key with a higher "
                "quota (Settings → AI)."
            )
        return f"Your own model ({byo.model}) failed: {reason} Check Settings → AI."
    if is_transient(exc):
        return "The AI provider is busy right now. Wait a minute and retry."
    return "The assistant ran into a problem. Please try again."


def _busy() -> Conflict:
    return Conflict(
        "This conversation is still working on the previous request.", code="RUN_IN_PROGRESS"
    )


def _expire_approvals(run: AIRun) -> None:
    for approval in run.approvals:
        if approval.status == ApprovalStatus.pending:
            approval.status = ApprovalStatus.expired
            approval.decided_at = utcnow()


def _human(text: str, note_id: uuid.UUID | None) -> HumanMessage:
    if note_id is None:
        return HumanMessage(content=text)
    return HumanMessage(content=f"{text}\n\n(Context: the user is looking at note {note_id}.)")


def launch_run(prepared: PreparedRun, user: User, settings: Settings) -> RunChannel:
    """Execute a prepared run in the background; returns the channel to subscribe to."""
    run_id, thread_id, user_id = prepared.run.id, prepared.thread.id, user.id
    intro = {"user_message_id": str(prepared.user_message_id)} if prepared.user_message_id else {}

    async def work(channel: RunChannel) -> None:
        await execute_run(
            channel,
            run_id=run_id,
            user_id=user_id,
            graph_input=prepared.graph_input,
            settings=settings,
            intro=intro,
        )

    return hub.launch(run_id, thread_id, user_id, work)


async def execute_run(
    channel: RunChannel,
    *,
    run_id: uuid.UUID,
    user_id: uuid.UUID,
    graph_input: Any,
    settings: Settings,
    intro: dict[str, Any] | None = None,
) -> None:
    """Drive one run with its own DB session and publish every event to its channel."""
    async with get_session_factory()() as db:
        try:
            user = await db.get(User, user_id)
            run = await db.get(AIRun, run_id)
            thread = await db.get(AIThread, run.thread_id) if run else None
            if user is None or run is None or thread is None:
                await channel.publish(
                    {"type": "error", "code": "NOT_FOUND", "message": "This conversation is gone."}
                )
                return
            runner = AIRunner(db, settings)
            async for event in runner._drive(user, thread, run, graph_input, intro):
                await channel.publish(event)
        except asyncio.CancelledError:
            # Process shutdown: record the run as interrupted so it does not look alive.
            with contextlib.suppress(Exception):
                await db.rollback()
                run = await db.get(AIRun, run_id)
                if run is not None and run.status in OPEN_RUN_STATUSES:
                    run.status = RunStatus.failed
                    run.error = "interrupted"
                    run.completed_at = utcnow()
                    await db.commit()
            raise
        except Exception:  # noqa: BLE001 - _drive handles run failures; this is a last resort
            log.exception("ai_run_execute_failed", extra={"run_id": str(run_id)})
            with contextlib.suppress(Exception):
                await db.rollback()
                run = await db.get(AIRun, run_id)
                if run is not None and run.status in OPEN_RUN_STATUSES:
                    run.status = RunStatus.failed
                    run.error = "internal"
                    run.completed_at = utcnow()
                    await db.commit()
            await channel.publish(
                {
                    "type": "error",
                    "code": "AI_RUN_FAILED",
                    "message": "The assistant ran into a problem. Please try again.",
                }
            )
            await channel.publish({"type": "done", "status": "failed", "usage": {}})


def _mark_plan(
    run: AIRun, *, status: str, tool: str | None = None, kind: str | None = None
) -> None:
    """Mark the first pending plan step that matches a completed tool (or a step kind)."""
    plan = run.plan
    if not plan:
        return
    steps = copy.deepcopy(list(plan.get("steps", [])))
    for step in steps:
        if step.get("status") in ("done", "skipped"):
            continue
        matches = (tool is not None and tool in (step.get("tools") or [])) or (
            kind is not None and step.get("kind") == kind
        )
        if matches:
            step["status"] = status
            # Everything before a completed step is implicitly done (the model may skip tools).
            for earlier in steps:
                if earlier is step:
                    break
                if earlier.get("status") in ("pending", "active", "waiting"):
                    earlier["status"] = "done"
            break
    run.plan = {**plan, "steps": steps}


def _observe_drive(model: str, status: str, timer: metrics.Timer, usage: dict[str, int]) -> None:
    timer.__exit__(None, None, None)
    metrics.ai_runs.labels(model, status).inc()
    metrics.ai_run_latency.labels(model).observe(timer.seconds)
    for direction, key in (("input", "input_tokens"), ("output", "output_tokens")):
        if usage.get(key):
            metrics.ai_tokens.labels(model, direction).inc(usage[key])


def _observe_event(event: dict[str, Any]) -> None:
    kind = event.get("type")
    if kind == "step" and event.get("status") in ("completed", "failed"):
        tool = str(event.get("tool", ""))
        provider = tool.split("__", 1)[0] if "__" in tool else "notely"
        metrics.ai_tool_calls.labels(provider, tool, str(event["status"])).inc()
    elif kind == "verification":
        tool = str(event.get("tool", ""))
        metrics.ai_verifications.labels(
            str(event.get("provider", "notely")), str(event.get("status"))
        ).inc()


def _merge_sources(
    existing: list[dict[str, Any]], new: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    seen = {(s.get("provider"), s.get("object_id")) for s in existing}
    merged = copy.deepcopy(list(existing))
    for src in new:
        key = (src.get("provider"), src.get("object_id"))
        if key not in seen:
            seen.add(key)
            merged.append(dict(src))
    return merged


def _text_of(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in content
            if part
        )
    return ""


def _accumulate_usage(usage: dict[str, int], message: AIMessage) -> None:
    meta = getattr(message, "usage_metadata", None) or {}
    for key in ("input_tokens", "output_tokens", "total_tokens"):
        if isinstance(meta.get(key), int):
            usage[key] = usage.get(key, 0) + int(meta[key])


def _title_from(text: str) -> str:
    first = " ".join(text.strip().split())
    return (first[:60] + "…") if len(first) > 60 else (first or DEFAULT_TITLE)


def _pref(user: User, key: str) -> Any:
    prefs = user.preferences if isinstance(user.preferences, dict) else {}
    ai = prefs.get("ai", {})
    return ai.get(key) if isinstance(ai, dict) else None
