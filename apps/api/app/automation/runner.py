"""Execution lifecycle: create a run, hand it to the worker, record how it went.

    queued → running → completed | stopped | failed | waiting_for_approval

The API only creates the run and enqueues it; the worker executes it. (Without Redis — tests,
a laptop without the queue — the run executes inline so it still happens.)
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.automation.engine import WorkflowEngine
from app.automation.model import Workflow
from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.db.base import utcnow
from app.models.automation import (
    Automation,
    AutomationExecution,
    AutomationExecutionStep,
    AutomationStatus,
)
from app.models.notification import NotificationKind
from app.models.user import User
from app.services.notification_service import NotificationService

log = get_logger(__name__)

TERMINAL = ("completed", "stopped", "failed", "skipped")
ACTIVE = ("queued", "running")
PAUSE_AFTER_FAILURES = 5
JOB = "run_automation_execution"


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


class AutomationRunner:
    def __init__(self, db: AsyncSession, settings: Settings | None = None) -> None:
        self.db = db
        self.settings = settings or get_settings()

    async def previous_run_at(self, automation: Automation) -> datetime | None:
        return await self.db.scalar(
            select(AutomationExecution.started_at)
            .where(
                AutomationExecution.automation_id == automation.id,
                AutomationExecution.run_mode != "test",
                AutomationExecution.status.in_(("completed", "stopped")),
            )
            .order_by(AutomationExecution.started_at.desc())
            .limit(1)
        )

    async def active_run(self, automation: Automation) -> AutomationExecution | None:
        return await self.db.scalar(
            select(AutomationExecution).where(
                AutomationExecution.automation_id == automation.id,
                AutomationExecution.run_mode != "test",
                AutomationExecution.status.in_(ACTIVE),
            )
        )

    async def create_execution(
        self,
        automation: Automation,
        *,
        run_mode: str,
        occurrence: datetime | None = None,
        idempotency_key: str | None = None,
        test_step_id: str | None = None,
        trigger_data: dict[str, Any] | None = None,
    ) -> AutomationExecution:
        """A queued run with a snapshot of the workflow and the trigger's data. An event trigger
        passes the item that started the run as `trigger_data` (its fields become
        `{{trigger.<field>}}`); the base fields always win so they keep their meaning."""
        fired = occurrence or utcnow()
        previous = await self.previous_run_at(automation)
        execution = AutomationExecution(
            automation_id=automation.id,
            occurrence_at=fired,
            status="queued",
            attempts=1,
            run_mode=run_mode,
            idempotency_key=idempotency_key,
            started_at=utcnow(),
            result={},
            context={
                # Snapshot: editing the automation never changes a run already under way.
                "workflow": Workflow.model_validate(automation.action_config).model_dump(),
                "trigger": {
                    **(trigger_data or {}),
                    "type": {"scheduled": "schedule"}.get(run_mode, run_mode),
                    "fired_at": _iso(fired),
                    "previous_run_at": _iso(previous),
                },
                "test_step_id": test_step_id,
            },
        )
        self.db.add(execution)
        await self.db.flush()
        return execution

    async def dispatch(self, execution: AutomationExecution) -> AutomationExecution:
        """Hand the run to the worker; run it here only when no queue is reachable."""
        from app.workers import queue

        await self.db.commit()
        job = await queue.enqueue(JOB, str(execution.id))
        if job is None:
            await self.process(execution.id)
            await self.db.refresh(execution)
        return execution

    async def process(self, execution_id: uuid.UUID | str) -> AutomationExecution | None:
        execution = await self.db.get(AutomationExecution, uuid.UUID(str(execution_id)))
        if execution is None or execution.status in TERMINAL:
            return execution
        automation = await self.db.get(Automation, execution.automation_id)
        user = await self.db.get(User, automation.user_id) if automation else None
        if automation is None or user is None or not user.is_active:
            execution.status, execution.error = "failed", "The automation's owner is unavailable."
            execution.finished_at = utcnow()
            await self.db.commit()
            return execution
        execution.status = "running"
        execution.error = None
        await self.db.commit()
        try:
            outcome = await WorkflowEngine(self.db, self.settings).run(automation, user, execution)
        except Exception:  # noqa: BLE001 — a run must always end in a recorded state
            log.exception("automation_run_crashed", extra={"execution_id": str(execution.id)})
            await self.db.rollback()
            refreshed = await self.db.get(AutomationExecution, execution.id)
            owner = await self.db.get(Automation, automation.id)
            assert refreshed is not None and owner is not None
            execution, automation = refreshed, owner
            outcome = "failed"
            execution.error = execution.error or "Something went wrong while running. Try again."
        await self._finish(automation, user, execution, outcome)
        return execution

    async def _summary(self, execution: AutomationExecution, outcome: str) -> str:
        rows = list(
            await self.db.scalars(
                select(AutomationExecutionStep)
                .where(AutomationExecutionStep.execution_id == execution.id)
                .order_by(AutomationExecutionStep.position)
            )
        )
        if outcome == "failed":
            return execution.error or "A step failed."
        if outcome == "waiting_for_approval":
            waiting = next((r for r in rows if r.status == "waiting_for_approval"), None)
            return waiting.summary if waiting and waiting.summary else "Waiting for your approval"
        done = [r for r in rows if r.status in ("completed", "simulated") and r.summary]
        found = [r.summary for r in done if (r.result or {}).get("group") == "find"]
        changed = [r.summary for r in done if (r.result or {}).get("group") == "do"]
        thought = [r.summary for r in done if (r.result or {}).get("group") == "ai"]
        # "10 emails found · Created 3 tasks · Updated note “Daily Email Summary”"
        highlights = [*found[:1], *changed[:3]] or thought[:2]
        stop = next(
            (r for r in rows if r.kind == "filter" and not (r.output or {}).get("passed", True)),
            None,
        )
        parts = [str(h) for h in highlights]
        if outcome == "stopped" and stop is not None:
            parts.append(f"Stopped: {stop.name or 'a condition'} wasn't met")
        problems = sum(1 for r in rows if r.status == "failed")
        if problems:
            parts.append(f"{problems} step{'s' if problems > 1 else ''} had a problem")
        return " · ".join(parts) or "Finished"

    async def _finish(
        self, automation: Automation, user: User, execution: AutomationExecution, outcome: str
    ) -> None:
        execution.status = outcome
        execution.finished_at = utcnow()
        summary = await self._summary(execution, outcome)
        execution.result = {"outcome": outcome, "summary": summary}
        notify = NotificationService(self.db)
        href = f"/app/automations/{automation.id}?run={execution.id}"
        if outcome == "waiting_for_approval":
            await notify.notify(
                user,
                NotificationKind.automation,
                f"“{automation.name}” is waiting for your approval",
                body=summary,
                href=href,
                dedupe_key=f"automation-approval:{execution.id}",
                commit=False,
            )
        if execution.run_mode == "scheduled":
            if outcome == "failed":
                automation.consecutive_failures = (automation.consecutive_failures or 0) + 1
                if automation.consecutive_failures >= PAUSE_AFTER_FAILURES and automation.enabled:
                    automation.enabled = False
                    automation.status = AutomationStatus.paused
                    await notify.notify(
                        user,
                        NotificationKind.automation,
                        f"“{automation.name}” was paused after {PAUSE_AFTER_FAILURES} failed runs",
                        body=summary,
                        href=href,
                        dedupe_key=f"automation-paused:{execution.id}",
                        commit=False,
                    )
                else:
                    await notify.notify(
                        user,
                        NotificationKind.automation,
                        f"“{automation.name}” didn't finish",
                        body=summary,
                        href=href,
                        dedupe_key=f"automation-failed:{execution.id}",
                        commit=False,
                    )
            elif outcome in ("completed", "stopped"):
                automation.consecutive_failures = 0
        await self.db.commit()


def execution_view(execution: AutomationExecution) -> dict[str, Any]:
    return {
        "id": execution.id,
        "status": execution.status,
        "run_mode": execution.run_mode,
        "summary": (execution.result or {}).get("summary"),
        "error": execution.error,
        "started_at": execution.started_at,
        "finished_at": execution.finished_at,
    }
