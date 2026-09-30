"""The change journal: every change an AI run or an automation run makes, with enough before /
after state to reverse it, and the record of each batch revert.

A *batch* is one AI run (`ai_run`) or one automation execution (`automation_run`). Rows are
written by the services that make the change (tasks, notes, calendar) and by the tool runners
for connected apps, while a batch context is active (app.services.action_journal). Nothing is
inferred from log text. Rows are never deleted by a revert: they are marked.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import (
    Base,
    JSONType,
    TenantScopedMixin,
    TZDateTime,
    UUIDPrimaryKeyMixin,
)

BATCH_KINDS = ("ai_run", "automation_run")


class ActionRecord(UUIDPrimaryKeyMixin, TenantScopedMixin, Base):
    __tablename__ = "action_records"
    __table_args__ = (
        Index("ix_action_records_batch", "batch_kind", "batch_id", "sequence"),
        Index("ix_action_records_user_created", "user_id", "created_at"),
    )

    batch_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    batch_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # The tool call id (AI) or workflow step id (automation) that made the change.
    source_ref: Mapped[str | None] = mapped_column(String(120), nullable=True)
    provider: Mapped[str] = mapped_column(String(60), nullable=False, default="notely")
    kind: Mapped[str] = mapped_column(String(80), nullable=False)  # task.create, note.update, ...
    resource_type: Mapped[str] = mapped_column(String(40), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    label: Mapped[str] = mapped_column(String(300), nullable=False)
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)
    # Provider changes: the ids the reverse call needs (never tokens).
    revert_ref: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)
    reversible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    irreversible_reason: Mapped[str | None] = mapped_column(String(300), nullable=True)
    # applied → reverted | revert_failed | revert_skipped (changed since, already gone, ...)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="applied")
    revert_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    revert_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reverted_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TZDateTime(), nullable=False)


class BatchRevert(UUIDPrimaryKeyMixin, TenantScopedMixin, Base):
    """One per batch (unique), so a second Revert click can't run it twice. `status`:
    running → reverted (all done) | partial (some couldn't be reverted) | failed."""

    __tablename__ = "batch_reverts"
    __table_args__ = (
        UniqueConstraint("batch_kind", "batch_id", name="uq_batch_reverts_batch"),
    )

    batch_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    batch_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")
    requested_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    summary: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    requested_at: Mapped[datetime] = mapped_column(TZDateTime(), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)
