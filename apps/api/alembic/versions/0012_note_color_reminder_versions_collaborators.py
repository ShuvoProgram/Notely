"""notes: colour, reminder, version history, collaborators

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-21 16:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "notes",
        sa.Column("color", sa.String(length=20), nullable=False, server_default="default"),
    )
    op.add_column("notes", sa.Column("reminder_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_notes_reminder_at", "notes", ["reminder_at"])

    op.create_table(
        "note_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("note_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("note_version", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("content_json", postgresql.JSONB(), nullable=False),
        sa.Column("plain_text", sa.Text(), nullable=False),
        sa.Column("reason", sa.String(length=40), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["note_id"], ["notes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_note_versions_note_id", "note_versions", ["note_id"])
    op.create_index("ix_note_versions_note_created", "note_versions", ["note_id", "created_at"])

    sa.Enum("viewer", "editor", name="collaborator_role").create(op.get_bind(), checkfirst=True)
    collaborator_role = postgresql.ENUM(
        "viewer", "editor", name="collaborator_role", create_type=False
    )
    op.create_table(
        "note_collaborators",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("note_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("role", collaborator_role, nullable=False),
        sa.Column("invited_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["note_id"], ["notes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["invited_by"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("note_id", "email", name="uq_note_collaborators_note_email"),
    )
    op.create_index("ix_note_collaborators_note_id", "note_collaborators", ["note_id"])
    op.create_index("ix_note_collaborators_user_id", "note_collaborators", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_note_collaborators_user_id", table_name="note_collaborators")
    op.drop_index("ix_note_collaborators_note_id", table_name="note_collaborators")
    op.drop_table("note_collaborators")
    sa.Enum(name="collaborator_role").drop(op.get_bind(), checkfirst=True)
    op.drop_index("ix_note_versions_note_created", table_name="note_versions")
    op.drop_index("ix_note_versions_note_id", table_name="note_versions")
    op.drop_table("note_versions")
    op.drop_index("ix_notes_reminder_at", table_name="notes")
    op.drop_column("notes", "reminder_at")
    op.drop_column("notes", "color")
