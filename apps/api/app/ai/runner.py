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

import copy
import uuid
from collections.abc import AsyncIterator
from typing import Any, cast

from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.agent import AgentContext, build_graph
from app.ai.cancel import CANCEL_TTL, cancel_key
from app.ai.checkpoint import get_checkpointer
from app.ai.llm import get_chat_model, provider_name, resolve_model_alias
from app.ai.policy import ToolPolicyEngine
from app.ai.tools import build_registry, get_tool_registry
from app.core.config import Settings
from app.core.exceptions import Conflict, NotFound
from app.core.kv import kv
from app.core.logging import get_logger
from app.db.base import utcnow
from app.models.ai import (
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

log = get_logger(__name__)


class AIThreadService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_threads(self, user: User, limit: int = 50) -> list[AIThread]:
        stmt = (
            select(AIThread)
            .where(AIThread.user_id == user.id, AIThread.archived_at.is_(None))
            .order_by(AIThread.updated_at.desc())
            .limit(limit)
        )
        return list(await self.db.scalars(stmt))

    async def get_thread(self, user: User, thread_id: uuid.UUID) -> AIThread:
        thread = await self.db.scalar(
            select(AIThread).where(AIThread.id == thread_id, AIThread.user_id == user.id)
        )
        if thread is None:
            raise NotFound("Conversation not found.")
        return thread

    async def create_thread(self, user: User, *, title: str, note_id: uuid.UUID | None) -> AIThread:
        thread = AIThread(
            tenant_id=user.tenant_id, user_id=user.id, title=title[:200], note_id=note_id
        )
        self.db.add(thread)
        await self.db.flush()
        return thread

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

    async def get_run(self, user: User, run_id: uuid.UUID) -> AIRun:
        run = await self.db.scalar(
            select(AIRun).where(AIRun.id == run_id, AIRun.user_id == user.id)
        )
        if run is None:
            raise NotFound("Run not found.")
        return run

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

    async def start(
        self, user: User, *, text: str, thread_id: uuid.UUID | None, note_id: uuid.UUID | None
    ) -> AsyncIterator[dict[str, Any]]:
        if thread_id is None:
            thread = await self.threads.create_thread(
                user, title=_title_from(text), note_id=note_id
            )
        else:
            thread = await self.threads.get_thread(user, thread_id)
        active = await self._active_run(thread)
        if active is not None:
            raise Conflict(
                "This conversation is still working on the previous request.",
                code="RUN_IN_PROGRESS",
            )
        now = utcnow()
        self.db.add(
            AIMessageRow(
                tenant_id=user.tenant_id,
                user_id=user.id,
                thread_id=thread.id,
                role=MessageRole.user,
                content=text,
                created_at=now,
            )
        )
        model_alias = resolve_model_alias(self.settings, _pref(user, "model"))
        run = AIRun(
            tenant_id=user.tenant_id,
            user_id=user.id,
            thread_id=thread.id,
            status=RunStatus.running,
            model=model_alias,
            provider=provider_name(self.settings),
            created_at=now,
            started_at=now,
        )
        self.db.add(run)
        thread.updated_at = now
        await self.db.commit()

        human = HumanMessage(content=text)
        if note_id is not None:
            human = HumanMessage(
                content=f"{text}\n\n(Context: the user is looking at note {note_id}.)"
            )
        async for event in self._drive(user, thread, run, {"messages": [human]}):
            yield event

    async def resume(
        self,
        user: User,
        *,
        run_id: uuid.UUID,
        approval_id: uuid.UUID,
        approved: list[str],
        reject_all: bool,
    ) -> AsyncIterator[dict[str, Any]]:
        run = await self.threads.get_run(user, run_id)
        if run.status != RunStatus.waiting_for_approval:
            raise Conflict("This run is not waiting for approval.", code="RUN_NOT_WAITING")
        approval = await self.db.scalar(
            select(AIApproval).where(AIApproval.id == approval_id, AIApproval.run_id == run.id)
        )
        if approval is None or approval.status != ApprovalStatus.pending:
            raise Conflict("This approval was already decided.", code="APPROVAL_DECIDED")

        allowed = set(approval.tool_call_ids)
        approved_ids = [] if reject_all else [cid for cid in approved if cid in allowed]
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
        await self.db.commit()
        thread = await self.threads.get_thread(user, run.thread_id)
        async for event in self._drive(
            user, thread, run, Command(resume={"approved": approved_ids})
        ):
            yield event

    async def cancel(self, user: User, run_id: uuid.UUID) -> AIRun:
        run = await self.threads.get_run(user, run_id)
        if run.status in (RunStatus.running, RunStatus.waiting_for_approval, RunStatus.queued):
            await kv.set(cancel_key(run.id), "1", CANCEL_TTL)
            if run.status == RunStatus.waiting_for_approval:
                # Nothing is executing; finalise immediately and expire the approval.
                for approval in run.approvals:
                    if approval.status == ApprovalStatus.pending:
                        approval.status = ApprovalStatus.expired
                        approval.decided_at = utcnow()
                run.status = RunStatus.cancelled
                run.completed_at = utcnow()
                await self.db.commit()
        return run

    # --- internals ------------------------------------------------------------------------------

    async def _active_run(self, thread: AIThread) -> AIRun | None:
        return await self.db.scalar(
            select(AIRun).where(
                AIRun.thread_id == thread.id,
                AIRun.status.in_([RunStatus.running, RunStatus.queued]),
            )
        )

    async def _drive(
        self, user: User, thread: AIThread, run: AIRun, graph_input: Any
    ) -> AsyncIterator[dict[str, Any]]:
        yield {
            "type": "run",
            "run_id": str(run.id),
            "thread_id": str(thread.id),
            "status": run.status.value,
        }
        model = get_chat_model(run.model, settings=self.settings, script_key=str(user.id))
        # Tool discovery is dynamic: built-ins plus whatever the user's connections offer today.
        from app.services.connection_service import ConnectionService

        provider_tools = await ConnectionService(self.db, self.settings).tools_for_user(user)
        registry = build_registry(provider_tools)
        ctx = AgentContext(
            user=user,
            db=self.db,
            run_id=run.id,
            model=model,
            registry=registry,
            policy=ToolPolicyEngine(registry),
            max_iterations=self.settings.ai_max_tool_iterations,
        )
        graph = build_graph(get_checkpointer())
        config = {"configurable": {"thread_id": str(thread.id)}}

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
                    if isinstance(data, dict) and data.get("type") in (
                        "step",
                        "plan",
                        "verification",
                    ):
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
            await self._finish(run, RunStatus.cancelled)
            yield {"type": "done", "run_id": str(run.id), "status": "cancelled", "usage": usage}
            return
        except Exception as exc:  # noqa: BLE001
            log.exception("ai_run_failed", extra={"run_id": str(run.id)})
            await self.db.rollback()
            await self._finish(run, RunStatus.failed, error=type(exc).__name__)
            yield {
                "type": "error",
                "code": "AI_RUN_FAILED",
                "message": "The assistant ran into a problem. Please try again.",
            }
            yield {"type": "done", "run_id": str(run.id), "status": "failed", "usage": usage}
            return

        if interrupted:
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
        thread.updated_at = utcnow()
        run.token_usage = {**run.token_usage, **usage} if usage else run.token_usage
        self._close_plan(run)
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
    return (first[:60] + "…") if len(first) > 60 else (first or "New conversation")


def _pref(user: User, key: str) -> Any:
    prefs = user.preferences if isinstance(user.preferences, dict) else {}
    ai = prefs.get("ai", {})
    return ai.get(key) if isinstance(ai, dict) else None
