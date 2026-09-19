"""notes: folders, tags, notes, note_tags, full-text search

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-19
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _scoped_columns() -> list[sa.Column]:
    return [
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
    ]


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "folders",
        *_scoped_columns(),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column(
            "parent_id", sa.Uuid(), sa.ForeignKey("folders.id", ondelete="CASCADE"), nullable=True
        ),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        *_timestamps(),
        sa.UniqueConstraint("user_id", "parent_id", "name", name="uq_folders_user_parent_name"),
    )
    op.create_index("ix_folders_tenant_id", "folders", ["tenant_id"])
    op.create_index("ix_folders_user_id", "folders", ["user_id"])
    op.create_index("ix_folders_parent_id", "folders", ["parent_id"])

    op.create_table(
        "tags",
        *_scoped_columns(),
        sa.Column("name", sa.String(length=60), nullable=False),
        sa.Column("color", sa.String(length=7), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint("user_id", "name", name="uq_tags_user_name"),
    )
    op.create_index("ix_tags_tenant_id", "tags", ["tenant_id"])
    op.create_index("ix_tags_user_id", "tags", ["user_id"])

    op.create_table(
        "notes",
        *_scoped_columns(),
        sa.Column("title", sa.String(length=300), nullable=False, server_default=""),
        sa.Column("content_json", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("plain_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "folder_id", sa.Uuid(), sa.ForeignKey("folders.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("is_favorite", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
    )
    op.create_index("ix_notes_tenant_id", "notes", ["tenant_id"])
    op.create_index("ix_notes_user_id", "notes", ["user_id"])
    op.create_index("ix_notes_folder_id", "notes", ["folder_id"])
    op.create_index("ix_notes_deleted_at", "notes", ["deleted_at"])
    op.create_index("ix_notes_user_updated", "notes", ["user_id", sa.text("updated_at DESC")])

    # Full-text search: generated tsvector over title (weight A) + body (weight B).
    op.execute(
        """
        ALTER TABLE notes ADD COLUMN search_vector tsvector
        GENERATED ALWAYS AS (
            setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
            setweight(to_tsvector('english', coalesce(plain_text, '')), 'B')
        ) STORED
        """
    )
    op.execute("CREATE INDEX ix_notes_search_vector ON notes USING GIN (search_vector)")

    op.create_table(
        "note_tags",
        sa.Column(
            "note_id", sa.Uuid(), sa.ForeignKey("notes.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column(
            "tag_id", sa.Uuid(), sa.ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
    )
    op.create_index("ix_note_tags_user_id", "note_tags", ["user_id"])


def downgrade() -> None:
    op.drop_table("note_tags")
    op.drop_table("notes")
    op.drop_table("tags")
    op.drop_table("folders")
