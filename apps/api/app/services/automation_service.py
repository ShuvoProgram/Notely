"""Automation use cases: save, switch on, run, test, retry, approve, templates.

Every read and write is scoped to the requesting user; executions, steps and approvals are
always reached through an automation the user owns.
"""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.automation.actions import ActionContext
from app.automation.catalog import Catalog, build_catalog
from app.automation.model import ActionStep, Workflow, iter_steps
from app.automation.runner import ACTIVE, AutomationRunner
from app.automation.scheduler import upcoming
from app.automation.validation import Issue, normalise, validate
from app.core.config import Settings, get_settings
from app.core.exceptions import Conflict, NotFound, ValidationFailed
from app.models.automation import (
    Automation,
    AutomationAction,
    AutomationApproval,
    AutomationExecution,
    AutomationExecutionStep,
    AutomationStatus,
    AutomationTemplate,
)
from app.models.user import User
from app.schemas.automations import (
    ApprovalOut,
    AutomationIn,
    AutomationOut,
    ExecutionDetailOut,
    ExecutionOut,
    ExecutionStepOut,
    IssueOut,
    LastRunOut,
    TemplateIn,
    TemplateOut,
    ValidateOut,
)
from app.services.automation_templates import BUILTIN_TEMPLATES
from app.services.connection_service import ConnectionService


def current_workflow(stored: dict[str, Any]) -> dict[str, Any]:
    """The stored definition in today's format (older versions are upgraded on read)."""
    try:
        return Workflow.model_validate(stored).model_dump()
    except ValidationError:
        return stored


def workflow_apps(workflow: dict[str, Any]) -> list[str]:
    """Apps in the order they appear: "gmail → ai → notely"."""
    try:
        parsed = Workflow.model_validate(workflow)
    except ValidationError:
        return []
    apps: list[str] = []
    for step in iter_steps(parsed.steps):
        if isinstance(step, ActionStep):
            app = step.action.split(".", 1)[0]
            if app not in apps:
                apps.append(app)
    return apps


def execution_out(execution: AutomationExecution) -> ExecutionOut:
    return ExecutionOut(
        id=execution.id,
        status=execution.status,
        run_mode=execution.run_mode,
        summary=(execution.result or {}).get("summary"),
        error=execution.error,
        occurrence_at=execution.occurrence_at,
        started_at=execution.started_at,
        finished_at=execution.finished_at,
        trigger=(execution.context or {}).get("trigger") or {},
    )


def _issues_error(issues: list[Issue]) -> ValidationFailed:
    first = issues[0].message
    more = f" (and {len(issues) - 1} more)" if len(issues) > 1 else ""
    return ValidationFailed(
        f"Finish setting up this automation first: {first}{more}",
        code="AUTOMATION_NOT_READY",
        details={"issues": [issue.to_dict() for issue in issues]},
    )


class AutomationService:
    def __init__(self, db: AsyncSession, settings: Settings | None = None) -> None:
        self.db = db
        self.settings = settings or get_settings()

    def context(self, user: User) -> ActionContext:
        return ActionContext(
            db=self.db,
            user=user,
            settings=self.settings,
            connections=ConnectionService(self.db, self.settings),
        )

    async def catalog(self, user: User) -> Catalog:
        return await build_catalog(self.context(user))

    # --- reading ----------------------------------------------------------------------------

    async def get(self, user: User, automation_id: uuid.UUID) -> Automation:
        row = await self.db.scalar(
            select(Automation).where(Automation.id == automation_id, Automation.user_id == user.id)
        )
        if row is None:
            raise NotFound("Automation not found.")
        return row

    async def _last_runs(self, ids: list[uuid.UUID]) -> dict[uuid.UUID, AutomationExecution]:
        if not ids:
            return {}
        latest = (
            select(
                AutomationExecution.automation_id,
                func.max(AutomationExecution.started_at).label("started_at"),
            )
            .where(
                AutomationExecution.automation_id.in_(ids),
                AutomationExecution.run_mode != "test",
                AutomationExecution.status != "skipped",
            )
            .group_by(AutomationExecution.automation_id)
            .subquery()
        )
        rows = await self.db.scalars(
            select(AutomationExecution).join(
                latest,
                (AutomationExecution.automation_id == latest.c.automation_id)
                & (AutomationExecution.started_at == latest.c.started_at),
            )
        )
        return {row.automation_id: row for row in rows}

    async def _pending_approvals(self, ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
        if not ids:
            return {}
        rows = await self.db.execute(
            select(AutomationExecution.automation_id, func.count(AutomationApproval.id))
            .join(AutomationApproval, AutomationApproval.execution_id == AutomationExecution.id)
            .where(
                AutomationExecution.automation_id.in_(ids),
                AutomationApproval.status == "pending",
                AutomationExecution.status == "waiting_for_approval",
            )
            .group_by(AutomationExecution.automation_id)
        )
        return {automation_id: count for automation_id, count in rows.all()}

    def _out(
        self,
        row: Automation,
        last: AutomationExecution | None = None,
        approvals: int = 0,
        issues: list[Issue] | None = None,
    ) -> AutomationOut:
        return AutomationOut(
            id=row.id,
            name=row.name,
            description=row.description,
            workflow=current_workflow(row.action_config),
            schedule_kind=row.schedule_kind,
            schedule_config=row.schedule_config or {},
            timezone=row.timezone,
            starts_at=row.starts_at,
            ends_at=row.ends_at,
            next_run_at=row.next_run_at if row.enabled else None,
            enabled=row.enabled,
            status=row.status.value if hasattr(row.status, "value") else str(row.status),
            consecutive_failures=row.consecutive_failures or 0,
            created_at=row.created_at,
            updated_at=row.updated_at,
            apps=workflow_apps(row.action_config),
            last_run=LastRunOut(
                id=last.id,
                status=last.status,
                run_mode=last.run_mode,
                summary=(last.result or {}).get("summary"),
                error=last.error,
                started_at=last.started_at,
                finished_at=last.finished_at,
            )
            if last
            else None,
            running=bool(last and last.status in ACTIVE),
            pending_approvals=approvals,
            issues=[IssueOut(**issue.to_dict()) for issue in issues or []],
        )

    async def list_automations(self, user: User) -> list[AutomationOut]:
        rows = list(
            await self.db.scalars(
                select(Automation)
                .where(Automation.user_id == user.id)
                .order_by(Automation.created_at.desc())
            )
        )
        ids = [row.id for row in rows]
        last = await self._last_runs(ids)
        approvals = await self._pending_approvals(ids)
        return [self._out(row, last.get(row.id), approvals.get(row.id, 0)) for row in rows]

    async def view(self, user: User, automation_id: uuid.UUID) -> AutomationOut:
        row = await self.get(user, automation_id)
        last = (await self._last_runs([row.id])).get(row.id)
        approvals = (await self._pending_approvals([row.id])).get(row.id, 0)
        issues = await validate(
            self.context(user), Workflow.model_validate(row.action_config), await self.catalog(user)
        )
        return self._out(row, last, approvals, issues)

    # --- saving -----------------------------------------------------------------------------

    async def check(self, user: User, workflow: dict[str, Any]) -> ValidateOut:
        try:
            parsed = Workflow.model_validate(workflow)
        except ValidationError as exc:
            message = str(exc.errors()[0]["msg"]).removeprefix("Value error, ")
            return ValidateOut(valid=False, issues=[], error=message)
        issues = await validate(self.context(user), parsed, await self.catalog(user))
        return ValidateOut(valid=not issues, issues=[IssueOut(**i.to_dict()) for i in issues])

    async def save(
        self, user: User, payload: AutomationIn, automation_id: uuid.UUID | None = None
    ) -> AutomationOut:
        catalog = await self.catalog(user)
        workflow = normalise(Workflow.model_validate(payload.workflow), catalog)
        issues = await validate(self.context(user), workflow, catalog)
        if payload.enabled and issues:
            raise _issues_error(issues)
        row = await self.get(user, automation_id) if automation_id else None
        if row is None:
            row = Automation(
                tenant_id=user.tenant_id, user_id=user.id, action=AutomationAction.workflow
            )
            self.db.add(row)
        row.name = payload.name
        row.description = payload.description
        row.action = AutomationAction.workflow
        row.action_config = workflow.model_dump()
        row.schedule_kind = payload.schedule_kind
        row.schedule_config = payload.schedule_config
        row.timezone = payload.timezone
        row.starts_at = payload.starts_at
        row.ends_at = payload.ends_at
        row.enabled = payload.enabled
        row.status = AutomationStatus.active if payload.enabled else AutomationStatus.paused
        row.next_run_at = upcoming(row)
        if payload.enabled and payload.schedule_kind != "manual" and row.next_run_at is None:
            raise ValidationFailed("This schedule has no future run. Check the dates.")
        if payload.enabled:
            row.consecutive_failures = 0
        await self.db.commit()
        await self.db.refresh(row)
        last = (await self._last_runs([row.id])).get(row.id)
        return self._out(row, last, 0, issues)

    async def set_enabled(
        self, user: User, automation_id: uuid.UUID, enabled: bool
    ) -> AutomationOut:
        row = await self.get(user, automation_id)
        issues: list[Issue] = []
        if enabled:
            issues = await validate(
                self.context(user),
                Workflow.model_validate(row.action_config),
                await self.catalog(user),
            )
            if issues:
                raise _issues_error(issues)
            row.next_run_at = upcoming(row)
            if row.schedule_kind != "manual" and row.next_run_at is None:
                raise ValidationFailed("This schedule has no future run. Check the dates.")
            row.consecutive_failures = 0
        row.enabled = enabled
        row.status = AutomationStatus.active if enabled else AutomationStatus.paused
        await self.db.commit()
        await self.db.refresh(row)
        last = (await self._last_runs([row.id])).get(row.id)
        return self._out(row, last, 0, issues)

    async def delete(self, user: User, automation_id: uuid.UUID) -> None:
        row = await self.get(user, automation_id)
        await self.db.delete(row)
        await self.db.commit()

    async def duplicate(self, user: User, automation_id: uuid.UUID) -> AutomationOut:
        source = await self.get(user, automation_id)
        return await self.save(
            user,
            AutomationIn(
                name=f"{source.name} (copy)"[:160],
                description=source.description,
                workflow=source.action_config,
                schedule_kind=source.schedule_kind,
                schedule_config=source.schedule_config,
                timezone=source.timezone,
                starts_at=source.starts_at,
                ends_at=source.ends_at,
                enabled=False,
            ),
        )

    # --- running ----------------------------------------------------------------------------

    async def run(
        self, user: User, automation_id: uuid.UUID, idempotency_key: str | None = None
    ) -> ExecutionOut:
        automation = await self.get(user, automation_id)
        runner = AutomationRunner(self.db, self.settings)
        if idempotency_key:
            existing = await self.db.scalar(
                select(AutomationExecution).where(
                    AutomationExecution.automation_id == automation.id,
                    AutomationExecution.idempotency_key == idempotency_key,
                )
            )
            if existing is not None:
                return execution_out(existing)
        if await runner.active_run(automation) is not None:
            raise Conflict("This automation is already running.", code="AUTOMATION_RUNNING")
        issues = await validate(
            self.context(user),
            Workflow.model_validate(automation.action_config),
            await self.catalog(user),
        )
        if issues:
            raise _issues_error(issues)
        execution = await runner.create_execution(
            automation, run_mode="manual", idempotency_key=idempotency_key
        )
        return execution_out(await runner.dispatch(execution))

    async def test(
        self, user: User, automation_id: uuid.UUID, step_id: str | None = None
    ) -> ExecutionOut:
        automation = await self.get(user, automation_id)
        workflow = Workflow.model_validate(automation.action_config)
        if step_id and step_id not in {s.id for s in iter_steps(workflow.steps)}:
            raise ValidationFailed("That step isn't part of this automation.")
        runner = AutomationRunner(self.db, self.settings)
        execution = await runner.create_execution(automation, run_mode="test", test_step_id=step_id)
        return execution_out(await runner.dispatch(execution))

    async def executions(self, user: User, automation_id: uuid.UUID) -> list[ExecutionOut]:
        await self.get(user, automation_id)
        rows = await self.db.scalars(
            select(AutomationExecution)
            .where(AutomationExecution.automation_id == automation_id)
            .order_by(AutomationExecution.started_at.desc())
            .limit(50)
        )
        return [execution_out(row) for row in rows]

    async def _execution(
        self, user: User, automation_id: uuid.UUID, execution_id: uuid.UUID
    ) -> tuple[Automation, AutomationExecution]:
        automation = await self.get(user, automation_id)
        execution = await self.db.scalar(
            select(AutomationExecution).where(
                AutomationExecution.id == execution_id,
                AutomationExecution.automation_id == automation.id,
            )
        )
        if execution is None:
            raise NotFound("Run not found.")
        return automation, execution

    async def execution_detail(
        self, user: User, automation_id: uuid.UUID, execution_id: uuid.UUID
    ) -> ExecutionDetailOut:
        _, execution = await self._execution(user, automation_id, execution_id)
        steps = await self.db.scalars(
            select(AutomationExecutionStep)
            .where(AutomationExecutionStep.execution_id == execution.id)
            .order_by(AutomationExecutionStep.position)
        )
        approvals = await self.db.scalars(
            select(AutomationApproval).where(AutomationApproval.execution_id == execution.id)
        )
        return ExecutionDetailOut(
            **execution_out(execution).model_dump(),
            steps=[
                ExecutionStepOut(
                    step_id=s.step_id,
                    position=s.position,
                    kind=s.kind,
                    name=s.name,
                    status=s.status,
                    summary=s.summary,
                    error=s.error,
                    input=s.input or {},
                    output=s.output,
                    details=s.result or {},
                    attempts=s.attempts or 0,
                    started_at=s.started_at,
                    finished_at=s.finished_at,
                )
                for s in steps
            ],
            approvals=[
                ApprovalOut(
                    id=a.id,
                    execution_id=a.execution_id,
                    step_id=a.step_id,
                    status=a.status,
                    proposal=a.proposal or {},
                    decided_at=a.decided_at,
                )
                for a in approvals
            ],
        )

    async def retry_step(
        self, user: User, automation_id: uuid.UUID, execution_id: uuid.UUID, step_id: str
    ) -> ExecutionOut:
        automation, execution = await self._execution(user, automation_id, execution_id)
        if execution.status != "failed":
            raise Conflict("Only a run that failed can be retried.", code="RUN_NOT_RETRYABLE")
        step = await self.db.scalar(
            select(AutomationExecutionStep).where(
                AutomationExecutionStep.execution_id == execution.id,
                AutomationExecutionStep.step_id == step_id,
            )
        )
        if step is None or step.status != "failed":
            raise Conflict("Only a failed step can be retried.", code="STEP_NOT_RETRYABLE")
        # A retry uses the automation as it is now, so a fix made after the failure applies.
        # Steps that already succeeded keep their outputs.
        current = Workflow.model_validate(automation.action_config)
        if step_id in {s.id for s in iter_steps(current.steps)}:
            context = dict(execution.context or {})
            context["workflow"] = current.model_dump()
            execution.context = context
        failed = await self.db.scalars(
            select(AutomationExecutionStep).where(
                AutomationExecutionStep.execution_id == execution.id,
                AutomationExecutionStep.status.in_(("failed", "skipped")),
            )
        )
        for row in failed:
            await self.db.delete(row)
        execution.status = "queued"
        execution.error = None
        execution.finished_at = None
        execution.attempts += 1
        await self.db.flush()
        return execution_out(await AutomationRunner(self.db, self.settings).dispatch(execution))

    async def decide(
        self, user: User, automation_id: uuid.UUID, approval_id: uuid.UUID, approved: bool
    ) -> ExecutionOut:
        await self.get(user, automation_id)
        approval = await self.db.scalar(
            select(AutomationApproval)
            .join(AutomationExecution, AutomationApproval.execution_id == AutomationExecution.id)
            .where(
                AutomationApproval.id == approval_id,
                AutomationExecution.automation_id == automation_id,
            )
        )
        if approval is None:
            raise NotFound("Approval not found.")
        if approval.status != "pending":
            raise Conflict("This was already decided.", code="APPROVAL_DECIDED")
        _, execution = await self._execution(user, automation_id, approval.execution_id)
        from app.db.base import utcnow

        approval.status = "approved" if approved else "rejected"
        approval.decision = {"approved": approved}
        approval.decided_at = utcnow()
        execution.status = "queued"
        await self.db.flush()
        return execution_out(await AutomationRunner(self.db, self.settings).dispatch(execution))

    # --- templates --------------------------------------------------------------------------

    async def templates(self, user: User) -> list[TemplateOut]:
        catalog = await self.catalog(user)
        connected = {a["id"] for a in catalog.apps if a.get("connected")}
        offered = {a["id"] for a in catalog.apps}
        out: list[TemplateOut] = []
        for template in BUILTIN_TEMPLATES:
            apps = workflow_apps(template["workflow"])
            if any(app not in offered for app in apps):
                continue  # an app this deployment doesn't offer at all
            missing = [app for app in apps if app not in connected]
            out.append(
                TemplateOut(
                    id=template["id"],
                    name=template["name"],
                    description=template["description"],
                    builtin=True,
                    apps=apps,
                    workflow=template["workflow"],
                    schedule_kind=template["schedule_kind"],
                    schedule_config=template["schedule_config"],
                    available=not missing,
                    missing_apps=missing,
                    prompt=template.get("prompt"),
                )
            )
        mine = await self.db.scalars(
            select(AutomationTemplate)
            .where(AutomationTemplate.user_id == user.id)
            .order_by(AutomationTemplate.created_at.desc())
        )
        for row in mine:
            definition = row.definition or {}
            workflow = current_workflow(definition.get("workflow") or {})
            apps = workflow_apps(workflow)
            missing = [app for app in apps if app not in connected]
            out.append(
                TemplateOut(
                    id=str(row.id),
                    name=row.name,
                    description=row.description,
                    builtin=False,
                    apps=apps,
                    workflow=workflow,
                    schedule_kind=definition.get("schedule_kind", "daily"),
                    schedule_config=definition.get("schedule_config", {}),
                    available=not missing,
                    missing_apps=missing,
                )
            )
        return out

    async def save_template(
        self, user: User, automation_id: uuid.UUID, payload: TemplateIn
    ) -> TemplateOut:
        source = await self.get(user, automation_id)
        row = AutomationTemplate(
            tenant_id=user.tenant_id,
            user_id=user.id,
            name=payload.name or source.name,
            description=payload.description or source.description,
            definition={
                "workflow": source.action_config,
                "schedule_kind": source.schedule_kind,
                "schedule_config": source.schedule_config,
                "timezone": source.timezone,
            },
        )
        self.db.add(row)
        await self.db.commit()
        apps = workflow_apps(source.action_config)
        return TemplateOut(
            id=str(row.id),
            name=row.name,
            description=row.description,
            builtin=False,
            apps=apps,
            workflow=current_workflow(source.action_config),
            schedule_kind=source.schedule_kind,
            schedule_config=source.schedule_config,
            available=True,
        )

    async def delete_template(self, user: User, template_id: uuid.UUID) -> None:
        row = await self.db.scalar(
            select(AutomationTemplate).where(
                AutomationTemplate.id == template_id, AutomationTemplate.user_id == user.id
            )
        )
        if row is None:
            raise NotFound("Template not found.")
        await self.db.delete(row)
        await self.db.commit()
