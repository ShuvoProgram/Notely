"""action journal: reversible AI / automation changes

- `action_records`: one row per change an AI run or automation run made, with before/after
  state and how to reverse it.
- `batch_reverts`: one per reverted batch (unique), so a revert can't run twice.

Revision ID: 0023
Revises: 0022
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
TS = sa.DateTime(timezone=True)


def _scoped() -> list[sa.Column]:  # type: ignore[type-arg]
    return [
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "action_records",
        *_scoped(),
        sa.Column("batch_kind", sa.String(20), nullable=False),
        sa.Column("batch_id", sa.Uuid(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("source_ref", sa.String(120), nullable=True),
        sa.Column("provider", sa.String(60), nullable=False),
        sa.Column("kind", sa.String(80), nullable=False),
        sa.Column("resource_type", sa.String(40), nullable=False),
        sa.Column("resource_id", sa.String(255), nullable=True),
        sa.Column("label", sa.String(300), nullable=False),
        sa.Column("before", JSON, nullable=True),
        sa.Column("after", JSON, nullable=True),
        sa.Column("revert_ref", JSON, nullable=True),
        sa.Column("reversible", sa.Boolean(), nullable=False),
        sa.Column("irreversible_reason", sa.String(300), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("revert_note", sa.Text(), nullable=True),
        sa.Column("revert_attempts", sa.Integer(), nullable=False),
        sa.Column("reverted_at", TS, nullable=True),
        sa.Column("created_at", TS, nullable=False),
    )
    op.create_index("ix_action_records_tenant_id", "action_records", ["tenant_id"])
    op.create_index("ix_action_records_user_id", "action_records", ["user_id"])
    op.create_index("ix_action_records_batch", "action_records", ["batch_kind", "batch_id", "sequence"])
    op.create_index("ix_action_records_user_created", "action_records", ["user_id", "created_at"])

    op.create_table(
        "batch_reverts",
        *_scoped(),
        sa.Column("batch_kind", sa.String(20), nullable=False),
        sa.Column("batch_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("requested_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("summary", JSON, nullable=False),
        sa.Column("requested_at", TS, nullable=False),
        sa.Column("finished_at", TS, nullable=True),
        sa.UniqueConstraint("batch_kind", "batch_id", name="uq_batch_reverts_batch"),
    )
    op.create_index("ix_batch_reverts_tenant_id", "batch_reverts", ["tenant_id"])
    op.create_index("ix_batch_reverts_user_id", "batch_reverts", ["user_id"])


def downgrade() -> None:
    op.drop_table("batch_reverts")
    op.drop_table("action_records")
