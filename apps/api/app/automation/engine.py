"""The workflow engine: runs one execution of a workflow, step by step, durably.

Each step's resolved input, full output and a one-line summary are written to
``automation_execution_steps`` as soon as the step finishes, so a run can pause for
approval, survive a worker restart, or have one failed step retried without redoing
the steps that already succeeded.
"""

from __future__ import annotations

import asyncio
import copy
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.automation.actions import ActionContext, ActionDefinition, ActionError
from app.automation.catalog import BUILTIN_APPS, resolve_action
from app.automation.conditions import evaluate
from app.automation.mapping import ReferenceUnavailable, cap, is_blank, resolve, to_text, unwrap
from app.automation.model import ActionStep, BranchStep, FilterStep, Workflow, iter_steps
from app.core.config import Settings
from app.core.logging import get_logger
from app.db.base import utcnow
from app.integrations.base.errors import ProviderError, ProviderErrorKind
from app.integrations.registry import get_providers
from app.models.automation import (
    Automation,
    AutomationApproval,
    AutomationExecution,
    AutomationExecutionStep,
)
from app.models.user import User
from app.services.connection_service import ConnectionService

log = get_logger(__name__)

DONE = ("completed", "simulated", "skipped")
BACKOFF_SECONDS = (2.0, 6.0, 15.0)
_RECONNECT_KINDS = {
    ProviderErrorKind.auth_failed,
    ProviderErrorKind.expired,
    ProviderErrorKind.permission_denied,
    ProviderErrorKind.admin_approval_required,
}


def app_name(app_id: str) -> str:
    if app_id in BUILTIN_APPS:
        return str(BUILTIN_APPS[app_id]["name"])
    provider = get_providers().get(app_id)
    return provider.manifest.name if provider else app_id.replace("_", " ").title()


def summarize_output(action: ActionDefinition, output: Any) -> str:
    """One readable line: "10 emails found", "Created task “Call Sam”"."""
    if isinstance(output, dict):
        message = output.get("message")
        if isinstance(message, str) and message.strip():
            return message.strip()
        declared = {f.key: f.label for f in action.outputs}
        for key, value in output.items():
            if isinstance(value, list):
                label = declared.get(key, key.replace("_", " "))
                noun = label.lower().removesuffix(" found")
                return (
                    f"{len(value)} {noun} found"
                    if action.group == "find"
                    else f"{len(value)} {noun}"
                )
        title = output.get("title") or output.get("subject") or output.get("name")
        if isinstance(title, str) and title:
            return f"{action.label}: {title[:80]}"
    return f"{action.label} — done"


@dataclass
class RunState:
    execution: AutomationExecution
    automation: Automation
    user: User
    scope: dict[str, Any]
    rows: dict[str, AutomationExecutionStep]
    test: bool
    stop_after: str | None = None
    reached_stop: bool = False
    position: int = 0
    waiting: list[str] = field(default_factory=list)


class WorkflowEngine:
    def __init__(
        self,
        db: AsyncSession,
        settings: Settings,
        *,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.db = db
        self.settings = settings
        self.connections = ConnectionService(db, settings)
        self.sleep = sleep

    # --- entry point ------------------------------------------------------------------------

    async def run(self, automation: Automation, user: User, execution: AutomationExecution) -> str:
        """Run or resume `execution`: completed | stopped | failed | waiting_for_approval."""
        context = execution.context or {}
        workflow = Workflow.model_validate(context.get("workflow") or automation.action_config)
        rows = {
            row.step_id: row
            for row in await self.db.scalars(
                select(AutomationExecutionStep).where(
                    AutomationExecutionStep.execution_id == execution.id
                )
            )
        }
        scope: dict[str, Any] = {
            "steps": {},
            "trigger": dict(context.get("trigger") or {}),
            "automation": {"name": automation.name},
        }
        for step_id, row in rows.items():
            if row.status in DONE:
                scope["steps"][step_id] = {"status": row.status, "output": row.output}
        state = RunState(
            execution=execution,
            automation=automation,
            user=user,
            scope=scope,
            rows=rows,
            test=execution.run_mode == "test",
            stop_after=context.get("test_step_id"),
            position=max((r.position for r in rows.values()), default=-1) + 1,
        )
        outcome = await self._run_list(workflow.steps, state)
        if outcome == "stopped" and state.reached_stop:
            outcome = "completed"
        return {"ok": "completed", "waiting": "waiting_for_approval"}.get(outcome, outcome)

    # --- walking ----------------------------------------------------------------------------

    def _row(self, state: RunState, step: Any) -> AutomationExecutionStep:
        row = state.rows.get(step.id)
        if row is None:
            row = AutomationExecutionStep(
                execution_id=state.execution.id,
                step_id=step.id,
                position=state.position,
                kind=step.kind if not isinstance(step, ActionStep) else step.action,
                status="pending",
                input={},
                result={},
                attempts=0,
            )
            state.position += 1
            state.rows[step.id] = row
            self.db.add(row)
        return row

    async def _skip(self, state: RunState, steps: list[Any], reason: str) -> None:
        for step in iter_steps(steps):
            row = self._row(state, step)
            if row.status in DONE:
                continue
            row.status, row.summary, row.finished_at = "skipped", reason, utcnow()
            row.output = None
            state.scope["steps"][step.id] = {"status": "skipped", "output": None}

    async def _run_list(self, steps: list[Any], state: RunState) -> str:
        for index, step in enumerate(steps):
            if state.reached_stop:
                return "stopped"
            outcome = await self._run_step(step, state)
            if outcome == "stopped":
                await self._skip(
                    state, steps[index + 1 :], "Didn't run: an earlier check stopped this path"
                )
                await self.db.commit()
                return "stopped"
            if outcome in ("failed", "waiting"):
                return outcome
            if state.stop_after == step.id:
                state.reached_stop = True
                return "stopped"
        return "ok"

    async def _run_step(self, step: Any, state: RunState) -> str:
        row = self._row(state, step)
        if not step.enabled:
            if row.status not in DONE:
                row.status, row.summary, row.finished_at = "skipped", "Turned off", utcnow()
                state.scope["steps"][step.id] = {"status": "skipped", "output": None}
                if isinstance(step, BranchStep):
                    await self._skip(state, step.then + step.otherwise, "Turned off")
            return "ok"
        if isinstance(step, FilterStep):
            return await self._run_filter(step, row, state)
        if isinstance(step, BranchStep):
            return await self._run_branch(step, row, state)
        return await self._run_action(step, row, state)

    async def _run_filter(
        self, step: FilterStep, row: AutomationExecutionStep, state: RunState
    ) -> str:
        if row.status == "completed":
            return "ok" if (row.output or {}).get("passed") else "stopped"
        row.name = step.name or "Only continue if…"
        try:
            passed = evaluate(step.condition, state.scope)
        except ReferenceUnavailable as exc:
            return await self._fail(state, step, row, self._unavailable(state, exc.step_id), {})
        row.status, row.started_at, row.finished_at = (
            "completed",
            row.started_at or utcnow(),
            utcnow(),
        )
        row.output = {"passed": passed}
        row.summary = "Condition met — continued" if passed else "Condition not met — stopped here"
        state.scope["steps"][step.id] = {"status": "completed", "output": row.output}
        await self.db.commit()
        return "ok" if passed else "stopped"

    async def _run_branch(
        self, step: BranchStep, row: AutomationExecutionStep, state: RunState
    ) -> str:
        if row.status == "completed":
            took_then = (row.output or {}).get("path") == "yes"
        else:
            row.name = step.name or "Split into paths"
            try:
                took_then = evaluate(step.condition, state.scope)
            except ReferenceUnavailable as exc:
                return await self._fail(state, step, row, self._unavailable(state, exc.step_id), {})
            row.status, row.started_at, row.finished_at = "completed", utcnow(), utcnow()
            row.output = {"path": "yes" if took_then else "no"}
            row.summary = "Took the “Yes” path" if took_then else "Took the “No” path"
            state.scope["steps"][step.id] = {"status": "completed", "output": row.output}
            await self._skip(
                state,
                step.otherwise if took_then else step.then,
                "Didn't run: the other path was taken",
            )
            await self.db.commit()
        outcome = await self._run_list(step.then if took_then else step.otherwise, state)
        # A check that stops inside a path only ends that path; the workflow carries on.
        if outcome == "stopped" and not state.reached_stop:
            return "ok"
        return outcome

    # --- actions ----------------------------------------------------------------------------

    def _context(self, state: RunState) -> ActionContext:
        return ActionContext(
            db=self.db,
            user=state.user,
            settings=self.settings,
            connections=self.connections,
            test=state.test,
            timezone=state.automation.timezone or "UTC",
        )

    def _unavailable(self, state: RunState, step_id: str) -> str:
        row = state.rows.get(step_id)
        label = (row.name if row and row.name else step_id).strip()
        return (
            f"This step uses data from “{label}”, which didn't finish. "
            "Fix or retry that step first."
        )

    async def _run_action(
        self, step: ActionStep, row: AutomationExecutionStep, state: RunState
    ) -> str:
        if row.status in DONE:
            return "ok"
        ctx = self._context(state)
        try:
            action = await resolve_action(ctx, step.action)
        except ActionError as exc:
            row.name = step.name or step.action
            return await self._fail(state, step, row, exc.message, exc.details)
        except ProviderError as exc:
            row.name = step.name or step.action
            return await self._fail(state, step, row, *self._provider_problem(step.action, exc))
        row.name = step.name or f"{app_name(action.app)} · {action.label}"
        row.started_at = row.started_at or utcnow()
        row.status = "running"
        try:
            inputs = resolve(step.inputs, state.scope)
        except ReferenceUnavailable as exc:
            return await self._fail(state, step, row, self._unavailable(state, exc.step_id), {})
        for spec in action.inputs:
            if is_blank(inputs.get(spec.key)) and spec.default is not None:
                inputs[spec.key] = spec.default
        row.input = cap(inputs, 50_000)
        missing = [f.label for f in action.inputs if f.required and is_blank(inputs.get(f.key))]
        if missing:
            return await self._fail(
                state,
                step,
                row,
                f"“{missing[0]}” was empty when this step ran. If it uses data from an earlier "
                "step, that step returned nothing for it.",
                {},
            )

        if state.test and action.writes:
            planned = {k: v for k, v in inputs.items() if not is_blank(v)}
            output = {"simulated": True, **planned}
            what = action.summary_of(inputs)
            summary = f"Test run — would {what[:1].lower()}{what[1:]}"
            return await self._finish(state, step, row, action, "simulated", output, summary)

        needs_approval = action.safety == "always_ask" or (
            action.safety == "ask" and step.approval != "auto"
        )
        if needs_approval:
            decision = await self._approval(state, step, action, inputs)
            if decision == "pending":
                row.status = "waiting_for_approval"
                row.summary = f"Waiting for your approval: {action.summary_of(inputs)}"
                state.waiting.append(step.id)
                await self.db.commit()
                return "waiting"
            if decision == "rejected":
                return await self._fail(
                    state, step, row, "You declined this step.", {"declined": True}
                )

        attempts = 0
        while True:
            attempts += 1
            row.attempts = (row.attempts or 0) + 1
            try:
                result = await action.handler(ctx, dict(inputs))
                break
            except ActionError as exc:
                if exc.details.get("retryable") and attempts <= step.retries:
                    await self.sleep(BACKOFF_SECONDS[min(attempts - 1, 2)])
                    continue
                details = {k: v for k, v in exc.details.items() if k != "retryable"}
                return await self._fail(state, step, row, exc.message, details)
            except ProviderError as exc:
                if exc.retryable and attempts <= step.retries:
                    await self.sleep(BACKOFF_SECONDS[min(attempts - 1, 2)])
                    continue
                return await self._fail(state, step, row, *self._provider_problem(step.action, exc))
            except Exception as exc:  # noqa: BLE001 — never leak internals into history
                log.exception("automation_step_crashed", extra={"action": step.action})
                return await self._fail(
                    state,
                    step,
                    row,
                    f"{app_name(action.app)} hit an unexpected problem ({type(exc).__name__}). "
                    "Try the step again.",
                    {},
                )
        output = cap(unwrap(result))
        return await self._finish(
            state, step, row, action, "completed", output, summarize_output(action, output)
        )

    def _provider_problem(self, action_id: str, exc: ProviderError) -> tuple[str, dict[str, Any]]:
        provider_id = action_id.split(".", 1)[0]
        _, detail = exc.user_message()
        details: dict[str, Any] = {"kind": exc.kind.value}
        if exc.kind in _RECONNECT_KINDS:
            details["fix_path"] = f"/app/settings/connections/{provider_id}"
        elif exc.kind == ProviderErrorKind.api_disabled and (exc.detail or "").startswith(
            "https://"
        ):
            details["fix_path"] = exc.detail  # Google's own "enable this API" page
        return f"{app_name(provider_id)}: {detail}", details

    async def _approval(
        self, state: RunState, step: ActionStep, action: ActionDefinition, inputs: dict[str, Any]
    ) -> str:
        approval = await self.db.scalar(
            select(AutomationApproval).where(
                AutomationApproval.execution_id == state.execution.id,
                AutomationApproval.step_id == step.id,
            )
        )
        if approval is None:
            self.db.add(
                AutomationApproval(
                    execution_id=state.execution.id,
                    step_id=step.id,
                    status="pending",
                    proposal={
                        "action": step.action,
                        "app": app_name(action.app),
                        "label": action.label,
                        "summary": action.summary_of(inputs),
                        "safety": action.safety,
                        "inputs": {
                            k: to_text(v)[:2000] for k, v in inputs.items() if not is_blank(v)
                        },
                    },
                    decision={},
                )
            )
            return "pending"
        return str(approval.status)

    async def _finish(
        self,
        state: RunState,
        step: ActionStep,
        row: AutomationExecutionStep,
        action: ActionDefinition,
        status: str,
        output: Any,
        summary: str,
    ) -> str:
        row.status, row.output, row.summary, row.error = status, output, summary, None
        # The group lets the run summary lead with what was found and what was changed.
        row.result = {"group": action.group}
        row.finished_at = utcnow()
        state.scope["steps"][step.id] = {"status": status, "output": copy.deepcopy(output)}
        await self.db.commit()
        return "ok"

    async def _fail(
        self,
        state: RunState,
        step: Any,
        row: AutomationExecutionStep,
        message: str,
        details: dict[str, Any],
    ) -> str:
        row.status, row.error, row.result = "failed", message, details
        row.summary = message
        row.finished_at = utcnow()
        state.scope["steps"][step.id] = {"status": "failed", "output": None}
        state.execution.error = f"{row.name or step.id}: {message}"
        await self.db.commit()
        if isinstance(step, ActionStep) and step.on_error == "continue":
            return "ok"
        return "failed"
