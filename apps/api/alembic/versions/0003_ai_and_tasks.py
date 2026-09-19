"""ai and tasks: tasks, ai threads/messages/runs/tool calls/approvals, audit, preferences

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-19 20:44:12.434777
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


RISK_LEVEL = postgresql.ENUM(
    "read",
    "write",
    "external_communication",
    "destructive",
    name="ai_risk_level",
    create_type=False,
)


def upgrade() -> None:
    RISK_LEVEL.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "audit_events",
        sa.Column("connection_id", sa.Uuid(), nullable=True),
        sa.Column("provider", sa.String(length=60), nullable=False),
        sa.Column("action", sa.String(length=120), nullable=False),
        sa.Column("tool_name", sa.String(length=120), nullable=True),
        sa.Column(
            "risk_level",
            RISK_LEVEL,
            nullable=False,
        ),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=True),
        sa.Column(
            "request_metadata",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "result_metadata",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_audit_events_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_audit_events_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_events")),
    )
    op.create_index(
        op.f("ix_audit_events_created_at"), "audit_events", ["created_at"], unique=False
    )
    op.create_index(op.f("ix_audit_events_run_id"), "audit_events", ["run_id"], unique=False)
    op.create_index(op.f("ix_audit_events_tenant_id"), "audit_events", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_audit_events_user_id"), "audit_events", ["user_id"], unique=False)
    op.create_table(
        "ai_threads",
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("note_id", sa.Uuid(), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
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
            ["note_id"], ["notes.id"], name=op.f("fk_ai_threads_note_id_notes"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_ai_threads_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_ai_threads_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_threads")),
    )
    op.create_index(op.f("ix_ai_threads_note_id"), "ai_threads", ["note_id"], unique=False)
    op.create_index(op.f("ix_ai_threads_tenant_id"), "ai_threads", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_ai_threads_user_id"), "ai_threads", ["user_id"], unique=False)
    op.create_table(
        "tasks",
        sa.Column("note_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column(
            "priority",
            sa.Enum("none", "low", "medium", "high", name="task_priority"),
            nullable=False,
        ),
        sa.Column("status", sa.Enum("open", "done", name="task_status"), nullable=False),
        sa.Column("source", sa.Enum("manual", "ai", name="task_source"), nullable=False),
        sa.Column("external_provider", sa.String(length=60), nullable=True),
        sa.Column("external_task_id", sa.String(length=255), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
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
            ["note_id"], ["notes.id"], name=op.f("fk_tasks_note_id_notes"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_tasks_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_tasks_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tasks")),
    )
    op.create_index(op.f("ix_tasks_note_id"), "tasks", ["note_id"], unique=False)
    op.create_index(op.f("ix_tasks_status"), "tasks", ["status"], unique=False)
    op.create_index(op.f("ix_tasks_tenant_id"), "tasks", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_tasks_user_id"), "tasks", ["user_id"], unique=False)
    op.create_table(
        "ai_runs",
        sa.Column("thread_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "queued",
                "running",
                "waiting_for_approval",
                "completed",
                "failed",
                "cancelled",
                name="ai_run_status",
            ),
            nullable=False,
        ),
        sa.Column("model", sa.String(length=120), nullable=True),
        sa.Column("provider", sa.String(length=60), nullable=True),
        sa.Column(
            "token_usage",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("cost_usd", sa.Numeric(precision=12, scale=6), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "steps",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_ai_runs_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["thread_id"],
            ["ai_threads.id"],
            name=op.f("fk_ai_runs_thread_id_ai_threads"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_ai_runs_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_runs")),
    )
    op.create_index(op.f("ix_ai_runs_status"), "ai_runs", ["status"], unique=False)
    op.create_index(op.f("ix_ai_runs_tenant_id"), "ai_runs", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_ai_runs_thread_id"), "ai_runs", ["thread_id"], unique=False)
    op.create_index(op.f("ix_ai_runs_user_id"), "ai_runs", ["user_id"], unique=False)
    op.create_table(
        "ai_approvals",
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("pending", "approved", "rejected", "expired", name="ai_approval_status"),
            nullable=False,
        ),
        sa.Column(
            "tool_call_ids",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "decision",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["ai_runs.id"],
            name=op.f("fk_ai_approvals_run_id_ai_runs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_ai_approvals_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_ai_approvals_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_approvals")),
    )
    op.create_index(op.f("ix_ai_approvals_run_id"), "ai_approvals", ["run_id"], unique=False)
    op.create_index(op.f("ix_ai_approvals_tenant_id"), "ai_approvals", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_ai_approvals_user_id"), "ai_approvals", ["user_id"], unique=False)
    op.create_table(
        "ai_messages",
        sa.Column("thread_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=True),
        sa.Column(
            "role",
            sa.Enum("user", "assistant", "tool", "system", name="ai_message_role"),
            nullable=False,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "tool_calls",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
        sa.Column("tool_call_id", sa.String(length=120), nullable=True),
        sa.Column(
            "sources",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["ai_runs.id"],
            name=op.f("fk_ai_messages_run_id_ai_runs"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_ai_messages_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["thread_id"],
            ["ai_threads.id"],
            name=op.f("fk_ai_messages_thread_id_ai_threads"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_ai_messages_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_messages")),
    )
    op.create_index(op.f("ix_ai_messages_tenant_id"), "ai_messages", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_ai_messages_thread_id"), "ai_messages", ["thread_id"], unique=False)
    op.create_index(op.f("ix_ai_messages_user_id"), "ai_messages", ["user_id"], unique=False)
    op.create_table(
        "ai_tool_calls",
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("call_id", sa.String(length=120), nullable=False),
        sa.Column("tool_name", sa.String(length=120), nullable=False),
        sa.Column("provider", sa.String(length=60), nullable=False),
        sa.Column(
            "risk_level",
            RISK_LEVEL,
            nullable=False,
        ),
        sa.Column(
            "arguments",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "result",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "proposed", "approved", "rejected", "executed", "failed", name="ai_tool_call_status"
            ),
            nullable=False,
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["ai_runs.id"],
            name=op.f("fk_ai_tool_calls_run_id_ai_runs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_ai_tool_calls_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_ai_tool_calls_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_tool_calls")),
    )
    op.create_index(op.f("ix_ai_tool_calls_run_id"), "ai_tool_calls", ["run_id"], unique=False)
    op.create_index(
        op.f("ix_ai_tool_calls_tenant_id"), "ai_tool_calls", ["tenant_id"], unique=False
    )
    op.create_index(op.f("ix_ai_tool_calls_user_id"), "ai_tool_calls", ["user_id"], unique=False)
    op.add_column(
        "users",
        sa.Column(
            "preferences",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "preferences")
    op.drop_index(op.f("ix_ai_tool_calls_user_id"), table_name="ai_tool_calls")
    op.drop_index(op.f("ix_ai_tool_calls_tenant_id"), table_name="ai_tool_calls")
    op.drop_index(op.f("ix_ai_tool_calls_run_id"), table_name="ai_tool_calls")
    op.drop_table("ai_tool_calls")
    op.drop_index(op.f("ix_ai_messages_user_id"), table_name="ai_messages")
    op.drop_index(op.f("ix_ai_messages_thread_id"), table_name="ai_messages")
    op.drop_index(op.f("ix_ai_messages_tenant_id"), table_name="ai_messages")
    op.drop_table("ai_messages")
    op.drop_index(op.f("ix_ai_approvals_user_id"), table_name="ai_approvals")
    op.drop_index(op.f("ix_ai_approvals_tenant_id"), table_name="ai_approvals")
    op.drop_index(op.f("ix_ai_approvals_run_id"), table_name="ai_approvals")
    op.drop_table("ai_approvals")
    op.drop_index(op.f("ix_ai_runs_user_id"), table_name="ai_runs")
    op.drop_index(op.f("ix_ai_runs_thread_id"), table_name="ai_runs")
    op.drop_index(op.f("ix_ai_runs_tenant_id"), table_name="ai_runs")
    op.drop_index(op.f("ix_ai_runs_status"), table_name="ai_runs")
    op.drop_table("ai_runs")
    op.drop_index(op.f("ix_tasks_user_id"), table_name="tasks")
    op.drop_index(op.f("ix_tasks_tenant_id"), table_name="tasks")
    op.drop_index(op.f("ix_tasks_status"), table_name="tasks")
    op.drop_index(op.f("ix_tasks_note_id"), table_name="tasks")
    op.drop_table("tasks")
    op.drop_index(op.f("ix_ai_threads_user_id"), table_name="ai_threads")
    op.drop_index(op.f("ix_ai_threads_tenant_id"), table_name="ai_threads")
    op.drop_index(op.f("ix_ai_threads_note_id"), table_name="ai_threads")
    op.drop_table("ai_threads")
    op.drop_index(op.f("ix_audit_events_user_id"), table_name="audit_events")
    op.drop_index(op.f("ix_audit_events_tenant_id"), table_name="audit_events")
    op.drop_index(op.f("ix_audit_events_run_id"), table_name="audit_events")
    op.drop_index(op.f("ix_audit_events_created_at"), table_name="audit_events")
    op.drop_table("audit_events")
    for enum_name in (
        "ai_risk_level",
        "ai_tool_call_status",
        "ai_approval_status",
        "ai_message_role",
        "ai_run_status",
        "task_priority",
        "task_status",
        "task_source",
    ):
        sa.Enum(name=enum_name).drop(op.get_bind(), checkfirst=True)
