from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.ai.actions import NoteActionRequest, NoteActionService
from app.ai.llm import provider_name
from app.ai.runner import AIRunner, AIThreadService
from app.ai.tools import get_tool_registry
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
    RunOut,
    ThreadDetailOut,
    ThreadOut,
)
from app.services.audit_service import AuditService

router = APIRouter(prefix="/ai", tags=["ai"])
audit_router = APIRouter(prefix="/audit", tags=["audit"])

ai_limit = rate_limit("ai", lambda s: s.rate_limit_ai_per_minute)


@router.post("/chat", dependencies=[Depends(ai_limit)])
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


@router.post("/approve", dependencies=[Depends(ai_limit)])
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


@router.post("/actions", dependencies=[Depends(ai_limit)])
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
async def get_ai_settings(ctx: CurrentAuth, settings: SettingsDep) -> dict[str, Any]:
    prefs = (
        (ctx.user.preferences or {}).get("ai", {}) if isinstance(ctx.user.preferences, dict) else {}
    )
    return ok(
        AISettingsOut(
            provider=provider_name(settings),
            models=[
                {"id": settings.ai_model_default, "label": "Balanced (default)"},
                {"id": settings.ai_model_fast, "label": "Fast"},
            ],
            preferences=AIPreferences.model_validate(prefs or {}),
            tools=[
                {
                    "name": t.name,
                    "risk": t.risk.value,
                    "provider": t.provider,
                    "description": t.description,
                }
                for t in get_tool_registry().all()
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


@audit_router.get("", response_model=Envelope[list[AuditEventOut]])
async def list_audit(ctx: CurrentAuth, db: DbDep) -> dict[str, Any]:
    return ok(
        [AuditEventOut.model_validate(e) for e in await AuditService(db).list_recent(ctx.user)]
    )
