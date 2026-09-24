"""concurrent AI conversations

- `ai_threads.last_activity_at`: sort key for the conversation list (messages and runs move a
  thread up; renaming or archiving does not). Backfilled from `updated_at`.
- `uq_ai_runs_thread_open`: at most one open (queued / running / waiting for approval) run per
  thread, so concurrent sends to one conversation cannot both start. Older duplicate open runs
  (left behind by crashes) are closed as failed first.

Revision ID: 0020
Revises: 0019
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OPEN = "status IN ('queued', 'running', 'waiting_for_approval')"


def upgrade() -> None:
    op.add_column(
        "ai_threads",
        sa.Column(
            "last_activity_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.execute("UPDATE ai_threads SET last_activity_at = updated_at")
    op.create_index("ix_ai_threads_user_activity", "ai_threads", ["user_id", "last_activity_at"])
    op.execute(
        f"""
        UPDATE ai_runs SET status = 'failed', error = 'interrupted', completed_at = now()
        WHERE {OPEN} AND id NOT IN (
            SELECT DISTINCT ON (thread_id) id FROM ai_runs
            WHERE {OPEN}
            ORDER BY thread_id, created_at DESC
        )
        """
    )
    op.create_index(
        "uq_ai_runs_thread_open",
        "ai_runs",
        ["thread_id"],
        unique=True,
        postgresql_where=sa.text(OPEN),
    )


def downgrade() -> None:
    op.drop_index("uq_ai_runs_thread_open", table_name="ai_runs")
    op.drop_index("ix_ai_threads_user_activity", table_name="ai_threads")
    op.drop_column("ai_threads", "last_activity_at")
