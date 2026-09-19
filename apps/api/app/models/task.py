from __future__ import annotations

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import Date, Enum, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantScopedMixin, TimestampMixin, TZDateTime, UUIDPrimaryKeyMixin


class TaskPriority(enum.StrEnum):
    none = "none"
    low = "low"
    medium = "medium"
    high = "high"


class TaskStatus(enum.StrEnum):
    open = "open"
    done = "done"


class TaskSource(enum.StrEnum):
    manual = "manual"
    ai = "ai"


class Task(UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin, Base):
    """A task, possibly extracted from a note and possibly synced to an external provider."""

    __tablename__ = "tasks"

    note_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("notes.id", ondelete="SET NULL"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    priority: Mapped[TaskPriority] = mapped_column(
        Enum(TaskPriority, name="task_priority"), nullable=False, default=TaskPriority.none
    )
    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus, name="task_status"), nullable=False, default=TaskStatus.open, index=True
    )
    source: Mapped[TaskSource] = mapped_column(
        Enum(TaskSource, name="task_source"), nullable=False, default=TaskSource.manual
    )
    external_provider: Mapped[str | None] = mapped_column(String(60), nullable=True)
    external_task_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)
