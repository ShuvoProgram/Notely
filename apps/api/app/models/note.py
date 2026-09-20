from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import (
    Base,
    JSONType,
    TenantScopedMixin,
    TimestampMixin,
    TZDateTime,
    UUIDPrimaryKeyMixin,
)


class Folder(UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "folders"
    __table_args__ = (
        UniqueConstraint("user_id", "parent_id", "name", name="uq_folders_user_parent_name"),
    )

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("folders.id", ondelete="CASCADE"), nullable=True, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    notes: Mapped[list[Note]] = relationship(back_populates="folder")


class Tag(UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "tags"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_tags_user_name"),)

    name: Mapped[str] = mapped_column(String(60), nullable=False)
    color: Mapped[str | None] = mapped_column(String(7), nullable=True)  # #RRGGBB


class NoteTag(Base):
    __tablename__ = "note_tags"

    note_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("notes.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )


class Note(UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin, Base):
    """A note. `content_json` is canonical TipTap JSON; `plain_text` is derived server-side."""

    __tablename__ = "notes"
    __table_args__ = (Index("ix_notes_user_updated", "user_id", "updated_at"),)

    title: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    content_json: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    plain_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONType, nullable=False, default=dict
    )
    folder_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("folders.id", ondelete="SET NULL"), nullable=True, index=True
    )
    is_favorite: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    archived_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True, index=True)

    folder: Mapped[Folder | None] = relationship(back_populates="notes")
    tags: Mapped[list[Tag]] = relationship(
        secondary="note_tags", lazy="selectin", order_by=Tag.name
    )
