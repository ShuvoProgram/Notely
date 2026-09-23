"""automations and encrypted TOTP state

Revision ID: 0015
Revises: 0014
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("totp_secret_encrypted", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("totp_pending_secret_encrypted", sa.Text(), nullable=True))
    op.add_column(
        "users", sa.Column("totp_pending_expires_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "user_sessions",
        sa.Column("two_factor_verified_at", sa.DateTime(timezone=True), nullable=True),
    )
    action_type = sa.Enum(
        "create_task", "send_reminder", "summarize_notes", name="automation_action"
    )
    status_type = sa.Enum(
        "active",
        "paused",
        "running",
        "completed",
        "failed",
        "needs_attention",
        name="automation_status",
    )
    op.create_table(
        "automations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("action", action_type, nullable=False),
        sa.Column("action_config", sa.JSON(), nullable=False),
        sa.Column("schedule_kind", sa.String(20), nullable=False),
        sa.Column("schedule_config", sa.JSON(), nullable=False),
        sa.Column("timezone", sa.String(60), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True)),
        sa.Column("ends_at", sa.DateTime(timezone=True)),
        sa.Column("next_run_at", sa.DateTime(timezone=True)),
        sa.Column("status", status_type, nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_automations_due", "automations", ["status", "next_run_at"])
    op.create_table(
        "automation_executions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "automation_id",
            sa.Uuid(),
            sa.ForeignKey("automations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("occurrence_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("automation_id", "occurrence_at", name="uq_automation_occurrence"),
    )


def downgrade() -> None:
    op.drop_table("automation_executions")
    op.drop_index("ix_automations_due", table_name="automations")
    op.drop_table("automations")
    sa.Enum(name="automation_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="automation_action").drop(op.get_bind(), checkfirst=True)
    op.drop_column("user_sessions", "two_factor_verified_at")
    op.drop_column("users", "totp_pending_expires_at")
    op.drop_column("users", "totp_pending_secret_encrypted")
    op.drop_column("users", "totp_secret_encrypted")
