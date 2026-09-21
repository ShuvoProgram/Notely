from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import (
    Base,
    JSONType,
    TenantScopedMixin,
    TimestampMixin,
    TZDateTime,
    UUIDPrimaryKeyMixin,
    utcnow,
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
    # Appearance + reminder. `color` is a preset name or a custom "#rrggbb" (validated in the
    # schema); the UI renders either as a soft tint, never a full-bleed fill.
    color: Mapped[str] = mapped_column(String(20), nullable=False, default="default")
    reminder_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True, index=True)
    archived_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True, index=True)

    folder: Mapped[Folder | None] = relationship(back_populates="notes")
    collaborators: Mapped[list[NoteCollaborator]] = relationship(
        back_populates="note", lazy="selectin", cascade="all, delete-orphan"
    )
    tags: Mapped[list[Tag]] = relationship(
        secondary="note_tags", lazy="selectin", order_by=Tag.name
    )


NOTE_COLORS = (
    "default",
    "warm",
    "cream",
    "yellow",
    "green",
    "mint",
    "blue",
    "sky",
    "purple",
    "lavender",
    "pink",
    "rose",
    "gray",
)


class NoteVersion(UUIDPrimaryKeyMixin, Base):
    """A snapshot of a note's title + body. Written on meaningful changes (see NoteService),
    not on every keystroke; `note_version` is the note's counter at snapshot time."""

    __tablename__ = "note_versions"
    __table_args__ = (Index("ix_note_versions_note_created", "note_id", "created_at"),)

    note_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("notes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    note_version: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    content_json: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    plain_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    reason: Mapped[str] = mapped_column(String(40), nullable=False, default="edit")
    created_at: Mapped[datetime] = mapped_column(
        TZDateTime(), nullable=False, default=utcnow, server_default=func.now()
    )


class CollaboratorRole(enum.StrEnum):
    viewer = "viewer"
    editor = "editor"


class NoteCollaborator(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Someone besides the owner who may open (and, as editor, change) a note. Invitations are
    by email; `user_id` is filled once the address matches an account in the workspace."""

    __tablename__ = "note_collaborators"
    __table_args__ = (
        UniqueConstraint("note_id", "email", name="uq_note_collaborators_note_email"),
    )

    note_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("notes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    role: Mapped[CollaboratorRole] = mapped_column(
        Enum(CollaboratorRole, name="collaborator_role"),
        nullable=False,
        default=CollaboratorRole.viewer,
    )
    invited_by: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # The emailed link carries `invite_token`; it is single-use and expires. `accepted_at` is
    # set when the recipient opens the link signed in (signup with the invited address also
    # binds `user_id`, so access never depends on the email arriving).
    invite_token: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    invite_expires_at: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)
    invited_at: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)
    accepted_at: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)

    note: Mapped[Note] = relationship(back_populates="collaborators")
