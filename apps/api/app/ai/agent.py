"""The Notely agent graph.

    agent ──(tool calls?)──► tools ──► agent ──► ... ──► END
                             │
                             └─ interrupt() when any call needs human approval

The PRD pipeline (discover → plan → read → propose → approve → execute → verify) maps onto
this loop: tool discovery is the per-run registry, planning is the `plan_steps` tool, proposals
are the interrupt payload, and verification is the read-back the framework runs after every
approved write (`ToolSpec.verify`).

Nodes receive a `Runtime[AgentContext]`; the context carries the DB session, user and run id
and is *not* checkpointed. State (messages, sources) is checkpointed per thread so a run can
pause for approval and resume later.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Annotated, Any, TypedDict

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, SystemMessage, ToolMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph, add_messages
from langgraph.graph.state import CompiledStateGraph
from langgraph.runtime import Runtime
from langgraph.types import interrupt
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.cancel import cancel_key
from app.ai.policy import ToolPolicyEngine, ValidatedCall
from app.ai.prompts import assistant_system_prompt
from app.ai.tools.base import ToolContext, ToolRegistry, Verification, args_to_dict
from app.core.config import get_settings
from app.core.exceptions import APIError
from app.core.kv import kv
from app.core.logging import get_logger
from app.db.base import utcnow
from app.integrations.base.errors import ProviderError, ProviderErrorKind
from app.models.ai import RiskLevel
from app.models.user import User
from app.services.audit_service import AuditService

log = get_logger(__name__)


def _merge_sources(left: list[dict[str, Any]], right: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = {(s.get("provider"), s.get("object_id")) for s in left}
    merged = list(left)
    for s in right:
        key = (s.get("provider"), s.get("object_id"))
        if key not in seen:
            seen.add(key)
            merged.append(s)
    return merged


class AgentState(TypedDict, total=False):
    messages: Annotated[list[BaseMessage], add_messages]
    sources: Annotated[list[dict[str, Any]], _merge_sources]
    iterations: int


@dataclass
class AgentContext:
    user: User
    db: AsyncSession
    run_id: uuid.UUID
    model: BaseChatModel
    registry: ToolRegistry
    policy: ToolPolicyEngine
    max_iterations: int = 8


@dataclass(frozen=True)
class Proposal:
    """What the user is asked to approve. Serialisable; lives in the interrupt payload."""

    call_id: str
    tool_name: str
    provider: str
    risk: str
    summary: str
    arguments: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "call_id": self.call_id,
            "tool_name": self.tool_name,
            "provider": self.provider,
            "risk": self.risk,
            "summary": self.summary,
            "arguments": self.arguments,
        }


async def agent_node(state: AgentState, runtime: Runtime[AgentContext]) -> dict[str, Any]:
    ctx = runtime.context
    iterations = state.get("iterations", 0)
    if iterations >= ctx.max_iterations:
        return {
            "messages": [
                AIMessage(
                    content="I've hit the step limit for this request. Try narrowing it down."
                )
            ],
            "iterations": iterations,
        }
    model = ctx.model.bind_tools(ctx.registry.openai_schemas())
    system = SystemMessage(content=assistant_system_prompt(ctx.user.display_name))
    response = await model.ainvoke([system, *state.get("messages", [])])
    return {"messages": [response], "iterations": iterations + 1}


def route_after_agent(state: AgentState) -> str:
    last = state["messages"][-1] if state.get("messages") else None
    if isinstance(last, AIMessage) and last.tool_calls:
        return "tools"
    return END


async def tools_node(state: AgentState, runtime: Runtime[AgentContext]) -> dict[str, Any]:
    ctx = runtime.context
    writer = get_stream_writer()
    last = state["messages"][-1]
    assert isinstance(last, AIMessage)

    accepted, rejected = ctx.policy.validate_calls(ctx.user, [dict(tc) for tc in last.tool_calls])
    outputs: list[BaseMessage] = [
        ToolMessage(
            content=json.dumps({"error": r.reason}), tool_call_id=r.call_id, name=r.tool_name
        )
        for r in rejected
    ]

    needs_approval = [c for c in accepted if c.decision.requires_confirmation]
    approved_ids: set[str] = {c.call_id for c in accepted if not c.decision.requires_confirmation}
    if needs_approval:
        payload = {
            "type": "approval_required",
            "proposals": [
                Proposal(
                    call_id=c.call_id,
                    tool_name=c.spec.name,
                    provider=c.spec.provider,
                    risk=c.spec.risk.value,
                    summary=c.spec.summarize(c.args),
                    arguments=args_to_dict(c.args),
                ).to_dict()
                for c in needs_approval
            ],
        }
        # Pauses the graph; on resume `decision` is the runner's Command(resume=...) value.
        decision = interrupt(payload)
        approved_ids |= set(decision.get("approved", []))
        for c in needs_approval:
            if c.call_id not in approved_ids:
                outputs.append(
                    ToolMessage(
                        content=json.dumps(
                            {"declined": True, "message": "The user declined this action."}
                        ),
                        tool_call_id=c.call_id,
                        name=c.spec.name,
                    )
                )

    sources: list[dict[str, Any]] = []
    for call in accepted:
        if call.call_id not in approved_ids:
            continue
        if await kv.get(cancel_key(ctx.run_id)):
            # The user pressed Stop while earlier calls ran: nothing further may execute,
            # especially approved writes.
            outputs.append(
                ToolMessage(
                    content=json.dumps({"cancelled": True, "message": "The user stopped the run."}),
                    tool_call_id=call.call_id,
                    name=call.spec.name,
                )
            )
            continue
        result = await _execute(ctx, call, writer)
        retrieved_at = utcnow().isoformat()
        sources.extend(
            {**src, "retrieved_at": retrieved_at} for src in (result.pop("sources", []) or [])
        )
        outputs.append(
            ToolMessage(
                content=json.dumps(result, default=str),
                tool_call_id=call.call_id,
                name=call.spec.name,
            )
        )
    return {"messages": outputs, "sources": sources}


async def _execute(ctx: AgentContext, call: ValidatedCall, writer: Any) -> dict[str, Any]:
    spec = call.spec
    label = spec.summarize(call.args)
    writer(
        {
            "type": "step",
            "call_id": call.call_id,
            "tool": spec.name,
            "label": label,
            "status": "running",
        }
    )
    audit = AuditService(ctx.db)
    tool_ctx = ToolContext(user=ctx.user, db=ctx.db, run_id=ctx.run_id)
    connection = None
    try:
        if spec.connection_id is not None:
            # Provider tool: the connection must be the user's and usable; decrypt just-in-time.
            from app.services.connection_service import ConnectionService

            connections = ConnectionService(ctx.db, get_settings())
            connection = await connections.get_connection(ctx.user, spec.connection_id)
            if not connection.is_usable:
                raise ProviderError(
                    ProviderErrorKind.expired, "connection not usable", provider=spec.provider
                )
            await connections.refresh_if_needed(ctx.user, connection)
            tool_ctx.credential = connections.vault.load(connection).access_token
        result = await spec.handler(tool_ctx, call.args)
        status = "completed"
        if "plan" in spec.tags and isinstance(result.get("plan"), dict):
            writer({"type": "plan", "call_id": call.call_id, **result["plan"]})
    except ProviderError as exc:
        title, body = exc.user_message()
        result = {"error": body, "code": f"PROVIDER_{exc.kind.value.upper()}", "title": title}
        status = "failed"
        if connection is not None:
            from app.services.connection_service import ConnectionService

            await ConnectionService(ctx.db, get_settings()).record_tool_failure(
                connection, exc, user=ctx.user
            )
    except APIError as exc:
        result = {"error": exc.message, "code": exc.code}
        status = "failed"
    except Exception:  # noqa: BLE001 — never leak internals to the model or the user
        log.exception("tool_execution_failed", extra={"tool": spec.name, "run_id": str(ctx.run_id)})
        result = {"error": "The tool failed unexpectedly."}
        status = "failed"
    await audit.record(
        ctx.user,
        provider=spec.provider,
        action=spec.capability,
        tool_name=spec.name,
        risk_level=spec.risk,
        status=status,
        run_id=ctx.run_id,
        connection_id=spec.connection_id,
        request_metadata={"summary": label, "arg_keys": sorted(args_to_dict(call.args).keys())},
        result_metadata={"ok": status == "completed", "keys": sorted(result.keys())[:10]},
    )
    await ctx.db.commit()
    writer(
        {
            "type": "step",
            "call_id": call.call_id,
            "tool": spec.name,
            "label": label,
            "status": status,
            "result_preview": _preview(result),
            "executed_at": utcnow().isoformat(),
        }
    )
    if status == "completed" and spec.verify is not None and spec.risk != RiskLevel.read:
        verification = await _verify(ctx, call, tool_ctx, result)
        result["verification"] = verification.to_dict()
        writer(
            {
                "type": "verification",
                "call_id": call.call_id,
                "provider": spec.provider,
                **verification.to_dict(),
            }
        )
    return result


async def _verify(
    ctx: AgentContext, call: ValidatedCall, tool_ctx: ToolContext, result: dict[str, Any]
) -> Verification:
    """Read back a write. Never raises: an unreachable provider yields `unverified`, a read-back
    that contradicts the write yields `failed`. Audited like any other external access."""
    spec = call.spec
    assert spec.verify is not None
    try:
        verification = await spec.verify(tool_ctx, call.args, result)
    except ProviderError as exc:
        verification = Verification.unverified(
            f"Could not confirm with {spec.provider}: {exc.user_message()[1]}"
        )
    except Exception:  # noqa: BLE001
        log.exception("tool_verification_failed", extra={"tool": spec.name})
        verification = Verification.unverified("Could not confirm the change")
    await AuditService(ctx.db).record(
        ctx.user,
        provider=spec.provider,
        action="verify",
        tool_name=spec.name,
        risk_level=RiskLevel.read,
        status=verification.status,
        run_id=ctx.run_id,
        connection_id=spec.connection_id,
        request_metadata={"call_id": call.call_id},
        result_metadata={"detail": verification.detail[:200]},
    )
    await ctx.db.commit()
    return verification


def _preview(result: dict[str, Any]) -> str:
    if "error" in result:
        return str(result["error"])
    if "results" in result:
        return f"{len(result['results'])} result(s)"
    if "notes" in result:
        return f"{len(result['notes'])} note(s)"
    if "tasks" in result:
        return f"{len(result['tasks'])} task(s)"
    if "title" in result:
        return str(result["title"])
    if "plan" in result:
        return f"{len(result['plan'].get('steps', []))} step(s)"
    return "done"


def build_graph(
    checkpointer: BaseCheckpointSaver[Any],
) -> CompiledStateGraph[AgentState, AgentContext, AgentState, AgentState]:
    graph = StateGraph(AgentState, context_schema=AgentContext)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tools_node)
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", route_after_agent, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")
    return graph.compile(checkpointer=checkpointer)


__all__ = ["AgentContext", "AgentState", "Proposal", "RiskLevel", "build_graph"]
