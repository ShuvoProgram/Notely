"""automation engine v2: step outputs, failure tracking, user templates

- Execution steps keep their full (capped) output, a plain-language summary and attempts.
- Automations track consecutive scheduled failures and have an optional description.
- `automation_templates` replaces "templates" stored as flagged automations.
- Run state no longer lives on the automation: legacy running/failed/needs_attention
  statuses become active or paused, and the due-index follows the new scheduler query.
- Legacy single-purpose actions become version 2 workflows.
- Adds the indexes the models declare but 0015–0017 did not create.

Revision ID: 0018
Revises: 0017
"""

import json
import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _legacy_workflow(action: str, config: dict, name: str) -> dict:
    if action == "create_task":
        step = {
            "kind": "action",
            "id": "create_task",
            "action": "notely.create_task",
            "inputs": {"title": str(config.get("title") or name)},
        }
        return {"version": 2, "steps": [step]}
    if action == "send_reminder":
        step = {
            "kind": "action",
            "id": "remind_me",
            "action": "notely.notify",
            "inputs": {"message": str(config.get("message") or name)},
        }
        return {"version": 2, "steps": [step]}
    # summarize_notes was never implemented; give it a real equivalent.
    return {
        "version": 2,
        "steps": [
            {"kind": "action", "id": "recent_notes", "action": "notely.find_notes", "inputs": {}},
            {
                "kind": "action",
                "id": "summary",
                "action": "ai.summarize",
                "inputs": {"data": "{{steps.recent_notes.output.notes}}"},
            },
            {
                "kind": "action",
                "id": "tell_me",
                "action": "notely.notify",
                "inputs": {"message": "{{steps.summary.output.summary}}"},
            },
        ],
    }


# Columns 0015/0017 created as JSON; the models (and every other table) use JSONB.
_JSON_COLUMNS = {
    "automations": ("action_config", "schedule_config"),
    "automation_executions": ("result", "context"),
    "automation_execution_steps": ("input", "result"),
    "automation_approvals": ("proposal", "decision"),
}


def _json() -> sa.types.TypeEngine:
    return sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        for table, columns in _JSON_COLUMNS.items():
            for column in columns:
                op.alter_column(
                    table,
                    column,
                    type_=postgresql.JSONB(),
                    postgresql_using=f"{column}::jsonb",
                )
    op.add_column("automation_execution_steps", sa.Column("output", _json(), nullable=True))
    op.add_column("automation_execution_steps", sa.Column("summary", sa.Text(), nullable=True))
    op.add_column(
        "automation_execution_steps", sa.Column("name", sa.String(length=160), nullable=True)
    )
    op.add_column(
        "automation_execution_steps",
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("automations", sa.Column("description", sa.Text(), nullable=True))
    op.add_column(
        "automations",
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_table(
        "automation_templates",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("definition", _json(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_automation_templates_tenant_id", "automation_templates", ["tenant_id"])
    op.create_index("ix_automation_templates_user_id", "automation_templates", ["user_id"])
    op.create_index("ix_automations_tenant_id", "automations", ["tenant_id"])
    op.create_index("ix_automations_user_id", "automations", ["user_id"])
    op.drop_index("ix_automations_due", table_name="automations")
    op.create_index("ix_automations_due", "automations", ["enabled", "next_run_at"])
    op.create_index(
        "ix_automation_executions_recent", "automation_executions", ["automation_id", "started_at"]
    )

    bind = op.get_bind()
    bind.execute(
        sa.text(
            "UPDATE automations SET status = CAST("
            "CASE WHEN enabled THEN 'active' ELSE 'paused' END AS automation_status) "
            "WHERE status IN ('running', 'failed', 'needs_attention')"
        )
    )
    # Runs left "running" by the old synchronous engine can never finish.
    bind.execute(
        sa.text(
            "UPDATE automation_executions SET status = 'failed', "
            "error = 'Interrupted before it finished.' WHERE status = 'running'"
        )
    )
    legacy = bind.execute(
        sa.text(
            "SELECT id, action, action_config, name FROM automations "
            "WHERE action IN ('create_task', 'send_reminder', 'summarize_notes')"
        )
    ).fetchall()
    for row in legacy:
        config = (
            row.action_config
            if isinstance(row.action_config, dict)
            else json.loads(row.action_config or "{}")
        )
        bind.execute(
            sa.text(
                "UPDATE automations SET action = 'workflow', "
                "action_config = CAST(:config AS JSON) WHERE id = :id"
            ),
            {"config": json.dumps(_legacy_workflow(row.action, config, row.name)), "id": row.id},
        )
    # "Templates" were automations flagged in their config; move them to the new table.
    flagged = bind.execute(
        sa.text(
            "SELECT id, tenant_id, user_id, name, action_config, schedule_kind, "
            "schedule_config, timezone, created_at, updated_at FROM automations"
        )
    ).fetchall()
    for row in flagged:
        config = (
            row.action_config
            if isinstance(row.action_config, dict)
            else json.loads(row.action_config or "{}")
        )
        if not config.get("is_template"):
            continue
        config.pop("is_template", None)
        schedule = (
            row.schedule_config
            if isinstance(row.schedule_config, dict)
            else json.loads(row.schedule_config or "{}")
        )
        definition = {
            "workflow": config,
            "schedule_kind": row.schedule_kind,
            "schedule_config": schedule,
            "timezone": row.timezone,
        }
        bind.execute(
            sa.text(
                "INSERT INTO automation_templates (id, tenant_id, user_id, name, definition, "
                "created_at, updated_at) VALUES (:id, :tenant, :user, :name, "
                "CAST(:definition AS JSON), :created, :updated)"
            ),
            {
                "id": uuid.uuid4(),
                "tenant": row.tenant_id,
                "user": row.user_id,
                "name": row.name,
                "definition": json.dumps(definition),
                "created": row.created_at,
                "updated": row.updated_at,
            },
        )
        bind.execute(sa.text("DELETE FROM automations WHERE id = :id"), {"id": row.id})


def downgrade() -> None:
    op.drop_index("ix_automation_executions_recent", table_name="automation_executions")
    op.drop_index("ix_automations_due", table_name="automations")
    op.create_index("ix_automations_due", "automations", ["status", "next_run_at"])
    op.drop_index("ix_automations_user_id", table_name="automations")
    op.drop_index("ix_automations_tenant_id", table_name="automations")
    op.drop_table("automation_templates")
    op.drop_column("automations", "consecutive_failures")
    op.drop_column("automations", "description")
    op.drop_column("automation_execution_steps", "attempts")
    op.drop_column("automation_execution_steps", "name")
    op.drop_column("automation_execution_steps", "summary")
    op.drop_column("automation_execution_steps", "output")
    if op.get_bind().dialect.name == "postgresql":
        for table, columns in _JSON_COLUMNS.items():
            for column in columns:
                op.alter_column(
                    table, column, type_=sa.JSON(), postgresql_using=f"{column}::json"
                )
