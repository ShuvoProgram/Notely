from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from app.api.deps import CurrentAuth, DbDep
from app.core.responses import Envelope, ok
from app.models.notification import NotificationKind
from app.services.notification_service import NotificationService

router = APIRouter(prefix="/notifications", tags=["notifications"])


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: NotificationKind
    title: str
    body: str | None
    href: str | None
    read_at: datetime | None
    created_at: datetime


class NotificationsOut(BaseModel):
    items: list[NotificationOut]
    unread: int


@router.get("", response_model=Envelope[NotificationsOut])
async def list_notifications(ctx: CurrentAuth, db: DbDep) -> dict[str, Any]:
    """The inbox. Time-based task reminders are derived here, so a poll is all a client needs."""
    service = NotificationService(db)
    await service.sweep_tasks(ctx.user)
    await service.sweep_notes(ctx.user)
    items = await service.list(ctx.user)
    return ok(
        NotificationsOut(
            items=[NotificationOut.model_validate(n) for n in items],
            unread=await service.unread_count(ctx.user),
        )
    )


@router.post("/{notification_id}/read", response_model=Envelope[NotificationOut])
async def mark_read(notification_id: uuid.UUID, ctx: CurrentAuth, db: DbDep) -> dict[str, Any]:
    row = await NotificationService(db).mark_read(ctx.user, notification_id)
    return ok(NotificationOut.model_validate(row))


@router.post("/read-all", response_model=Envelope[dict[str, int]])
async def mark_all_read(ctx: CurrentAuth, db: DbDep) -> dict[str, Any]:
    return ok({"marked": await NotificationService(db).mark_all_read(ctx.user)})
