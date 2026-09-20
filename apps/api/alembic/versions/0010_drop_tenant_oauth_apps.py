"""vendor OAuth apps are deployment configuration again (in-app setup removed)

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-20 20:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("ix_tenant_oauth_apps_tenant_id", table_name="tenant_oauth_apps")
    op.drop_table("tenant_oauth_apps")


def downgrade() -> None:
    op.create_table(
        "tenant_oauth_apps",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("prefix", sa.String(length=40), nullable=False),
        sa.Column("client_id", sa.String(length=500), nullable=False),
        sa.Column("client_secret_encrypted", sa.Text(), nullable=False),
        sa.Column("configured_by", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "prefix", name="uq_tenant_oauth_apps"),
    )
    op.create_index("ix_tenant_oauth_apps_tenant_id", "tenant_oauth_apps", ["tenant_id"])
