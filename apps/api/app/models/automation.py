from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, Enum, ForeignKey, Index, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import (
    Base,
    JSONType,
    TenantScopedMixin,
    TimestampMixin,
    TZDateTime,
    UUIDPrimaryKeyMixin,
)


class AutomationStatus(enum.StrEnum):
    """Whether the automation is switched on. How its runs went lives on the executions.

    `running`, `failed` and `needs_attention` are legacy values from the first version; they
    are no longer written (migration 0018 folds them into active/paused).
    """

    active = "active"
    paused = "paused"
    running = "running"
    completed = "completed"
    failed = "failed"
    needs_attention = "needs_attention"


class AutomationAction(enum.StrEnum):
    # Only `workflow` is written; the others were single-purpose actions in the first version
    # and are converted to workflows by migration 0018.
    workflow = "workflow"
    create_task = "create_task"
    send_reminder = "send_reminder"
    summarize_notes = "summarize_notes"


class Automation(UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "automations"
    __table_args__ = (Index("ix_automations_due", "enabled", "next_run_at"),)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    action: Mapped[AutomationAction] = mapped_column(
        Enum(AutomationAction, name="automation_action"), nullable=False
    )
    action_config: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    schedule_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    schedule_config: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    timezone: Mapped[str] = mapped_column(String(60), nullable=False, default="UTC")
    starts_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)
    status: Mapped[AutomationStatus] = mapped_column(
        Enum(AutomationStatus, name="automation_status"),
        nullable=False,
        default=AutomationStatus.active,
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Scheduled runs that failed in a row; the scheduler pauses the automation at a limit.
    consecutive_failures: Mapped[int] = mapped_column(nullable=False, default=0)
    # Event triggers only (schedule_kind "event"): high-water mark, recently seen item ids and
    # the outcome of the last check. See app/automation/triggers.py.
    trigger_state: Mapped[dict[str, Any]] = mapped_column(
        JSONType, nullable=False, default=dict, server_default="{}"
    )


class AutomationTemplate(UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin, Base):
    """A user's reusable starting point: a workflow plus its schedule, never executed itself."""

    __tablename__ = "automation_templates"
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    definition: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)


class AutomationExecution(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "automation_executions"
    __table_args__ = (
        UniqueConstraint("automation_id", "occurrence_at", name="uq_automation_occurrence"),
        Index(
            "ix_automation_execution_idempotency",
            "automation_id",
            "idempotency_key",
            unique=True,
        ),
        Index("ix_automation_executions_recent", "automation_id", "started_at"),
    )
    automation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("automations.id", ondelete="CASCADE"), nullable=False
    )
    occurrence_at: Mapped[datetime] = mapped_column(TZDateTime(), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")
    attempts: Mapped[int] = mapped_column(nullable=False, default=0)
    result: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(TZDateTime(), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)
    run_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="scheduled")
    idempotency_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    context: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)


class AutomationExecutionStep(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "automation_execution_steps"
    __table_args__ = (
        UniqueConstraint("execution_id", "step_id", name="uq_automation_execution_step"),
        Index("ix_automation_execution_steps_execution", "execution_id"),
    )

    execution_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("automation_executions.id", ondelete="CASCADE"), nullable=False
    )
    step_id: Mapped[str] = mapped_column(String(64), nullable=False)
    position: Mapped[int] = mapped_column(nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    input: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    # Extra facts about the outcome: a fix-it link, the planned change of a simulated write…
    result: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    # The step's full (size-capped) output: what later steps read and "View details" shows.
    output: Mapped[Any] = mapped_column(JSONType, nullable=True)
    # One plain-language line: "10 emails found", "Updated “Daily Email Summary”".
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    attempts: Mapped[int] = mapped_column(nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)


class AutomationApproval(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "automation_approvals"
    __table_args__ = (
        UniqueConstraint("execution_id", "step_id", name="uq_automation_approval_step"),
        Index("ix_automation_approvals_execution", "execution_id"),
    )

    execution_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("automation_executions.id", ondelete="CASCADE"), nullable=False
    )
    step_id: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    proposal: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    decision: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    decided_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)
