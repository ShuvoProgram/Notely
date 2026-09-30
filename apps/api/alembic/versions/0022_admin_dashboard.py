"""admin dashboard

- `users.role` (user | viewer | support | admin), `users.suspended_at`/`suspension_reason`,
  `users.last_active_at` (kept fresh by the sliding session; survives session cleanup).
- `admin_audit_events`: every administrative action, deployment-wide.
- `platform_events`: durable error/security/usage events (API 500s, job failures, OAuth
  failures, sign-ins, AI workflow drafts) that per-process metrics lose on restart.
- `platform_settings`: runtime settings (maintenance mode, sign-ups, AI, limits).
- Time-range indexes for the admin analytics.

Revision ID: 0022
Revises: 0021
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
TS = sa.DateTime(timezone=True)

ANALYTICS_INDEXES = [
    ("ix_users_created_at", "users", ["created_at"]),
    ("ix_notes_created_at", "notes", ["created_at"]),
    ("ix_tasks_created_at", "tasks", ["created_at"]),
    ("ix_ai_runs_created_at", "ai_runs", ["created_at"]),
    ("ix_ai_tool_calls_created_at", "ai_tool_calls", ["created_at"]),
    ("ix_automation_executions_started_at", "automation_executions", ["started_at"]),
    ("ix_automation_executions_status_started", "automation_executions", ["status", "started_at"]),
]


def upgrade() -> None:
    op.add_column("users", sa.Column("role", sa.String(20), nullable=False, server_default="user"))
    op.add_column("users", sa.Column("last_active_at", TS, nullable=True))
    op.add_column("users", sa.Column("suspended_at", TS, nullable=True))
    op.add_column("users", sa.Column("suspension_reason", sa.String(500), nullable=True))
    op.create_index("ix_users_role", "users", ["role"])
    op.create_index("ix_users_last_active_at", "users", ["last_active_at"])
    # Seed activity from the newest session so "last active" is meaningful from day one.
    op.execute(
        "UPDATE users SET last_active_at = s.seen FROM "
        "(SELECT user_id, max(last_seen_at) AS seen FROM user_sessions GROUP BY user_id) s "
        "WHERE s.user_id = users.id"
    )
    op.execute("UPDATE users SET suspended_at = updated_at WHERE is_active = false")

    op.create_table(
        "admin_audit_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "actor_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("actor_email", sa.String(320), nullable=True),
        sa.Column("actor_role", sa.String(20), nullable=True),
        sa.Column("action", sa.String(80), nullable=False),
        sa.Column("resource_type", sa.String(40), nullable=True),
        sa.Column("resource_id", sa.String(80), nullable=True),
        sa.Column("resource_label", sa.String(320), nullable=True),
        sa.Column("result", sa.String(20), nullable=False),
        sa.Column("ip_address", sa.String(64), nullable=True),
        sa.Column("user_agent", sa.String(512), nullable=True),
        sa.Column("request_id", sa.String(64), nullable=True),
        sa.Column("metadata", JSON, nullable=False),
        sa.Column("created_at", TS, nullable=False),
    )
    op.create_index("ix_admin_audit_events_actor_id", "admin_audit_events", ["actor_id"])
    op.create_index("ix_admin_audit_events_created", "admin_audit_events", ["created_at"])
    op.create_index(
        "ix_admin_audit_events_action_created", "admin_audit_events", ["action", "created_at"]
    )
    op.create_index(
        "ix_admin_audit_events_resource", "admin_audit_events", ["resource_type", "resource_id"]
    )

    op.create_table(
        "platform_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("category", sa.String(20), nullable=False),
        sa.Column("kind", sa.String(60), nullable=False),
        sa.Column("source", sa.String(160), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("metadata", JSON, nullable=False),
        sa.Column("occurred_at", TS, nullable=False),
    )
    op.create_index("ix_platform_events_occurred", "platform_events", ["occurred_at"])
    op.create_index("ix_platform_events_kind_occurred", "platform_events", ["kind", "occurred_at"])
    op.create_index(
        "ix_platform_events_category_occurred", "platform_events", ["category", "occurred_at"]
    )
    op.create_index(
        "ix_platform_events_user_occurred", "platform_events", ["user_id", "occurred_at"]
    )

    op.create_table(
        "platform_settings",
        sa.Column("key", sa.String(60), primary_key=True),
        sa.Column("value", JSON, nullable=True),
        sa.Column(
            "updated_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("updated_at", TS, nullable=False),
    )

    for name, table, columns in ANALYTICS_INDEXES:
        op.create_index(name, table, columns, if_not_exists=True)


def downgrade() -> None:
    for name, table, _ in ANALYTICS_INDEXES:
        op.drop_index(name, table_name=table, if_exists=True)
    op.drop_table("platform_settings")
    op.drop_table("platform_events")
    op.drop_table("admin_audit_events")
    op.drop_index("ix_users_last_active_at", table_name="users")
    op.drop_index("ix_users_role", table_name="users")
    op.drop_column("users", "suspension_reason")
    op.drop_column("users", "suspended_at")
    op.drop_column("users", "last_active_at")
    op.drop_column("users", "role")
