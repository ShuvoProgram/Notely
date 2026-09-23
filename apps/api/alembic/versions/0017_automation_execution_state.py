"""persist automation execution steps and approvals

Revision ID: 0017
Revises: 0016
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "automation_executions",
        sa.Column("run_mode", sa.String(length=20), nullable=False, server_default="scheduled"),
    )
    op.add_column("automation_executions", sa.Column("idempotency_key", sa.String(length=100)))
    op.add_column(
        "automation_executions",
        sa.Column("context", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )
    op.create_index(
        "ix_automation_execution_idempotency",
        "automation_executions",
        ["automation_id", "idempotency_key"],
        unique=True,
    )
    op.create_table(
        "automation_execution_steps",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "execution_id",
            sa.Uuid(),
            sa.ForeignKey("automation_executions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("step_id", sa.String(length=64), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("input", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("execution_id", "step_id", name="uq_automation_execution_step"),
    )
    op.create_index(
        "ix_automation_execution_steps_execution", "automation_execution_steps", ["execution_id"]
    )
    op.create_table(
        "automation_approvals",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "execution_id",
            sa.Uuid(),
            sa.ForeignKey("automation_executions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("step_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("proposal", sa.JSON(), nullable=False),
        sa.Column("decision", sa.JSON(), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("execution_id", "step_id", name="uq_automation_approval_step"),
    )
    op.create_index("ix_automation_approvals_execution", "automation_approvals", ["execution_id"])


def downgrade() -> None:
    op.drop_table("automation_approvals")
    op.drop_table("automation_execution_steps")
    op.drop_index("ix_automation_execution_idempotency", table_name="automation_executions")
    op.drop_column("automation_executions", "context")
    op.drop_column("automation_executions", "idempotency_key")
    op.drop_column("automation_executions", "run_mode")
