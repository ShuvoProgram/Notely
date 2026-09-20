from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Enum, ForeignKey, Numeric, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import (
    Base,
    JSONType,
    TenantScopedMixin,
    TimestampMixin,
    TZDateTime,
    UUIDPrimaryKeyMixin,
)


class MessageRole(enum.StrEnum):
    user = "user"
    assistant = "assistant"
    tool = "tool"
    system = "system"


class RunStatus(enum.StrEnum):
    queued = "queued"
    running = "running"
    waiting_for_approval = "waiting_for_approval"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class RiskLevel(enum.StrEnum):
    read = "read"
    write = "write"
    external_communication = "external_communication"
    destructive = "destructive"


class ToolCallStatus(enum.StrEnum):
    proposed = "proposed"
    approved = "approved"
    rejected = "rejected"
    executed = "executed"
    failed = "failed"


class ApprovalStatus(enum.StrEnum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    expired = "expired"


class AIThread(UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "ai_threads"

    title: Mapped[str] = mapped_column(String(200), nullable=False, default="New conversation")
    note_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("notes.id", ondelete="SET NULL"), nullable=True, index=True
    )
    archived_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)

    messages: Mapped[list[AIMessage]] = relationship(
        back_populates="thread",
        cascade="all, delete-orphan",
        order_by="AIMessage.created_at",
        lazy="noload",
    )


class AIMessage(UUIDPrimaryKeyMixin, TenantScopedMixin, Base):
    __tablename__ = "ai_messages"

    thread_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("ai_threads.id", ondelete="CASCADE"), nullable=False, index=True
    )
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("ai_runs.id", ondelete="SET NULL"), nullable=True
    )
    role: Mapped[MessageRole] = mapped_column(
        Enum(MessageRole, name="ai_message_role"), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tool_calls: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONType, nullable=True)
    tool_call_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    sources: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONType, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TZDateTime(), nullable=False)

    thread: Mapped[AIThread] = relationship(back_populates="messages")


class AIRun(UUIDPrimaryKeyMixin, TenantScopedMixin, Base):
    __tablename__ = "ai_runs"

    thread_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("ai_threads.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[RunStatus] = mapped_column(
        Enum(RunStatus, name="ai_run_status"), nullable=False, default=RunStatus.queued, index=True
    )
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    provider: Mapped[str | None] = mapped_column(String(60), nullable=True)
    token_usage: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    cost_usd: Mapped[float | None] = mapped_column(Numeric(12, 6), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    steps: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, nullable=False, default=list)
    # Declared by the agent via the `plan_steps` tool for multi-step / cross-app requests:
    # {"goal": str, "steps": [{"title", "kind", "tools", "status"}]}
    plan: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)
    # Source attribution accumulated across the whole run (survives approval pauses).
    sources: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(TZDateTime(), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)

    tool_calls: Mapped[list[AIToolCall]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="AIToolCall.created_at",
        lazy="selectin",
    )
    approvals: Mapped[list[AIApproval]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="AIApproval.created_at",
        lazy="selectin",
    )


class AIToolCall(UUIDPrimaryKeyMixin, TenantScopedMixin, Base):
    __tablename__ = "ai_tool_calls"

    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("ai_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    call_id: Mapped[str] = mapped_column(String(120), nullable=False)  # model-assigned id
    tool_name: Mapped[str] = mapped_column(String(120), nullable=False)
    provider: Mapped[str] = mapped_column(String(60), nullable=False, default="notely")
    risk_level: Mapped[RiskLevel] = mapped_column(
        Enum(RiskLevel, name="ai_risk_level"), nullable=False
    )
    arguments: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)
    status: Mapped[ToolCallStatus] = mapped_column(
        Enum(ToolCallStatus, name="ai_tool_call_status"),
        nullable=False,
        default=ToolCallStatus.proposed,
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Post-execution check for write tools: {"status": verified|unverified|failed, "detail"}
    verification: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TZDateTime(), nullable=False)
    executed_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)

    run: Mapped[AIRun] = relationship(back_populates="tool_calls")


class AIApproval(UUIDPrimaryKeyMixin, TenantScopedMixin, Base):
    """A pending decision covering one or more proposed tool calls."""

    __tablename__ = "ai_approvals"

    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("ai_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[ApprovalStatus] = mapped_column(
        Enum(ApprovalStatus, name="ai_approval_status"),
        nullable=False,
        default=ApprovalStatus.pending,
    )
    tool_call_ids: Mapped[list[str]] = mapped_column(JSONType, nullable=False, default=list)
    decision: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TZDateTime(), nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)

    run: Mapped[AIRun] = relationship(back_populates="approvals")


class AuditEvent(UUIDPrimaryKeyMixin, TenantScopedMixin, Base):
    """Every tool execution (internal or external) produces one of these."""

    __tablename__ = "audit_events"

    connection_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    provider: Mapped[str] = mapped_column(String(60), nullable=False)
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    tool_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    risk_level: Mapped[RiskLevel] = mapped_column(
        Enum(RiskLevel, name="ai_risk_level"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    run_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    request_metadata: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    result_metadata: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(TZDateTime(), nullable=False, index=True)
