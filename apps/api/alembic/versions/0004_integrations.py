"""integrations: catalog, user connections, external items, webhook events

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-19 21:50:11.138865
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "integrations",
        sa.Column("provider", sa.String(length=60), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("category", sa.String(length=60), nullable=False),
        sa.Column("logo_url", sa.String(length=2048), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_integrations")),
        sa.UniqueConstraint("provider", name=op.f("uq_integrations_provider")),
    )
    op.create_table(
        "webhook_events",
        sa.Column("provider", sa.String(length=60), nullable=False),
        sa.Column("event_id", sa.String(length=255), nullable=False),
        sa.Column("event_type", sa.String(length=120), nullable=True),
        sa.Column("connection_id", sa.Uuid(), nullable=True),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "payload",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_webhook_events")),
        sa.UniqueConstraint("provider", "event_id", name="uq_webhook_events_provider_event"),
    )
    op.create_index(
        op.f("ix_webhook_events_connection_id"), "webhook_events", ["connection_id"], unique=False
    )
    op.create_index(
        op.f("ix_webhook_events_provider"), "webhook_events", ["provider"], unique=False
    )
    op.create_index(op.f("ix_webhook_events_status"), "webhook_events", ["status"], unique=False)
    op.create_table(
        "user_connections",
        sa.Column("integration_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=60), nullable=False),
        sa.Column("auth_type", sa.String(length=20), nullable=False),
        sa.Column("external_account_id", sa.String(length=255), nullable=True),
        sa.Column("external_account_name", sa.String(length=255), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "connecting",
                "connected",
                "syncing",
                "needs_attention",
                "expired",
                "error",
                "disconnected",
                name="connection_status",
            ),
            nullable=False,
        ),
        sa.Column("access_token_encrypted", sa.Text(), nullable=True),
        sa.Column("refresh_token_encrypted", sa.Text(), nullable=True),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "scopes",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "config",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "metadata",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("last_error_code", sa.String(length=60), nullable=True),
        sa.Column("disconnected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["integration_id"],
            ["integrations.id"],
            name=op.f("fk_user_connections_integration_id_integrations"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_user_connections_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_connections_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_connections")),
        sa.UniqueConstraint("user_id", "provider", name="uq_user_connections_user_provider"),
    )
    op.create_index(
        op.f("ix_user_connections_integration_id"),
        "user_connections",
        ["integration_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_user_connections_provider"), "user_connections", ["provider"], unique=False
    )
    op.create_index(
        op.f("ix_user_connections_status"), "user_connections", ["status"], unique=False
    )
    op.create_index(
        op.f("ix_user_connections_tenant_id"), "user_connections", ["tenant_id"], unique=False
    )
    op.create_index(
        op.f("ix_user_connections_user_id"), "user_connections", ["user_id"], unique=False
    )
    op.create_table(
        "external_items",
        sa.Column("connection_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=60), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("kind", sa.String(length=60), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=True),
        sa.Column("content_text", sa.Text(), nullable=False),
        sa.Column(
            "metadata",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["connection_id"],
            ["user_connections.id"],
            name=op.f("fk_external_items_connection_id_user_connections"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_external_items_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_external_items_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_external_items")),
        sa.UniqueConstraint(
            "connection_id", "external_id", name="uq_external_items_connection_external"
        ),
    )
    op.create_index(
        op.f("ix_external_items_connection_id"), "external_items", ["connection_id"], unique=False
    )
    op.create_index(
        op.f("ix_external_items_provider"), "external_items", ["provider"], unique=False
    )
    op.create_index(
        op.f("ix_external_items_tenant_id"), "external_items", ["tenant_id"], unique=False
    )
    op.create_index(op.f("ix_external_items_user_id"), "external_items", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_external_items_user_id"), table_name="external_items")
    op.drop_index(op.f("ix_external_items_tenant_id"), table_name="external_items")
    op.drop_index(op.f("ix_external_items_provider"), table_name="external_items")
    op.drop_index(op.f("ix_external_items_connection_id"), table_name="external_items")
    op.drop_table("external_items")
    op.drop_index(op.f("ix_user_connections_user_id"), table_name="user_connections")
    op.drop_index(op.f("ix_user_connections_tenant_id"), table_name="user_connections")
    op.drop_index(op.f("ix_user_connections_status"), table_name="user_connections")
    op.drop_index(op.f("ix_user_connections_provider"), table_name="user_connections")
    op.drop_index(op.f("ix_user_connections_integration_id"), table_name="user_connections")
    op.drop_table("user_connections")
    op.drop_index(op.f("ix_webhook_events_status"), table_name="webhook_events")
    op.drop_index(op.f("ix_webhook_events_provider"), table_name="webhook_events")
    op.drop_index(op.f("ix_webhook_events_connection_id"), table_name="webhook_events")
    op.drop_table("webhook_events")
    op.drop_table("integrations")
    sa.Enum(name="connection_status").drop(op.get_bind(), checkfirst=True)
