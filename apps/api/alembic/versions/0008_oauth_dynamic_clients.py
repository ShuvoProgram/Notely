"""remote MCP OAuth: dynamically registered clients (RFC 7591), one per authorization server

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-20 18:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    op.create_table(
        "oauth_dynamic_clients",
        sa.Column("issuer", sa.String(length=500), nullable=False),
        sa.Column("server_url", sa.String(length=500), nullable=False),
        sa.Column("client_id", sa.String(length=500), nullable=False),
        sa.Column("client_secret_encrypted", sa.Text(), nullable=True),
        sa.Column("redirect_uris", JSON, nullable=False),
        sa.Column("metadata", JSON, nullable=False),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("issuer", name="uq_oauth_dynamic_clients_issuer"),
    )


def downgrade() -> None:
    op.drop_table("oauth_dynamic_clients")
