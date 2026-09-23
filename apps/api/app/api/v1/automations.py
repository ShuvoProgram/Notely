from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, status

from app.api.deps import CurrentAuth, DbDep, SettingsDep
from app.automation.planner import draft_automation
from app.core.rate_limit import rate_limit
from app.core.responses import Envelope, ok
from app.schemas.automations import (
    ApprovalDecision,
    AutomationIn,
    AutomationOut,
    DraftOut,
    DraftRequest,
    EnabledRequest,
    ExecutionDetailOut,
    ExecutionOut,
    RunRequest,
    TemplateIn,
    TemplateOut,
    TestRequest,
    ValidateOut,
    ValidateRequest,
)
from app.services.automation_service import AutomationService

router = APIRouter(prefix="/automations", tags=["automations"])

ai_limit = rate_limit("ai", lambda s: s.rate_limit_ai_per_minute)
run_limit = rate_limit("automation_run", 30)


@router.get("/catalog", response_model=Envelope[dict[str, Any]])
async def catalog(ctx: CurrentAuth, db: DbDep, settings: SettingsDep) -> dict[str, Any]:
    """Every app and action this user can use, with input and output fields."""
    return ok((await AutomationService(db, settings).catalog(ctx.user)).to_dict())


@router.get("/templates", response_model=Envelope[list[TemplateOut]])
async def templates(ctx: CurrentAuth, db: DbDep, settings: SettingsDep) -> dict[str, Any]:
    return ok(await AutomationService(db, settings).templates(ctx.user))


@router.delete("/templates/{template_id}", response_model=Envelope[dict[str, bool]])
async def delete_template(
    template_id: uuid.UUID, ctx: CurrentAuth, db: DbDep, settings: SettingsDep
) -> dict[str, Any]:
    await AutomationService(db, settings).delete_template(ctx.user, template_id)
    return ok({"deleted": True})


@router.post("/draft", response_model=Envelope[DraftOut], dependencies=[Depends(ai_limit)])
async def draft(
    payload: DraftRequest, ctx: CurrentAuth, db: DbDep, settings: SettingsDep
) -> dict[str, Any]:
    """A reviewable workflow from plain language (or a change to an existing one)."""
    service = AutomationService(db, settings)
    return ok(await draft_automation(service.context(ctx.user), payload))


@router.post("/validate", response_model=Envelope[ValidateOut])
async def validate_workflow(
    payload: ValidateRequest, ctx: CurrentAuth, db: DbDep, settings: SettingsDep
) -> dict[str, Any]:
    return ok(await AutomationService(db, settings).check(ctx.user, payload.workflow))


@router.get("", response_model=Envelope[list[AutomationOut]])
async def list_automations(ctx: CurrentAuth, db: DbDep, settings: SettingsDep) -> dict[str, Any]:
    return ok(await AutomationService(db, settings).list_automations(ctx.user))


@router.post("", status_code=status.HTTP_201_CREATED, response_model=Envelope[AutomationOut])
async def create_automation(
    payload: AutomationIn, ctx: CurrentAuth, db: DbDep, settings: SettingsDep
) -> dict[str, Any]:
    return ok(await AutomationService(db, settings).save(ctx.user, payload))


@router.get("/{automation_id}", response_model=Envelope[AutomationOut])
async def get_automation(
    automation_id: uuid.UUID, ctx: CurrentAuth, db: DbDep, settings: SettingsDep
) -> dict[str, Any]:
    return ok(await AutomationService(db, settings).view(ctx.user, automation_id))


@router.patch("/{automation_id}", response_model=Envelope[AutomationOut])
async def update_automation(
    automation_id: uuid.UUID,
    payload: AutomationIn,
    ctx: CurrentAuth,
    db: DbDep,
    settings: SettingsDep,
) -> dict[str, Any]:
    return ok(await AutomationService(db, settings).save(ctx.user, payload, automation_id))


@router.delete("/{automation_id}", response_model=Envelope[dict[str, bool]])
async def delete_automation(
    automation_id: uuid.UUID, ctx: CurrentAuth, db: DbDep, settings: SettingsDep
) -> dict[str, Any]:
    await AutomationService(db, settings).delete(ctx.user, automation_id)
    return ok({"deleted": True})


@router.post("/{automation_id}/duplicate", response_model=Envelope[AutomationOut])
async def duplicate_automation(
    automation_id: uuid.UUID, ctx: CurrentAuth, db: DbDep, settings: SettingsDep
) -> dict[str, Any]:
    return ok(await AutomationService(db, settings).duplicate(ctx.user, automation_id))


@router.post("/{automation_id}/template", response_model=Envelope[TemplateOut])
async def save_as_template(
    automation_id: uuid.UUID,
    payload: TemplateIn,
    ctx: CurrentAuth,
    db: DbDep,
    settings: SettingsDep,
) -> dict[str, Any]:
    return ok(await AutomationService(db, settings).save_template(ctx.user, automation_id, payload))


@router.post("/{automation_id}/enabled", response_model=Envelope[AutomationOut])
async def set_enabled(
    automation_id: uuid.UUID,
    payload: EnabledRequest,
    ctx: CurrentAuth,
    db: DbDep,
    settings: SettingsDep,
) -> dict[str, Any]:
    service = AutomationService(db, settings)
    return ok(await service.set_enabled(ctx.user, automation_id, payload.enabled))


@router.post(
    "/{automation_id}/run",
    response_model=Envelope[ExecutionOut],
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(run_limit)],
)
async def run_now(
    automation_id: uuid.UUID,
    payload: RunRequest,
    ctx: CurrentAuth,
    db: DbDep,
    settings: SettingsDep,
) -> dict[str, Any]:
    """Start a real run in the background; poll the run for progress."""
    service = AutomationService(db, settings)
    return ok(await service.run(ctx.user, automation_id, payload.idempotency_key))


@router.post(
    "/{automation_id}/test",
    response_model=Envelope[ExecutionOut],
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(run_limit)],
)
async def test_run(
    automation_id: uuid.UUID,
    payload: TestRequest,
    ctx: CurrentAuth,
    db: DbDep,
    settings: SettingsDep,
) -> dict[str, Any]:
    """Reads and AI run for real; anything that would change data is only simulated."""
    service = AutomationService(db, settings)
    return ok(await service.test(ctx.user, automation_id, payload.step_id))


@router.get("/{automation_id}/runs", response_model=Envelope[list[ExecutionOut]])
async def runs(
    automation_id: uuid.UUID, ctx: CurrentAuth, db: DbDep, settings: SettingsDep
) -> dict[str, Any]:
    return ok(await AutomationService(db, settings).executions(ctx.user, automation_id))


@router.get("/{automation_id}/runs/{run_id}", response_model=Envelope[ExecutionDetailOut])
async def run_detail(
    automation_id: uuid.UUID,
    run_id: uuid.UUID,
    ctx: CurrentAuth,
    db: DbDep,
    settings: SettingsDep,
) -> dict[str, Any]:
    service = AutomationService(db, settings)
    return ok(await service.execution_detail(ctx.user, automation_id, run_id))


@router.post(
    "/{automation_id}/runs/{run_id}/steps/{step_id}/retry",
    response_model=Envelope[ExecutionOut],
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(run_limit)],
)
async def retry_step(
    automation_id: uuid.UUID,
    run_id: uuid.UUID,
    step_id: str,
    ctx: CurrentAuth,
    db: DbDep,
    settings: SettingsDep,
) -> dict[str, Any]:
    service = AutomationService(db, settings)
    return ok(await service.retry_step(ctx.user, automation_id, run_id, step_id))


@router.post(
    "/{automation_id}/approvals/{approval_id}",
    response_model=Envelope[ExecutionOut],
    status_code=status.HTTP_202_ACCEPTED,
)
async def decide_approval(
    automation_id: uuid.UUID,
    approval_id: uuid.UUID,
    payload: ApprovalDecision,
    ctx: CurrentAuth,
    db: DbDep,
    settings: SettingsDep,
) -> dict[str, Any]:
    service = AutomationService(db, settings)
    return ok(await service.decide(ctx.user, automation_id, approval_id, payload.approved))
