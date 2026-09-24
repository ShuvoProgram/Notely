from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from app.ai.actions import NoteActionRequest, NoteActionService
from app.ai.byo import model_as_dict
from app.ai.llm import provider_name
from app.ai.runner import AIRunner, AIThreadService, launch_run
from app.ai.streams import hub
from app.ai.tools import build_registry
from app.api.deps import CurrentAuth, DbDep, SettingsDep
from app.api.sse import sse_response
from app.core.rate_limit import rate_limit
from app.core.responses import Envelope, ok
from app.models.ai import RunStatus
from app.models.user import User
from app.schemas.ai import (
    AIPreferences,
    AISettingsOut,
    ApproveRequest,
    AuditEventOut,
    ChatRequest,
    MessageOut,
    ModelDraftIn,
    ModelInfo,
    ModelListIn,
    ModelListOut,
    ModelTestOut,
    RunOut,
    ThreadCreate,
    ThreadDetailOut,
    ThreadOut,
    ThreadUpdate,
    UserModelIn,
    UserModelOut,
    describe_run_error,
)
from app.services.ai_settings_service import AISettingsService
from app.services.audit_service import AuditService

router = APIRouter(prefix="/ai", tags=["ai"])
audit_router = APIRouter(prefix="/audit", tags=["audit"])

ai_limit = rate_limit("ai", lambda s: s.rate_limit_ai_per_minute)
tenant_ai_limit = rate_limit("ai", lambda s: s.rate_limit_ai_tenant_per_minute, key="tenant")


@router.post("/chat", dependencies=[Depends(ai_limit), Depends(tenant_ai_limit)])
async def chat(
    payload: ChatRequest, ctx: CurrentAuth, db: DbDep, settings: SettingsDep
) -> StreamingResponse:
    """Start a run in a conversation (a new one when `thread_id` is omitted) and stream it.

    The run executes in the background (app/ai/streams.py): closing this stream does not stop
    it. Another conversation's runs are never affected; a second send to a conversation that is
    still working fails with 409 RUN_IN_PROGRESS."""
    prepared = await AIRunner(db, settings).prepare_chat(
        ctx.user,
        text=payload.message,
        thread_id=payload.thread_id,
        note_id=payload.note_id,
        retry=payload.retry,
    )
    return sse_response(launch_run(prepared, ctx.user, settings).subscribe())


@router.post("/approve", dependencies=[Depends(ai_limit), Depends(tenant_ai_limit)])
async def approve(
    payload: ApproveRequest, ctx: CurrentAuth, db: DbDep, settings: SettingsDep
) -> StreamingResponse:
    """Decide a pending approval and resume the run. Streams the continuation."""
    prepared = await AIRunner(db, settings).prepare_resume(
        ctx.user,
        run_id=payload.run_id,
        approval_id=payload.approval_id,
        approved=payload.approved_call_ids,
        reject_all=payload.reject_all,
    )
    return sse_response(launch_run(prepared, ctx.user, settings).subscribe())


@router.get("/runs/{run_id}/stream")
async def stream_run(
    run_id: uuid.UUID, ctx: CurrentAuth, db: DbDep, after: int = Query(-1, ge=-1)
) -> StreamingResponse:
    """Re-attach to a run (after a reload or reconnect): replays events with `seq > after`,
    then follows it live. A run executing elsewhere, or already finished, is followed through
    the database instead and ends with its outcome."""
    service = AIThreadService(db)
    run = await service.get_run(ctx.user, run_id)
    channel = hub.get(run.id)
    if channel is not None and channel.user_id == ctx.user.id:
        return sse_response(channel.subscribe(after))
    return sse_response(_follow_persisted(service, ctx.user, run.id))


async def _follow_persisted(
    service: AIThreadService, user: User, run_id: uuid.UUID
) -> AsyncIterator[dict[str, Any]]:
    """Outcome of a run that has no live channel here, polled from the database."""
    while True:
        run = await service.get_run(user, run_id)
        await service.db.refresh(run)
        base = {"run_id": str(run.id), "thread_id": str(run.thread_id)}
        if run.status in (RunStatus.queued, RunStatus.running):
            if not await service.settle_orphan(run):
                yield {"type": "ping", **base}
                await asyncio.sleep(1.0)
                continue
        if run.status == RunStatus.completed:
            message = await service.run_message(user, run.id)
            if message is not None:
                yield {
                    "type": "message",
                    **base,
                    "message_id": str(message.id),
                    "content": message.content,
                    "sources": message.sources or [],
                }
        elif run.status == RunStatus.waiting_for_approval:
            approval = await service.get_pending_approval(user, run)
            if approval is not None:
                calls = {tc.call_id: tc for tc in run.tool_calls}
                yield {
                    "type": "approval_required",
                    **base,
                    "approval_id": str(approval.id),
                    "proposals": [
                        {
                            "call_id": cid,
                            "tool_name": calls[cid].tool_name,
                            "provider": calls[cid].provider,
                            "risk": calls[cid].risk_level.value,
                            "summary": calls[cid].tool_name.replace("_", " "),
                            "arguments": calls[cid].arguments,
                        }
                        for cid in approval.tool_call_ids
                        if cid in calls
                    ],
                }
        elif run.status == RunStatus.failed:
            yield {
                "type": "error",
                **base,
                "code": "AI_RUN_FAILED",
                "message": _failure_text(run.error),
            }
        yield {"type": "done", **base, "status": run.status.value, "usage": run.token_usage}
        return


def _failure_text(error: str | None) -> str:
    return describe_run_error(error) or "The assistant ran into a problem. Please try again."


@router.post("/actions", dependencies=[Depends(ai_limit), Depends(tenant_ai_limit)])
async def note_action(
    payload: NoteActionRequest, ctx: CurrentAuth, db: DbDep, settings: SettingsDep
) -> StreamingResponse:
    """Run a note action (summarize, improve, key points, extract tasks, custom). Streams SSE."""
    return sse_response(NoteActionService(db, settings).run(ctx.user, payload))


@router.get("/threads", response_model=Envelope[list[ThreadOut]])
async def list_threads(ctx: CurrentAuth, db: DbDep, archived: bool = False) -> dict[str, Any]:
    """Conversations by latest activity, each with its last message and open run (if any)."""
    service = AIThreadService(db)
    out: list[ThreadOut] = []
    for item in await service.list_threads(ctx.user, archived=archived):
        run = item.open_run
        if run is not None and await service.settle_orphan(run):
            run = None
        last = item.last_message
        out.append(
            ThreadOut.model_validate(item.thread).model_copy(
                update={
                    "last_message": _preview(last.content) if last else None,
                    "last_message_role": last.role if last else None,
                    "active_run_id": run.id if run else None,
                    "active_run_status": run.status if run else None,
                }
            )
        )
    return ok(out)


@router.post("/threads", response_model=Envelope[ThreadOut], status_code=201)
async def create_thread(payload: ThreadCreate, ctx: CurrentAuth, db: DbDep) -> dict[str, Any]:
    """An empty conversation (its title follows the first message unless one is given)."""
    thread = await AIThreadService(db).create_thread(
        ctx.user, title=payload.title, note_id=payload.note_id
    )
    await db.commit()
    return ok(ThreadOut.model_validate(thread))


@router.get("/threads/{thread_id}", response_model=Envelope[ThreadDetailOut])
async def get_thread(thread_id: uuid.UUID, ctx: CurrentAuth, db: DbDep) -> dict[str, Any]:
    service = AIThreadService(db)
    thread = await service.get_thread(ctx.user, thread_id)
    messages = await service.list_messages(ctx.user, thread.id)
    active = await service.open_run(ctx.user, thread.id)
    if active is not None and await service.settle_orphan(active):
        active = None
    last = await service.last_run(ctx.user, thread.id)
    return ok(
        ThreadDetailOut(
            thread=ThreadOut.model_validate(thread),
            messages=[MessageOut.model_validate(m) for m in messages],
            active_run=RunOut.model_validate(active) if active else None,
            last_run=RunOut.model_validate(last) if last else None,
        )
    )


@router.patch("/threads/{thread_id}", response_model=Envelope[ThreadOut])
async def update_thread(
    thread_id: uuid.UUID, payload: ThreadUpdate, ctx: CurrentAuth, db: DbDep
) -> dict[str, Any]:
    """Rename and/or archive (restore with `archived: false`)."""
    thread = await AIThreadService(db).update_thread(
        ctx.user, thread_id, title=payload.title, archived=payload.archived
    )
    return ok(ThreadOut.model_validate(thread))


@router.delete("/threads/{thread_id}", response_model=Envelope[dict[str, bool]])
async def delete_thread(
    thread_id: uuid.UUID, ctx: CurrentAuth, db: DbDep, settings: SettingsDep
) -> dict[str, Any]:
    service = AIThreadService(db)
    # Stop whatever this conversation is still doing before its rows disappear.
    run = await service.open_run(ctx.user, thread_id)
    if run is not None:
        await AIRunner(db, settings).cancel(ctx.user, run.id)
        await hub.wait(run.id, 5.0)
    await service.delete_thread(ctx.user, thread_id)
    return ok({"deleted": True})


def _preview(text: str, limit: int = 140) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


@router.get("/runs", response_model=Envelope[list[RunOut]])
async def list_runs(ctx: CurrentAuth, db: DbDep) -> dict[str, Any]:
    return ok([RunOut.model_validate(r) for r in await AIThreadService(db).list_runs(ctx.user)])


@router.get("/runs/{run_id}", response_model=Envelope[RunOut])
async def get_run(run_id: uuid.UUID, ctx: CurrentAuth, db: DbDep) -> dict[str, Any]:
    return ok(RunOut.model_validate(await AIThreadService(db).get_run(ctx.user, run_id)))


@router.post("/runs/{run_id}/cancel", response_model=Envelope[RunOut])
async def cancel_run(
    run_id: uuid.UUID, ctx: CurrentAuth, db: DbDep, settings: SettingsDep
) -> dict[str, Any]:
    run = await AIRunner(db, settings).cancel(ctx.user, run_id)
    return ok(RunOut.model_validate(run))


@router.get("/settings", response_model=Envelope[AISettingsOut])
async def get_ai_settings(ctx: CurrentAuth, db: DbDep, settings: SettingsDep) -> dict[str, Any]:
    from app.services.connection_service import ConnectionService

    registry = build_registry(await ConnectionService(db, settings).tools_for_user(ctx.user))
    prefs = (
        (ctx.user.preferences or {}).get("ai", {}) if isinstance(ctx.user.preferences, dict) else {}
    )
    row = await AISettingsService(db, settings).get(ctx.user)
    return ok(
        AISettingsOut(
            provider=provider_name(settings),
            models=[
                {"id": settings.ai_model_default, "label": "Balanced (default)"},
                {"id": settings.ai_model_fast, "label": "Fast"},
            ],
            preferences=AIPreferences.model_validate(prefs or {}),
            user_model=UserModelOut.model_validate(row, from_attributes=True) if row else None,
            user_model_providers=AISettingsService.catalog(),
            encryption_available=bool(settings.encryption_key),
            tools=[
                {
                    "name": t.name,
                    "risk": t.risk.value,
                    "provider": t.provider,
                    "capability": t.capability,
                    "description": t.description,
                }
                for t in registry.all()
            ],
        )
    )


@router.patch("/settings", response_model=Envelope[AIPreferences])
async def update_ai_settings(
    payload: AIPreferences, ctx: CurrentAuth, db: DbDep, settings: SettingsDep
) -> dict[str, Any]:
    if payload.model is not None and payload.model not in (
        settings.ai_model_default,
        settings.ai_model_fast,
    ):
        payload.model = None
    prefs = dict(ctx.user.preferences or {})
    prefs["ai"] = payload.model_dump()
    ctx.user.preferences = prefs
    await db.commit()
    return ok(payload)


@router.put("/settings/model", response_model=Envelope[UserModelOut])
async def set_user_model(
    payload: UserModelIn, ctx: CurrentAuth, db: DbDep, settings: SettingsDep
) -> dict[str, Any]:
    """Save the user's own provider/model/API key (key is write-only, stored encrypted)."""
    row = await AISettingsService(db, settings).upsert(
        ctx.user,
        provider=payload.provider,
        model=payload.model,
        base_url=payload.base_url,
        api_key=payload.api_key,
        enabled=payload.enabled,
        verify=payload.verify,
    )
    return ok(UserModelOut.model_validate(row, from_attributes=True))


@router.post(
    "/settings/model/models",
    response_model=Envelope[ModelListOut],
    dependencies=[Depends(ai_limit)],
)
async def list_user_models(
    payload: ModelListIn, ctx: CurrentAuth, db: DbDep, settings: SettingsDep
) -> dict[str, Any]:
    """The models a key can use, from the vendor's own list endpoint (key never stored here)."""
    models = await AISettingsService(db, settings).list_models(
        ctx.user, provider=payload.provider, api_key=payload.api_key, base_url=payload.base_url
    )
    return ok(ModelListOut(models=[ModelInfo(**model_as_dict(m)) for m in models]))


@router.post(
    "/settings/model/test",
    response_model=Envelope[ModelTestOut],
    dependencies=[Depends(ai_limit)],
)
async def test_user_model(
    ctx: CurrentAuth, db: DbDep, settings: SettingsDep, payload: ModelDraftIn | None = None
) -> dict[str, Any]:
    """One tiny completion. With a body, it tests that draft without storing anything (the
    key in the body is used once and forgotten); without one, the saved configuration."""
    service = AISettingsService(db, settings)
    if payload is not None:
        result = await service.test_draft(
            ctx.user,
            provider=payload.provider,
            model=payload.model,
            base_url=payload.base_url,
            api_key=payload.api_key,
        )
    else:
        result = await service.test(ctx.user)
    return ok(
        ModelTestOut(
            ok=result.ok,
            detail=result.detail,
            latency_ms=result.latency_ms,
            supports_tools=result.supports_tools,
        )
    )


@router.delete("/settings/model", response_model=Envelope[dict[str, bool]])
async def delete_user_model(ctx: CurrentAuth, db: DbDep, settings: SettingsDep) -> dict[str, Any]:
    await AISettingsService(db, settings).delete(ctx.user)
    return ok({"deleted": True})


@audit_router.get("", response_model=Envelope[list[AuditEventOut]])
async def list_audit(ctx: CurrentAuth, db: DbDep) -> dict[str, Any]:
    return ok(
        [AuditEventOut.model_validate(e) for e in await AuditService(db).list_recent(ctx.user)]
    )
