"""Evaluate filter and path conditions against a run's scope.

Comparisons are forgiving in the way a non-technical user expects: text comparisons ignore
case, numbers written as text compare as numbers, and a list "contains" an item when any
element's text contains it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.automation.mapping import is_blank, resolve, to_text
from app.automation.model import Condition, ConditionRule


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, list):
        return float(len(value))
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _date(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            from email.utils import parsedate_to_datetime

            try:
                parsed = parsedate_to_datetime(text)  # e-mail style dates
            except (TypeError, ValueError):
                return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _truthy(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "y", "1"}
    return bool(value)


def _contains(haystack: Any, needle: Any) -> bool:
    wanted = to_text(needle).casefold()
    if isinstance(haystack, list):
        return any(wanted in to_text(item).casefold() for item in haystack)
    return wanted in to_text(haystack).casefold()


def _equal(left: Any, right: Any) -> bool:
    ln, rn = _number(left), _number(right)
    if ln is not None and rn is not None and not isinstance(left, list):
        return ln == rn
    if isinstance(left, bool) or isinstance(right, bool):
        return _truthy(left) == _truthy(right)
    return to_text(left).strip().casefold() == to_text(right).strip().casefold()


def evaluate_rule(rule: ConditionRule, scope: dict[str, Any]) -> bool:
    left = resolve(rule.left, scope)
    right = resolve(rule.right, scope) if isinstance(rule.right, str) else rule.right
    op = rule.operator
    if op == "exists":
        return left is not None
    if op == "not_exists":
        return left is None
    if op == "is_empty":
        return is_blank(left)
    if op == "is_not_empty":
        return not is_blank(left)
    if op == "is_true":
        return _truthy(left)
    if op == "is_false":
        return not _truthy(left)
    if op == "equals":
        return _equal(left, right)
    if op == "not_equals":
        return not _equal(left, right)
    if op == "contains":
        return _contains(left, right)
    if op == "not_contains":
        return not _contains(left, right)
    if op in ("greater_than", "less_than"):
        ln, rn = _number(left), _number(right)
        if ln is None or rn is None:
            return False
        return ln > rn if op == "greater_than" else ln < rn
    if op in ("before", "after"):
        ld, rd = _date(left), _date(right)
        if ld is None or rd is None:
            return False
        return ld < rd if op == "before" else ld > rd
    return False


def evaluate(condition: Condition, scope: dict[str, Any]) -> bool:
    results = (
        evaluate(rule, scope) if isinstance(rule, Condition) else evaluate_rule(rule, scope)
        for rule in condition.rules
    )
    outcome = all(results) if condition.match == "all" else any(results)
    return not outcome if condition.negate else outcome
