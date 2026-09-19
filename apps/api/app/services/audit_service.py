"""Audit log: one event per tool/provider action. Stores metadata, never raw content."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utcnow
from app.models.ai import AuditEvent, RiskLevel
from app.models.user import User


class AuditService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def record(
        self,
        user: User,
        *,
        provider: str,
        action: str,
        risk_level: RiskLevel,
        status: str,
        tool_name: str | None = None,
        run_id: uuid.UUID | None = None,
        connection_id: uuid.UUID | None = None,
        request_metadata: dict[str, Any] | None = None,
        result_metadata: dict[str, Any] | None = None,
    ) -> AuditEvent:
        event = AuditEvent(
            tenant_id=user.tenant_id,
            user_id=user.id,
            provider=provider,
            action=action,
            tool_name=tool_name,
            risk_level=risk_level,
            status=status,
            run_id=run_id,
            connection_id=connection_id,
            request_metadata=request_metadata or {},
            result_metadata=result_metadata or {},
            created_at=utcnow(),
        )
        self.db.add(event)
        await self.db.flush()
        return event

    async def list_recent(self, user: User, limit: int = 100) -> list[AuditEvent]:
        stmt = (
            select(AuditEvent)
            .where(AuditEvent.user_id == user.id)
            .order_by(AuditEvent.created_at.desc())
            .limit(limit)
        )
        return list(await self.db.scalars(stmt))
