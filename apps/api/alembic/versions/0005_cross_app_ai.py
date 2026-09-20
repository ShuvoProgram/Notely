"""cross-app AI: run plans and tool-call verification

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-20 00:10:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    op.add_column("ai_runs", sa.Column("plan", JSON, nullable=True))
    op.add_column(
        "ai_runs", sa.Column("sources", JSON, nullable=False, server_default=sa.text("'[]'"))
    )
    op.add_column("ai_tool_calls", sa.Column("verification", JSON, nullable=True))


def downgrade() -> None:
    op.drop_column("ai_tool_calls", "verification")
    op.drop_column("ai_runs", "sources")
    op.drop_column("ai_runs", "plan")
