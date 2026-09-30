"""Housekeeping jobs."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import delete, or_

from app.core.logging import get_logger
from app.db.base import utcnow
from app.db.session import get_session_factory
from app.models.user import UserSession

log = get_logger(__name__)

# Keep revoked/expired sessions briefly so "signed out from another device" is explainable.
SESSION_RETENTION = timedelta(days=7)


async def cleanup_expired_sessions(_: dict[str, Any]) -> int:
    cutoff = utcnow() - SESSION_RETENTION
    async with get_session_factory()() as db:
        result = await db.execute(
            delete(UserSession).where(
                or_(UserSession.expires_at < cutoff, UserSession.revoked_at < cutoff)
            )
        )
        await db.commit()
    deleted = int(getattr(result, "rowcount", 0) or 0)
    log.info("cleanup_expired_sessions", extra={"deleted": deleted})
    return deleted


PLATFORM_EVENT_RETENTION = timedelta(days=90)


async def purge_platform_events(_: dict[str, Any]) -> int:
    """Platform events feed the admin dashboard's recent history; 90 days is plenty. The admin
    audit log is not purged — it is the record of who changed what."""
    from app.models.admin import PlatformEvent

    cutoff = utcnow() - PLATFORM_EVENT_RETENTION
    async with get_session_factory()() as db:
        result = await db.execute(delete(PlatformEvent).where(PlatformEvent.occurred_at < cutoff))
        await db.commit()
    deleted = int(getattr(result, "rowcount", 0) or 0)
    log.info("purge_platform_events", extra={"deleted": deleted})
    return deleted


async def purge_trashed_notes(_: dict[str, Any]) -> int:
    """Permanently delete notes that have sat in the trash longer than the retention window."""
    from app.repositories.note_repository import NoteRepository
    from app.services.note_service import TRASH_RETENTION

    cutoff = utcnow() - TRASH_RETENTION
    async with get_session_factory()() as db:
        deleted = await NoteRepository(db).purge_trash_older_than(cutoff)
        await db.commit()
    log.info("purge_trashed_notes", extra={"deleted": deleted})
    return deleted
