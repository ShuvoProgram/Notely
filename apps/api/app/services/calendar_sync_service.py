"""Tasks ↔ Google Calendar.

One task maps to at most one event (`calendar_event_id`); updates patch that event in place and
unlinking deletes it, so re-syncing never creates duplicates. Uses the user's own Google Calendar
connection (the `google_calendar` connector) — the same OAuth grant the assistant uses.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import APIError, ValidationFailed
from app.db.base import utcnow
from app.integrations.base.errors import ProviderError
from app.integrations.base.rest import RestOAuthProvider
from app.models.integration import ConnectionStatus
from app.models.notification import NotificationKind
from app.models.task import Task, TaskStatus
from app.models.user import User
from app.services.connection_service import ConnectionService
from app.services.notification_service import NotificationService

log = logging.getLogger(__name__)

PROVIDER = "google_calendar"
WRITE_SCOPE = "https://www.googleapis.com/auth/calendar.events"
DEFAULT_DURATION = timedelta(hours=1)


class CalendarNotConnected(APIError):
    status_code = 409
    code = "CALENDAR_NOT_CONNECTED"
    message = "Connect Google Calendar in Settings → Connections first."


class CalendarPermissionMissing(APIError):
    status_code = 409
    code = "CALENDAR_PERMISSION_MISSING"
    message = "Reconnect Google Calendar and allow “Create and update events”."


class CalendarSyncService:
    def __init__(self, db: AsyncSession, settings: Settings) -> None:
        self.db = db
        self.settings = settings
        self.connections = ConnectionService(db, settings)
        self.notifications = NotificationService(db)

    async def status(self, user: User) -> dict[str, Any]:
        """What the tasks UI needs to know before offering "Add to Google Calendar"."""
        conn = await self.connections.get_by_provider(user, PROVIDER)
        connected = bool(conn and conn.status not in (ConnectionStatus.disconnected,))
        return {
            "connected": connected,
            "healthy": bool(conn and conn.status == ConnectionStatus.connected),
            "can_write": bool(conn and WRITE_SCOPE in (conn.scopes or [])),
            "account": conn.external_account_name if conn else None,
            "status": conn.status.value if conn else None,
        }

    async def sync(self, user: User, task: Task, *, calendar_id: str | None = None) -> Task:
        """Create the event for a task, or update the existing one."""
        if task.due_date is None:
            raise ValidationFailed(
                "Give the task a due date first.", details={"fields": {"due_date": ["Required"]}}
            )
        conn = await self.connections.get_by_provider(user, PROVIDER)
        if conn is None or conn.status == ConnectionStatus.disconnected:
            raise CalendarNotConnected()
        if WRITE_SCOPE not in (conn.scopes or []):
            raise CalendarPermissionMissing()
        provider = self.connections.adapter(conn)
        assert isinstance(provider, RestOAuthProvider)
        calendar = calendar_id or task.calendar_id or "primary"
        payload = self._event_payload(task)
        try:
            await self.connections.refresh_if_needed(user, conn)
            ctx = self.connections.context(user, conn)
            async with provider.http(ctx) as http:
                if task.calendar_event_id:
                    resp = await http.patch(
                        f"/calendars/{calendar}/events/{task.calendar_event_id}", json=payload
                    )
                else:
                    resp = await http.post(f"/calendars/{calendar}/events", json=payload)
            event = resp.json()
        except ProviderError as exc:
            await self._record_failure(user, task, exc.user_message()[1])
            raise exc.as_api_error() from exc
        except Exception:  # noqa: BLE001 — network/parse errors are still "sync failed"
            await self._record_failure(user, task, "The calendar request failed.")
            raise
        task.calendar_id = calendar
        task.calendar_event_id = str(event.get("id") or task.calendar_event_id or "")
        task.calendar_event_url = event.get("htmlLink") or task.calendar_event_url
        task.calendar_synced_at = utcnow()
        task.calendar_error = None
        task.external_provider = PROVIDER
        task.external_task_id = task.calendar_event_id
        await self.notifications.notify(
            user,
            NotificationKind.calendar_synced,
            f"Added to Google Calendar: {task.title}",
            body="The event follows the task; edits sync automatically.",
            href="/app/tasks",
            dedupe_key=f"task:{task.id}:calendar:{task.calendar_event_id}",
            commit=False,
        )
        await self.db.commit()
        return task

    async def resync_if_linked(self, user: User, task: Task) -> None:
        """After an edit: keep the event in step. Failures are recorded, never raised, so the
        task change itself always succeeds."""
        if not task.calendar_event_id:
            return
        try:
            await self.sync(user, task)
        except Exception:  # noqa: BLE001
            log.info("calendar_resync_failed", extra={"task_id": str(task.id)})

    async def unlink(self, user: User, task: Task, *, delete_event: bool = True) -> Task:
        """Remove the calendar link; by default also deletes the event (best effort)."""
        if task.calendar_event_id and delete_event:
            conn = await self.connections.get_by_provider(user, PROVIDER)
            if conn is not None and conn.status != ConnectionStatus.disconnected:
                provider = self.connections.adapter(conn)
                assert isinstance(provider, RestOAuthProvider)
                try:
                    await self.connections.refresh_if_needed(user, conn)
                    calendar = task.calendar_id or "primary"
                    async with provider.http(self.connections.context(user, conn)) as http:
                        await http.delete(f"/calendars/{calendar}/events/{task.calendar_event_id}")
                except Exception:  # noqa: BLE001 — the event may already be gone
                    log.info("calendar_event_delete_failed", extra={"task_id": str(task.id)})
        task.calendar_id = None
        task.calendar_event_id = None
        task.calendar_event_url = None
        task.calendar_synced_at = None
        task.calendar_error = None
        if task.external_provider == PROVIDER:
            task.external_provider = None
            task.external_task_id = None
        await self.db.commit()
        return task

    async def _record_failure(self, user: User, task: Task, message: str) -> None:
        task.calendar_error = message
        await self.notifications.notify(
            user,
            NotificationKind.calendar_sync_failed,
            f"Calendar sync failed: {task.title}",
            body=message,
            href="/app/tasks",
            dedupe_key=f"task:{task.id}:calendar-failed:{message[:40]}",
            commit=False,
        )
        await self.db.commit()

    @staticmethod
    def _event_payload(task: Task) -> dict[str, Any]:
        assert task.due_date is not None
        title = task.title if task.status == TaskStatus.open else f"✓ {task.title}"
        body: dict[str, Any] = {
            "summary": title,
            "description": (task.description or "") + "\n\nFrom a Notely task.",
            "extendedProperties": {"private": {"notely_task_id": str(task.id)}},
        }
        if task.due_time is None:
            # All-day event: end date is exclusive in the Google API.
            body["start"] = {"date": task.due_date.isoformat()}
            body["end"] = {"date": (task.due_date + timedelta(days=1)).isoformat()}
        else:
            tz = task.timezone or "UTC"
            start = datetime.combine(task.due_date, task.due_time)
            end = start + DEFAULT_DURATION
            body["start"] = {"dateTime": start.isoformat(), "timeZone": tz}
            body["end"] = {"dateTime": end.isoformat(), "timeZone": tz}
        return body
