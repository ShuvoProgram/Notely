"""Durable platform events for the admin dashboard (see app.models.admin.PlatformEvent).

`record_event` opens its own short session and never raises: observability must not turn a
failing request or job into a different failure. `add_event` joins the caller's transaction.
"""

from __future__ import annotations

import re
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.base import utcnow
from app.models.admin import PlatformEvent

log = get_logger(__name__)

MAX_MESSAGE = 500
# Belt and braces: anything that looks like a credential is masked before it is stored.
_SECRETS = re.compile(
    r"(?i)(bearer\s+[a-z0-9._\-]+|(?:access|refresh)_token[\"'=:\s]+[^\s\"',}]+|"
    r"(?:api[_-]?key|secret|password)[\"'=:\s]+[^\s\"',}]+|sk-[a-z0-9_\-]{8,})"
)


def scrub(text: str | None, limit: int = MAX_MESSAGE) -> str | None:
    if text is None:
        return None
    return _SECRETS.sub("[redacted]", str(text))[:limit]


def _event(
    category: str,
    kind: str,
    *,
    source: str | None,
    message: str | None,
    user_id: uuid.UUID | str | None,
    metadata: dict[str, Any] | None,
) -> PlatformEvent:
    return PlatformEvent(
        category=category,
        kind=kind,
        source=(source or None) and source[:160],
        message=scrub(message),
        user_id=uuid.UUID(str(user_id)) if user_id else None,
        metadata_={k: v for k, v in (metadata or {}).items() if v is not None},
        occurred_at=utcnow(),
    )


def add_event(
    db: AsyncSession,
    category: str,
    kind: str,
    *,
    source: str | None = None,
    message: str | None = None,
    user_id: uuid.UUID | str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    db.add(
        _event(category, kind, source=source, message=message, user_id=user_id, metadata=metadata)
    )


async def record_event(
    category: str,
    kind: str,
    *,
    source: str | None = None,
    message: str | None = None,
    user_id: uuid.UUID | str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    from app.db.session import get_session_factory

    try:
        async with get_session_factory()() as db:
            db.add(
                _event(
                    category,
                    kind,
                    source=source,
                    message=message,
                    user_id=user_id,
                    metadata=metadata,
                )
            )
            await db.commit()
    except Exception:  # noqa: BLE001 — never let bookkeeping break the caller
        log.warning("platform_event_not_recorded", extra={"kind": kind})
