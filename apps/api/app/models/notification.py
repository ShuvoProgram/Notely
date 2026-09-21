from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantScopedMixin, TimestampMixin, TZDateTime, UUIDPrimaryKeyMixin


class NotificationKind(enum.StrEnum):
    task_due_soon = "task_due_soon"
    task_overdue = "task_overdue"
    task_completed = "task_completed"
    integration_connected = "integration_connected"
    integration_disconnected = "integration_disconnected"
    integration_auth_required = "integration_auth_required"
    calendar_synced = "calendar_synced"
    calendar_sync_failed = "calendar_sync_failed"


class Notification(UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin, Base):
    """An in-app notification. `dedupe_key` stops the same event (e.g. "task X is overdue")
    from being raised twice; `href` is where the notification takes the user."""

    __tablename__ = "notifications"
    __table_args__ = (
        UniqueConstraint("user_id", "dedupe_key", name="uq_notifications_user_dedupe"),
        Index("ix_notifications_user_created", "user_id", "created_at"),
    )

    kind: Mapped[NotificationKind] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    href: Mapped[str | None] = mapped_column(String(500), nullable=True)
    dedupe_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)
