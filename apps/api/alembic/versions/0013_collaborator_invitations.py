"""collaborators: invitation tokens, expiry, acceptance

Revision ID: 0013
Revises: 0012
Create Date: 2026-09-21 18:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "note_collaborators", sa.Column("invite_token", sa.String(length=64), nullable=True)
    )
    op.add_column(
        "note_collaborators",
        sa.Column("invite_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "note_collaborators",
        sa.Column("invited_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "note_collaborators",
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_note_collaborators_invite_token", "note_collaborators", ["invite_token"], unique=True
    )


def downgrade() -> None:
    op.drop_index("ix_note_collaborators_invite_token", table_name="note_collaborators")
    op.drop_column("note_collaborators", "accepted_at")
    op.drop_column("note_collaborators", "invited_at")
    op.drop_column("note_collaborators", "invite_expires_at")
    op.drop_column("note_collaborators", "invite_token")
