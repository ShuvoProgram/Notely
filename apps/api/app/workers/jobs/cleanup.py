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
