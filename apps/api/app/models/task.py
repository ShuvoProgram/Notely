from __future__ import annotations

import enum
import uuid
from datetime import date, datetime, time

from sqlalchemy import Date, Enum, ForeignKey, Index, String, Text, Time, Uuid
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
    __table_args__ = (Index("ix_tasks_user_status_created", "user_id", "status", "created_at"),)

    note_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("notes.id", ondelete="SET NULL"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Wall-clock time in the user's timezone (stored with it below); None means all day.
    due_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    timezone: Mapped[str | None] = mapped_column(String(60), nullable=True)
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
    # Google Calendar link: one event per task, updated in place, never duplicated.
    calendar_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    calendar_event_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    calendar_event_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    calendar_synced_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)
    calendar_error: Mapped[str | None] = mapped_column(Text, nullable=True)
