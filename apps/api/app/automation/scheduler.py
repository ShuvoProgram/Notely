"""When automations run.

Schedule kinds: once, daily, weekly (chosen weekdays), monthly (day of month), custom
(every N days), interval (every N minutes) and manual (only when the user runs it).

The cron job claims a due automation by moving its `next_run_at` forward *before* running
it. The schedule therefore always advances — a failed run never stalls it — and a second
worker can't pick the same occurrence (the unique occurrence constraint is a second guard).
"""

from __future__ import annotations

from calendar import monthrange
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import ValidationFailed
from app.core.logging import get_logger
from app.db.base import utcnow
from app.models.automation import Automation, AutomationExecution, AutomationStatus

log = get_logger(__name__)

STALE_AFTER = timedelta(minutes=30)
MIN_INTERVAL_MINUTES = 15


def _zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except Exception as exc:
        raise ValidationFailed("Use a valid time zone.", code="INVALID_TIMEZONE") from exc


def _clock(config: dict[str, Any]) -> tuple[int, int]:
    raw = str(config.get("time", "09:00"))
    try:
        hour, minute = (int(n) for n in raw.split(":", 1))
    except ValueError as exc:
        raise ValidationFailed("Choose a time like 09:00.") from exc
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValidationFailed("Choose a valid time of day.")
    return hour, minute


def next_occurrence(
    kind: str,
    config: dict[str, Any],
    timezone: str,
    *,
    starts_at: datetime | None = None,
    after: datetime | None = None,
) -> datetime | None:
    """The next run strictly after `after` (default: now), in UTC. None = no schedule."""
    if kind == "manual":
        return None
    tz = _zone(timezone)
    anchor = (after or utcnow()).astimezone(tz)
    if kind == "once":
        if starts_at is None:
            raise ValidationFailed("Choose when this should run.")
        return starts_at.astimezone(UTC)
    if starts_at is not None:
        anchor = max(anchor, starts_at.astimezone(tz) - timedelta(microseconds=1))
    if kind == "interval":
        every = int(config.get("every_minutes") or 60)
        if every < MIN_INTERVAL_MINUTES or every > 24 * 60:
            raise ValidationFailed(
                f"Repeat every {MIN_INTERVAL_MINUTES} minutes to 24 hours.", code="INVALID_SCHEDULE"
            )
        midnight = anchor.replace(hour=0, minute=0, second=0, microsecond=0)
        elapsed = int((anchor - midnight).total_seconds() // 60)
        slot = midnight + timedelta(minutes=(elapsed // every + 1) * every)
        return slot.astimezone(UTC)
    hour, minute = _clock(config)
    local = anchor.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if local <= anchor:
        local += timedelta(days=1)
    if kind == "weekly":
        days = config.get("days") or [local.weekday()]
        if not isinstance(days, list) or any(
            not isinstance(d, int) or d not in range(7) for d in days
        ):
            raise ValidationFailed("Choose at least one day of the week.")
        for _ in range(7):
            if local.weekday() in days:
                break
            local += timedelta(days=1)
    elif kind == "monthly":
        try:
            day = int(config.get("day", local.day))
        except (TypeError, ValueError) as exc:
            raise ValidationFailed("Choose a day of the month.") from exc
        if day not in range(1, 32):
            raise ValidationFailed("Choose a day of the month between 1 and 31.")
        local = local.replace(day=min(day, monthrange(local.year, local.month)[1]))
        if local <= anchor:
            year = local.year + (local.month == 12)
            month = 1 if local.month == 12 else local.month + 1
            local = local.replace(year=year, month=month, day=min(day, monthrange(year, month)[1]))
    elif kind == "custom":
        local += timedelta(days=max(1, int(config.get("interval_days", 1))) - 1)
    elif kind != "daily":
        raise ValidationFailed("Choose how often this should run.", code="INVALID_SCHEDULE")
    # A wall time skipped by a DST change moves to the first real instant after it.
    resolved = local.astimezone(UTC).astimezone(tz)
    if resolved.replace(tzinfo=None) != local.replace(tzinfo=None):
        local = resolved
    return local.astimezone(UTC)


def upcoming(automation: Automation, after: datetime | None = None) -> datetime | None:
    nxt = next_occurrence(
        automation.schedule_kind,
        automation.schedule_config or {},
        automation.timezone,
        starts_at=automation.starts_at,
        after=after,
    )
    if nxt is not None and automation.ends_at is not None and nxt > automation.ends_at:
        return None
    return nxt


async def recover_stale_runs(db: Any) -> int:
    """Runs a crashed worker left behind are marked interrupted so they can be retried."""
    rows = list(
        await db.scalars(
            select(AutomationExecution).where(
                AutomationExecution.status.in_(("queued", "running")),
                AutomationExecution.started_at < utcnow() - STALE_AFTER,
            )
        )
    )
    for row in rows:
        row.status = "failed"
        row.error = "This run was interrupted before it finished. Retry it or run it again."
        row.finished_at = utcnow()
    if rows:
        await db.commit()
    return len(rows)


async def claim_due(db: Any, automation_id: Any) -> AutomationExecution | None:
    """Advance the schedule and create the run for one due automation (or return None)."""
    from app.automation.runner import AutomationRunner

    row = await db.scalar(
        select(Automation).where(Automation.id == automation_id).with_for_update(skip_locked=True)
    )
    now = utcnow()
    if row is None or not row.enabled or row.next_run_at is None or row.next_run_at > now:
        return None
    occurrence = row.next_run_at
    # Missed occurrences (worker down for hours) run once, then the schedule resumes from now.
    row.next_run_at = upcoming(row, after=max(occurrence, now))
    if row.next_run_at is None:
        row.enabled = False
        row.status = AutomationStatus.completed
    try:
        execution = await AutomationRunner(db).create_execution(
            row, run_mode="scheduled", occurrence=occurrence
        )
    except IntegrityError:
        await db.rollback()
        return None
    await db.commit()
    return execution
