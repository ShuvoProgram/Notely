"""Worker jobs for automations: run queued executions and start scheduled ones."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from app.automation.runner import AutomationRunner
from app.automation.scheduler import claim_due, recover_stale_runs
from app.core.logging import get_logger
from app.db.base import utcnow
from app.db.session import get_session_factory
from app.models.automation import Automation

log = get_logger(__name__)


async def run_automation_execution(_: dict[str, Any], execution_id: str) -> str | None:
    """Execute one queued run (Run now, Test, a retry or an approval decision)."""
    async with get_session_factory()() as db:
        execution = await AutomationRunner(db).process(execution_id)
        return execution.status if execution else None


async def run_due_automations(_: dict[str, Any]) -> int:
    """Every minute: recover interrupted runs, then claim each due automation and queue its run.

    Each run is its own job (own timeout, runs in parallel), and each claim uses its own
    session, so one slow or failing workflow never delays or breaks another.
    """
    factory = get_session_factory()
    async with factory() as db:
        await recover_stale_runs(db)
        due = list(
            await db.scalars(
                select(Automation.id)
                .where(Automation.enabled.is_(True), Automation.next_run_at <= utcnow())
                .order_by(Automation.next_run_at)
                .limit(100)
            )
        )
    started = 0
    for automation_id in due:
        async with factory() as db:
            try:
                execution = await claim_due(db, automation_id)
                if execution is None:
                    continue
                runner = AutomationRunner(db)
                automation = await db.get(Automation, automation_id)
                active = await runner.active_run(automation) if automation else None
                if active is not None and active.id != execution.id:
                    execution.status = "skipped"
                    execution.error = "Skipped: the previous run was still going."
                    execution.finished_at = utcnow()
                    await db.commit()
                    continue
                await runner.dispatch(execution)
                started += 1
            except Exception:  # noqa: BLE001 — keep the cron alive for other automations
                log.exception(
                    "automation_schedule_failed", extra={"automation_id": str(automation_id)}
                )
    return started
