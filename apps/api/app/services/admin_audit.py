"""Admin audit trail writer. One row per administrative action or denied attempt.

Metadata is whatever the caller passes, filtered through `safe_metadata`: keys that name a
credential are dropped and strings are scrubbed/truncated, so a careless caller can't leak one.
"""

from __future__ import annotations

import re
import uuid
from typing import Any

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import request_id_var
from app.core.rate_limit import client_ip
from app.db.base import utcnow
from app.models.admin import AdminAuditEvent
from app.models.user import User
from app.services.platform_events import scrub

_SECRET_KEY = re.compile(r"(?i)(token|secret|password|api[_-]?key|credential|cookie|authorization)")


def safe_metadata(value: Any, depth: int = 0) -> Any:
    if depth > 4:
        return None
    if isinstance(value, dict):
        return {
            str(k)[:60]: safe_metadata(v, depth + 1)
            for k, v in list(value.items())[:40]
            if not _SECRET_KEY.search(str(k))
        }
    if isinstance(value, list | tuple):
        return [safe_metadata(v, depth + 1) for v in list(value)[:40]]
    if isinstance(value, str):
        return scrub(value, 500)
    if value is None or isinstance(value, bool | int | float):
        return value
    return scrub(str(value), 200)


class AdminAuditService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    def add(
        self,
        *,
        actor: User | None,
        action: str,
        request: Request | None = None,
        resource_type: str | None = None,
        resource_id: uuid.UUID | str | None = None,
        resource_label: str | None = None,
        result: str = "success",
        metadata: dict[str, Any] | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> AdminAuditEvent:
        if request is not None:
            ip_address = ip_address or client_ip(request)
            user_agent = user_agent or request.headers.get("user-agent")
        event = AdminAuditEvent(
            actor_id=actor.id if actor else None,
            actor_email=actor.email if actor else None,
            actor_role=actor.role if actor else None,
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id is not None else None,
            resource_label=(resource_label or None) and resource_label[:320],
            result=result,
            ip_address=(ip_address or None) and ip_address[:64],
            user_agent=(user_agent or None) and user_agent[:512],
            request_id=request_id_var.get(),
            metadata_=safe_metadata(metadata or {}),
            created_at=utcnow(),
        )
        self.db.add(event)
        return event
