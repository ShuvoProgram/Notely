from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.ai.actions import NoteActionRequest, NoteActionService
from app.ai.llm import provider_name
from app.ai.runner import AIRunner, AIThreadService
from app.ai.tools import build_registry
from app.api.deps import CurrentAuth, DbDep, SettingsDep
from app.api.sse import sse_response
from app.core.rate_limit import rate_limit
from app.core.responses import Envelope, ok
from app.models.ai import RunStatus
from app.schemas.ai import (
    AIPreferences,
    AISettingsOut,
    ApproveRequest,
    AuditEventOut,
    ChatRequest,
    MessageOut,
    ModelListIn,
    ModelListOut,
    ModelTestOut,
    RunOut,
    ThreadDetailOut,
    ThreadOut,
    UserModelIn,
    UserModelOut,
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
    """Start (or continue) a conversation. Streams SSE events; see app/ai/runner.py."""
    runner = AIRunner(db, settings)
    return sse_response(
        runner.start(
            ctx.user, text=payload.message, thread_id=payload.thread_id, note_id=payload.note_id
        )
    )


@router.post("/approve", dependencies=[Depends(ai_limit), Depends(tenant_ai_limit)])
async def approve(
    payload: ApproveRequest, ctx: CurrentAuth, db: DbDep, settings: SettingsDep
) -> StreamingResponse:
    """Decide a pending approval and resume the run. Streams the continuation."""
    runner = AIRunner(db, settings)
    return sse_response(
        runner.resume(
            ctx.user,
            run_id=payload.run_id,
            approval_id=payload.approval_id,
            approved=payload.approved_call_ids,
            reject_all=payload.reject_all,
        )
    )


@router.post("/actions", dependencies=[Depends(ai_limit), Depends(tenant_ai_limit)])
async def note_action(
    payload: NoteActionRequest, ctx: CurrentAuth, db: DbDep, settings: SettingsDep
) -> StreamingResponse:
    """Run a note action (summarize, improve, key points, extract tasks, custom). Streams SSE."""
    return sse_response(NoteActionService(db, settings).run(ctx.user, payload))


@router.get("/threads", response_model=Envelope[list[ThreadOut]])
async def list_threads(ctx: CurrentAuth, db: DbDep) -> dict[str, Any]:
    return ok(
        [ThreadOut.model_validate(t) for t in await AIThreadService(db).list_threads(ctx.user)]
    )


@router.get("/threads/{thread_id}", response_model=Envelope[ThreadDetailOut])
async def get_thread(thread_id: uuid.UUID, ctx: CurrentAuth, db: DbDep) -> dict[str, Any]:
    service = AIThreadService(db)
    thread = await service.get_thread(ctx.user, thread_id)
    messages = await service.list_messages(ctx.user, thread.id)
    active = next(
        (
            r
            for r in await service.list_runs(ctx.user)
            if r.thread_id == thread.id
            and r.status in (RunStatus.running, RunStatus.waiting_for_approval)
        ),
        None,
    )
    return ok(
        ThreadDetailOut(
            thread=ThreadOut.model_validate(thread),
            messages=[MessageOut.model_validate(m) for m in messages],
            active_run=RunOut.model_validate(active) if active else None,
        )
    )


@router.delete("/threads/{thread_id}", response_model=Envelope[dict[str, bool]])
async def delete_thread(thread_id: uuid.UUID, ctx: CurrentAuth, db: DbDep) -> dict[str, Any]:
    await AIThreadService(db).delete_thread(ctx.user, thread_id)
    return ok({"deleted": True})


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
    return ok(ModelListOut(models=models))


@router.post(
    "/settings/model/test",
    response_model=Envelope[ModelTestOut],
    dependencies=[Depends(ai_limit)],
)
async def test_user_model(ctx: CurrentAuth, db: DbDep, settings: SettingsDep) -> dict[str, Any]:
    """One tiny completion against the saved configuration; records verified_at/last_error."""
    result = await AISettingsService(db, settings).test(ctx.user)
    return ok(ModelTestOut(ok=result.ok, detail=result.detail, latency_ms=result.latency_ms))


@router.delete("/settings/model", response_model=Envelope[dict[str, bool]])
async def delete_user_model(ctx: CurrentAuth, db: DbDep, settings: SettingsDep) -> dict[str, Any]:
    await AISettingsService(db, settings).delete(ctx.user)
    return ok({"deleted": True})


@audit_router.get("", response_model=Envelope[list[AuditEventOut]])
async def list_audit(ctx: CurrentAuth, db: DbDep) -> dict[str, Any]:
    return ok(
        [AuditEventOut.model_validate(e) for e in await AuditService(db).list_recent(ctx.user)]
    )
