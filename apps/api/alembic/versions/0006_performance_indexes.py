"""performance: composite indexes for the hot per-user listings

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-20 15:00:00.000000

Every list endpoint filters by user_id and orders by a timestamp; single-column indexes on
user_id alone still force a sort. These cover the common (user_id, ordering) shapes.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# ix_notes_user_updated was already created by 0002 (as user_id, updated_at DESC); creating it
# again here broke every fresh database. It is left to 0002.
INDEXES: list[tuple[str, str, list[str]]] = [
    ("ix_tasks_user_status_created", "tasks", ["user_id", "status", "created_at"]),
    ("ix_ai_threads_user_updated", "ai_threads", ["user_id", "updated_at"]),
    ("ix_ai_runs_user_created", "ai_runs", ["user_id", "created_at"]),
    ("ix_ai_runs_thread_status", "ai_runs", ["thread_id", "status"]),
    ("ix_ai_messages_thread_created", "ai_messages", ["thread_id", "created_at"]),
    ("ix_audit_events_user_created", "audit_events", ["user_id", "created_at"]),
]


def upgrade() -> None:
    for name, table, columns in INDEXES:
        op.create_index(name, table, columns, unique=False, if_not_exists=True)


def downgrade() -> None:
    for name, table, _ in reversed(INDEXES):
        op.drop_index(name, table_name=table, if_exists=True)
