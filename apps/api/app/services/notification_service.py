"""In-app notifications: a small, deduplicated inbox per user.

Events are raised by the code that knows about them (connections, calendar sync, tasks). Time-based
ones (due soon / overdue) are derived on read by `sweep_tasks`, so no scheduler is needed and a
task is never nagged about twice thanks to the dedupe key.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFound
from app.db.base import utcnow
from app.models.notification import Notification, NotificationKind
from app.models.task import Task, TaskStatus
from app.models.user import User

DUE_SOON_WINDOW = timedelta(hours=24)
KEEP = 200  # newest notifications kept per user


def _prefs(user: User) -> dict[str, bool]:
    prefs = user.preferences if isinstance(user.preferences, dict) else {}
    raw = prefs.get("notifications") if isinstance(prefs, dict) else None
    return dict(raw) if isinstance(raw, dict) else {}


# Which preference switch governs each kind (default on).
PREF_FOR_KIND: dict[NotificationKind, str] = {
    NotificationKind.task_due_soon: "task_reminders",
    NotificationKind.task_overdue: "task_reminders",
    NotificationKind.task_completed: "task_completed",
    NotificationKind.integration_connected: "integrations",
    NotificationKind.integration_disconnected: "integrations",
    NotificationKind.integration_auth_required: "integrations",
    NotificationKind.calendar_synced: "calendar_sync",
    NotificationKind.calendar_sync_failed: "calendar_sync",
    NotificationKind.note_reminder: "note_reminders",
    NotificationKind.note_shared: "sharing",
    NotificationKind.automation: "automations",
}


class NotificationService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def notify(
        self,
        user: User,
        kind: NotificationKind,
        title: str,
        *,
        body: str | None = None,
        href: str | None = None,
        dedupe_key: str | None = None,
        commit: bool = True,
    ) -> Notification | None:
        """Raise a notification unless the user switched that kind off or it already exists."""
        if _prefs(user).get(PREF_FOR_KIND[kind], True) is False:
            return None
        if dedupe_key is not None:
            existing = await self.db.scalar(
                select(Notification.id).where(
                    Notification.user_id == user.id, Notification.dedupe_key == dedupe_key
                )
            )
            if existing is not None:
                return None
        row = Notification(
            tenant_id=user.tenant_id,
            user_id=user.id,
            kind=kind,
            title=title[:200],
            body=body,
            href=href,
            dedupe_key=dedupe_key,
        )
        self.db.add(row)
        try:
            if commit:
                await self.db.commit()
            else:
                await self.db.flush()
        except IntegrityError:  # raced on the dedupe key — the other writer won
            await self.db.rollback()
            return None
        return row

    async def list(self, user: User, *, limit: int = 50) -> list[Notification]:
        stmt = (
            select(Notification)
            .where(Notification.user_id == user.id, Notification.dismissed_at.is_(None))
            .order_by(Notification.created_at.desc())
            .limit(limit)
        )
        return list(await self.db.scalars(stmt))

    async def unread_count(self, user: User) -> int:
        return int(
            await self.db.scalar(
                select(func.count()).where(
                    Notification.user_id == user.id,
                    Notification.read_at.is_(None),
                    Notification.dismissed_at.is_(None),
                )
            )
            or 0
        )

    async def _own(self, user: User, notification_id: uuid.UUID) -> Notification:
        row = await self.db.scalar(
            select(Notification).where(
                Notification.id == notification_id,
                Notification.user_id == user.id,
                Notification.dismissed_at.is_(None),
            )
        )
        if row is None:
            raise NotFound("Notification not found.")
        return row

    async def mark_read(self, user: User, notification_id: uuid.UUID) -> Notification:
        row = await self._own(user, notification_id)
        if row.read_at is None:
            row.read_at = utcnow()
            await self.db.commit()
        return row

    async def mark_unread(self, user: User, notification_id: uuid.UUID) -> Notification:
        row = await self._own(user, notification_id)
        if row.read_at is not None:
            row.read_at = None
            await self.db.commit()
        return row

    async def dismiss(self, user: User, notification_id: uuid.UUID) -> None:
        """Remove from the inbox; the row stays so a derived reminder isn't raised again."""
        row = await self._own(user, notification_id)
        now = utcnow()
        row.dismissed_at = now
        row.read_at = row.read_at or now
        await self.db.commit()

    async def mark_all_read(self, user: User) -> int:
        result = await self.db.execute(
            update(Notification)
            .where(
                Notification.user_id == user.id,
                Notification.read_at.is_(None),
                Notification.dismissed_at.is_(None),
            )
            .values(read_at=utcnow())
        )
        await self.db.commit()
        return int(getattr(result, "rowcount", 0) or 0)

    async def sweep_notes(self, user: User) -> None:
        """Fire note reminders whose time has come (each exactly once)."""
        from app.models.note import Note  # local import: avoid a models cycle at import time

        now = utcnow()
        due = list(
            await self.db.scalars(
                select(Note).where(
                    Note.user_id == user.id,
                    Note.deleted_at.is_(None),
                    Note.reminder_at.is_not(None),
                    Note.reminder_at <= now,
                )
            )
        )
        for note in due:
            stamp = note.reminder_at.isoformat() if note.reminder_at else ""
            await self.notify(
                user,
                NotificationKind.note_reminder,
                f"Reminder: {note.title or 'Untitled note'}",
                body=(note.plain_text or "")[:120] or None,
                href=f"/app/notes/{note.id}",
                dedupe_key=f"note:{note.id}:reminder:{stamp}",
                commit=False,
            )
        await self.db.commit()

    async def sweep_tasks(self, user: User) -> None:
        """Derive due-soon / overdue notifications for open tasks with a due date."""
        tasks = list(
            await self.db.scalars(
                select(Task).where(
                    Task.user_id == user.id,
                    Task.status == TaskStatus.open,
                    Task.due_date.is_not(None),
                )
            )
        )
        now = utcnow()
        for task in tasks:
            due = _due_at(task)
            if due is None:
                continue
            when = _when_label(task)
            href = "/app/tasks"
            if due < now:
                await self.notify(
                    user,
                    NotificationKind.task_overdue,
                    f"Overdue: {task.title}",
                    body=f"Was due {when}.",
                    href=href,
                    dedupe_key=f"task:{task.id}:overdue:{task.due_date}:{task.due_time}",
                    commit=False,
                )
            elif due - now <= DUE_SOON_WINDOW:
                await self.notify(
                    user,
                    NotificationKind.task_due_soon,
                    f"Due soon: {task.title}",
                    body=f"Due {when}.",
                    href=href,
                    dedupe_key=f"task:{task.id}:soon:{task.due_date}:{task.due_time}",
                    commit=False,
                )
        await self.db.commit()

    async def prune(self, user: User) -> None:
        ids = list(
            await self.db.scalars(
                select(Notification.id)
                .where(Notification.user_id == user.id)
                .order_by(Notification.created_at.desc())
                .offset(KEEP)
            )
        )
        if ids:
            for row in await self.db.scalars(select(Notification).where(Notification.id.in_(ids))):
                await self.db.delete(row)
            await self.db.commit()


def _tz(task: Task) -> ZoneInfo:
    try:
        return ZoneInfo(task.timezone or "UTC")
    except Exception:  # noqa: BLE001 — unknown zone name from a client
        return ZoneInfo("UTC")


def _due_at(task: Task) -> datetime | None:
    """The instant a task is due: its time in its timezone, or end of day for all-day tasks."""
    if task.due_date is None:
        return None
    d: date = task.due_date
    t: time = task.due_time or time(23, 59)
    return datetime.combine(d, t, tzinfo=_tz(task))


def _when_label(task: Task) -> str:
    if task.due_date is None:
        return ""
    label = task.due_date.strftime("%b %d")
    if task.due_time is not None:
        label += f" at {task.due_time.strftime('%H:%M')}"
    return label
