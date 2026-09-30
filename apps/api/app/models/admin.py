"""Platform administration: the admin audit trail, platform events and runtime settings.

These tables are deployment-wide (not tenant-scoped) and deliberately outlive the users they
mention: actor/subject foreign keys are SET NULL and a readable snapshot (email) is kept.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, JSONType, TZDateTime, UUIDPrimaryKeyMixin


class AdminAuditEvent(UUIDPrimaryKeyMixin, Base):
    """One administrative action (or a denied attempt at one). Metadata never holds secrets."""

    __tablename__ = "admin_audit_events"
    __table_args__ = (
        Index("ix_admin_audit_events_created", "created_at"),
        Index("ix_admin_audit_events_action_created", "action", "created_at"),
        Index("ix_admin_audit_events_resource", "resource_type", "resource_id"),
    )

    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    actor_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    actor_role: Mapped[str | None] = mapped_column(String(20), nullable=True)
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    resource_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    resource_label: Mapped[str | None] = mapped_column(String(320), nullable=True)
    result: Mapped[str] = mapped_column(String(20), nullable=False, default="success")
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONType, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(TZDateTime(), nullable=False)


class PlatformEvent(UUIDPrimaryKeyMixin, Base):
    """Something the platform observed that per-process metrics would forget on restart:
    unhandled API errors, failed background jobs, OAuth failures, sign-in events, AI workflow
    drafts. Messages are short, sanitized summaries — never payloads, tokens or content."""

    __tablename__ = "platform_events"
    __table_args__ = (
        Index("ix_platform_events_occurred", "occurred_at"),
        Index("ix_platform_events_kind_occurred", "kind", "occurred_at"),
        Index("ix_platform_events_category_occurred", "category", "occurred_at"),
        Index("ix_platform_events_user_occurred", "user_id", "occurred_at"),
    )

    category: Mapped[str] = mapped_column(String(20), nullable=False)  # error|security|usage
    kind: Mapped[str] = mapped_column(String(60), nullable=False)
    source: Mapped[str | None] = mapped_column(String(160), nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONType, nullable=False, default=dict
    )
    occurred_at: Mapped[datetime] = mapped_column(TZDateTime(), nullable=False)


class PlatformSetting(Base):
    """A runtime setting admins change without a deploy. Values are validated by
    app.services.platform_settings; secrets never live here (they stay in the environment)."""

    __tablename__ = "platform_settings"

    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[Any] = mapped_column(JSONType, nullable=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(TZDateTime(), nullable=False)


def _analytics_indexes() -> None:
    """Indexes that serve the admin analytics (time-range scans across all users). Declared
    here, beside the feature that needs them, and created by migration 0022."""
    from app.models.ai import AIRun, AIToolCall
    from app.models.automation import AutomationExecution
    from app.models.note import Note
    from app.models.task import Task
    from app.models.user import User

    Index("ix_users_created_at", User.created_at)
    Index("ix_notes_created_at", Note.created_at)
    Index("ix_tasks_created_at", Task.created_at)
    Index("ix_ai_runs_created_at", AIRun.created_at)
    Index("ix_ai_tool_calls_created_at", AIToolCall.created_at)
    Index("ix_automation_executions_started_at", AutomationExecution.started_at)
    Index(
        "ix_automation_executions_status_started",
        AutomationExecution.status,
        AutomationExecution.started_at,
    )


_analytics_indexes()
