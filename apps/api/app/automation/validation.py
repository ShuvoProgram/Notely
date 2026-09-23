"""Checks that need the user's catalog: does each action exist and is it connected, are the
required inputs filled, do chosen notes still exist.

Drafts may be saved with issues; an automation can only be switched on without them.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass
from typing import Any, Literal

from app.automation.actions import ActionContext
from app.automation.catalog import Catalog
from app.automation.engine import app_name
from app.automation.mapping import is_blank
from app.automation.model import ActionStep, Workflow, iter_steps
from app.core.exceptions import APIError
from app.integrations.registry import get_providers
from app.services.note_service import NoteService


@dataclass
class Issue:
    message: str
    step_id: str | None = None
    field: str | None = None
    kind: Literal["fix", "connect", "unsupported"] = "fix"
    app: str | None = None
    fix_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


def normalise(workflow: Workflow, catalog: Catalog) -> Workflow:
    """Server-side safety rules the UI or an AI draft can't override."""
    for step in iter_steps(workflow.steps):
        if isinstance(step, ActionStep):
            action = catalog.get(step.action)
            if action is not None and action.safety == "always_ask":
                step.approval = "ask"
    return workflow


async def validate(ctx: ActionContext, workflow: Workflow, catalog: Catalog) -> list[Issue]:
    issues: list[Issue] = []
    actions = [s for s in iter_steps(workflow.steps) if isinstance(s, ActionStep) and s.enabled]
    if not actions:
        issues.append(Issue("Add at least one step that does something."))
    notes = NoteService(ctx.db)
    for step in actions:
        action = catalog.get(step.action)
        app_id = step.action.split(".", 1)[0]
        if action is None:
            provider = get_providers().get(app_id)
            if provider is None or app_id in ("notely", "ai"):
                issues.append(
                    Issue(
                        "Notely can't do this step. Choose another action.",
                        step_id=step.id,
                        kind="unsupported",
                    )
                )
                continue
            app = next((a for a in catalog.apps if a["id"] == app_id), None)
            connected = bool(app and app.get("connected"))
            issues.append(
                Issue(
                    (
                        f"{provider.manifest.name} doesn't allow this action with the "
                        f"permissions you granted. Reconnect {provider.manifest.name}."
                    )
                    if connected
                    else f"Connect {provider.manifest.name} to use this step.",
                    step_id=step.id,
                    kind="connect",
                    app=app_id,
                    fix_path=f"/app/settings/connections/{app_id}",
                )
            )
            continue
        for spec in action.inputs:
            value = step.inputs.get(spec.key)
            if spec.required and is_blank(value) and spec.default is None:
                if spec.type == "note" and not is_blank(step.inputs.get("note_title")):
                    continue
                issues.append(
                    Issue(
                        f"Fill in “{spec.label}” for {app_name(action.app)} · {action.label}.",
                        step_id=step.id,
                        field=spec.key,
                    )
                )
            if spec.type == "note" and isinstance(value, str) and value and "{{" not in value:
                try:
                    note = await notes.get_editable(ctx.user, uuid.UUID(value))
                    if note.deleted_at is not None:
                        raise ValueError
                except (APIError, ValueError):
                    issues.append(
                        Issue(
                            "The chosen note no longer exists. Choose another note.",
                            step_id=step.id,
                            field=spec.key,
                        )
                    )
    return issues
