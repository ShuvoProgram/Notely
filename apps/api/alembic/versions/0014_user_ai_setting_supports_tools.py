"""user AI settings: whether the endpoint can call tools

Revision ID: 0014
Revises: 0013
Create Date: 2026-09-21 20:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("user_ai_settings", sa.Column("supports_tools", sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column("user_ai_settings", "supports_tools")
