"""The persisted workflow definition (version 2).

    steps: [ action | filter | branch ]

An *action* runs one capability from the catalog; a *filter* stops the run (or the current
path) unless its condition holds; a *branch* runs one of two nested step lists and then the
workflow continues. Inputs reference earlier data with ``{{steps.<id>.output.<field>}}``,
``{{trigger.<field>}}`` or ``{{automation.name}}``.

This module validates structure only (ids, nesting, references). Whether an action exists,
is connected and has its required inputs is checked against the user's capability catalog
in ``app.automation.validation``.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, model_validator

STEP_ID = r"^[a-z][a-z0-9_]{0,63}$"
ACTION_ID = r"^[a-z0-9_]+\.[a-z0-9_]+$"
MAX_STEPS = 40
MAX_DEPTH = 3

REFERENCE = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")
_STEP_REFERENCE = re.compile(r"^steps\.([a-z][a-z0-9_]*)\.output(?:\.[A-Za-z0-9_]+)*$")
_OTHER_REFERENCE = re.compile(r"^(?:trigger\.[a-z_]+|automation\.name)$")

Operator = Literal[
    "equals",
    "not_equals",
    "contains",
    "not_contains",
    "greater_than",
    "less_than",
    "exists",
    "not_exists",
    "is_empty",
    "is_not_empty",
    "is_true",
    "is_false",
    "before",
    "after",
]
UNARY_OPERATORS = frozenset(
    {"exists", "not_exists", "is_empty", "is_not_empty", "is_true", "is_false"}
)


class ConditionRule(BaseModel):
    """`left` is usually a data reference; `right` is a literal or another reference."""

    left: str = Field(min_length=1, max_length=500)
    operator: Operator
    right: str | int | float | bool | None = None

    @model_validator(mode="after")
    def needs_right(self) -> ConditionRule:
        if self.operator not in UNARY_OPERATORS and (self.right is None or self.right == ""):
            raise ValueError("Choose what to compare with.")
        return self


class Condition(BaseModel):
    match: Literal["all", "any"] = "all"
    rules: list[ConditionRule | Condition] = Field(min_length=1, max_length=10)
    negate: bool = False


class _StepBase(BaseModel):
    id: str = Field(pattern=STEP_ID)
    # Optional user-facing title; the builder falls back to the action's label.
    name: str | None = Field(default=None, max_length=120)
    enabled: bool = True


class ActionStep(_StepBase):
    kind: Literal["action"] = "action"
    action: str = Field(pattern=ACTION_ID, max_length=160)
    inputs: dict[str, Any] = Field(default_factory=dict)
    # Only meaningful for actions whose safety is `ask`; `always_ask` ignores it, `safe` never asks.
    approval: Literal["ask", "auto"] = "ask"
    on_error: Literal["stop", "continue"] = "stop"
    retries: int = Field(default=2, ge=0, le=3)


class FilterStep(_StepBase):
    kind: Literal["filter"] = "filter"
    condition: Condition


class BranchStep(_StepBase):
    kind: Literal["branch"] = "branch"
    condition: Condition
    then: list[Step] = Field(default_factory=list, max_length=MAX_STEPS)
    otherwise: list[Step] = Field(default_factory=list, max_length=MAX_STEPS)


Step = Annotated[ActionStep | FilterStep | BranchStep, Field(discriminator="kind")]
BranchStep.model_rebuild()


def iter_steps(steps: list[Any]) -> Iterator[Any]:
    """Pre-order walk over every step, including those nested in branches."""
    for step in steps:
        yield step
        if isinstance(step, BranchStep):
            yield from iter_steps(step.then)
            yield from iter_steps(step.otherwise)


def references(value: Any) -> list[str]:
    """Every `{{…}}` path inside a (nested) value."""
    found: list[str] = []
    if isinstance(value, str):
        found.extend(match.strip() for match in REFERENCE.findall(value))
    elif isinstance(value, dict):
        for item in value.values():
            found.extend(references(item))
    elif isinstance(value, list):
        for item in value:
            found.extend(references(item))
    return found


def step_references(step: Any) -> list[str]:
    if isinstance(step, ActionStep):
        return references(step.inputs)
    if isinstance(step, (FilterStep, BranchStep)):
        return references(step.condition.model_dump())
    return []


class Workflow(BaseModel):
    version: Literal[2] = 2
    steps: list[Step] = Field(min_length=1, max_length=MAX_STEPS)

    @model_validator(mode="before")
    @classmethod
    def upgrade(cls, data: Any) -> Any:
        if isinstance(data, dict) and data.get("version", 1) == 1:
            return upgrade_v1(data)
        return data

    @model_validator(mode="after")
    def structure(self) -> Workflow:
        seen: set[str] = set()
        total = 0

        def walk(steps: list[Any], visible: set[str], depth: int) -> set[str]:
            nonlocal total
            if depth > MAX_DEPTH:
                raise ValueError(f"Paths can be nested at most {MAX_DEPTH} levels deep.")
            produced: set[str] = set()
            for step in steps:
                total += 1
                if step.id in seen:
                    raise ValueError(f"Two steps share the id '{step.id}'.")
                seen.add(step.id)
                for path in step_references(step):
                    matched = _STEP_REFERENCE.match(path)
                    if matched is None:
                        if _OTHER_REFERENCE.match(path) is None:
                            raise ValueError(f"'{path}' is not a valid piece of data.")
                        continue
                    if matched.group(1) not in visible:
                        raise ValueError(
                            f"A step uses data from '{matched.group(1)}' before it is available. "
                            "Check the order of the steps."
                        )
                if isinstance(step, BranchStep):
                    then_ids = walk(step.then, set(visible), depth + 1)
                    other_ids = walk(step.otherwise, set(visible), depth + 1)
                    # Later steps may use either path's data; it is empty when that path was
                    # not taken, which the engine resolves as "no value".
                    visible |= then_ids | other_ids
                    produced |= then_ids | other_ids
                visible.add(step.id)
                produced.add(step.id)
            return produced

        walk(self.steps, set(), 1)
        if total > MAX_STEPS:
            raise ValueError(f"An automation can have at most {MAX_STEPS} steps.")
        return self


# --- version 1 upgrade ------------------------------------------------------------------------
# Version 1 was a flat list of kinds with per-step "gating" conditions. It never shipped to
# production; this keeps drafts made during development loadable.

_V1_NATIVE = {
    "create_task": "notely.create_task",
    "create_note": "notely.create_note",
    "update_note": "notely.update_note",
    "notify": "notely.notify",
}
_V1_OPERATORS = {
    "equals": "equals",
    "not_equals": "not_equals",
    "contains": "contains",
    "greater": "greater_than",
    "less": "less_than",
    "has_data": "is_not_empty",
    "before": "before",
    "after": "after",
}


def _v1_condition(raw: dict[str, Any], decisions: dict[str, dict[str, Any]]) -> dict[str, Any]:
    if raw.get("all") is not None or raw.get("any") is not None:
        match = "all" if raw.get("all") is not None else "any"
        return {
            "match": match,
            "rules": [_v1_condition(item, decisions) for item in raw[match]],
        }
    path = str(raw.get("path") or "")
    decision = re.fullmatch(r"steps\.([a-z][a-z0-9_]*)\.output\.matched", path)
    if decision and decision.group(1) in decisions:
        wanted = raw.get("equals", raw.get("value", True))
        condition = dict(decisions[decision.group(1)])
        if wanted is False:
            condition["negate"] = not condition.get("negate", False)
        return condition
    left = "{{" + path + "}}"
    if raw.get("operator"):
        rule: dict[str, Any] = {"left": left, "operator": _V1_OPERATORS[raw["operator"]]}
        if rule["operator"] not in UNARY_OPERATORS:
            rule["right"] = raw.get("value")
        return {"match": "all", "rules": [rule]}
    rules: list[dict[str, Any]] = []
    if raw.get("exists") is not None:
        rules.append({"left": left, "operator": "exists" if raw["exists"] else "not_exists"})
    if raw.get("equals") is not None:
        rules.append({"left": left, "operator": "equals", "right": raw["equals"]})
    if raw.get("min_items") is not None:
        rules.append(
            {
                "left": "{{" + path + ".count}}",
                "operator": "greater_than",
                "right": int(raw["min_items"]) - 1,
            }
        )
    return {"match": "all", "rules": rules or [{"left": left, "operator": "is_not_empty"}]}


def upgrade_v1(data: dict[str, Any]) -> dict[str, Any]:
    decisions: dict[str, dict[str, Any]] = {}
    steps: list[dict[str, Any]] = []
    for raw in data.get("steps") or []:
        if not isinstance(raw, dict):
            steps.append(raw)
            continue
        kind = raw.get("kind")
        if kind == "condition":
            # A v1 decision produced `matched`; its readers are rewritten to the condition itself.
            decisions[str(raw.get("id"))] = _v1_condition(raw.get("condition") or {}, decisions)
            continue
        arguments = dict(raw.get("arguments") or {})
        if kind == "provider_tool":
            action = f"{raw.get('provider')}.{raw.get('tool')}"
        elif kind == "ai":
            action = "ai.ask"
            arguments = {
                "instructions": arguments.get("prompt", ""),
                "data": arguments.get("input", ""),
            }
        else:
            action = _V1_NATIVE.get(str(kind), f"notely.{kind}")
        automatic = raw.get("approval_mode") == "automatic" and not raw.get("approval_required")
        step: dict[str, Any] = {
            "kind": "action",
            "id": raw.get("id"),
            "action": action,
            "inputs": arguments,
            "enabled": raw.get("enabled", True),
            "approval": "auto" if automatic else "ask",
            "on_error": raw.get("on_failure", "stop"),
        }
        gate = raw.get("condition")
        if isinstance(gate, dict):
            steps.append(
                {
                    "kind": "branch",
                    "id": f"{raw.get('id')}_if",
                    "condition": _v1_condition(gate, decisions),
                    "then": [step],
                    "otherwise": [],
                }
            )
        else:
            steps.append(step)
    return {"version": 2, "steps": steps}
