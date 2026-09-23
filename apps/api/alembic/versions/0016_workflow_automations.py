"""add generic workflow automation action

Revision ID: 0016
Revises: 0015
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE automation_action ADD VALUE IF NOT EXISTS 'workflow'")


def downgrade() -> None:
    # PostgreSQL enum values cannot be removed safely without rebuilding the type.
    pass
