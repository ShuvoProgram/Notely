"""Data mapping between steps.

A run keeps a *scope*::

    {"steps": {<id>: {"status": "completed", "output": {...}}},
     "trigger": {"type": "schedule", "fired_at": "...", "previous_run_at": "..."},
     "automation": {"name": "..."}}

`{{steps.mail.output.results}}` on its own keeps the value's type (a list stays a list);
inside other text it becomes readable text, never JSON. Paths support list indexes
(`results.0.subject`) and `.count`.
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.automation.model import REFERENCE

_UNTRUSTED = re.compile(r'<untrusted_content source="[^"]*">\n?(.*?)\n?</untrusted_content>', re.S)
_ONLY_REFERENCE = re.compile(r"^\s*\{\{\s*([^{}]+?)\s*\}\}\s*$")
# Preferred keys when a record has to be shown as one line of text.
_TITLE_KEYS = ("title", "subject", "name", "summary", "text", "snippet", "message")
MAX_OUTPUT_CHARS = 200_000


class ReferenceUnavailable(Exception):
    """Raised when a step's data is required but that step failed or has not run."""

    def __init__(self, step_id: str) -> None:
        super().__init__(step_id)
        self.step_id = step_id


def unwrap(value: Any) -> Any:
    """Strip the assistant's untrusted-content markers from connector output.

    The markers protect the chat model from prompt injection; inside a workflow the data is
    passed to real fields (task titles, note bodies), and AI steps add their own framing.
    """
    if isinstance(value, str):
        if "<untrusted_content" not in value:
            return value
        return _UNTRUSTED.sub(lambda m: m.group(1), value).replace(
            "</untrusted_content >", "</untrusted_content>"
        )
    if isinstance(value, dict):
        return {key: unwrap(item) for key, item in value.items()}
    if isinstance(value, list):
        return [unwrap(item) for item in value]
    return value


def cap(value: Any, limit: int = MAX_OUTPUT_CHARS) -> Any:
    """Bound what is persisted per step: long texts are shortened, long lists trimmed."""
    try:
        size = len(json.dumps(value, default=str))
    except (TypeError, ValueError):
        return str(value)[:limit]
    if size <= limit:
        return value

    def shrink(item: Any, depth: int = 0) -> Any:
        if isinstance(item, str):
            return item if len(item) <= 4_000 else item[:4_000] + "…"
        if isinstance(item, list):
            return [shrink(x, depth + 1) for x in item[:100]]
        if isinstance(item, dict):
            return {k: shrink(v, depth + 1) for k, v in item.items()}
        return item

    return shrink(value)


def lookup(scope: dict[str, Any], path: str) -> Any:
    """Resolve a dotted path. Missing data is ``None``; a failed/unrun source step raises."""
    parts = path.split(".")
    if parts[0] == "steps" and len(parts) >= 3:
        entry = (scope.get("steps") or {}).get(parts[1])
        if entry is None or entry.get("status") in ("failed", "pending", "running", None):
            raise ReferenceUnavailable(parts[1])
        current: Any = entry.get("output")
        rest = parts[3:]
    else:
        current, rest = scope, parts
    for part in rest:
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit():
            index = int(part)
            current = current[index] if index < len(current) else None
        elif part == "count" and isinstance(current, (list, dict, str)):
            current = len(current)
        else:
            return None
    return current


def to_text(value: Any) -> str:
    """Readable text for a value placed inside a sentence or a note."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (int, float, str)):
        return str(value)
    if isinstance(value, list):
        lines = [to_text(item) for item in value]
        return "\n".join(f"- {line}" if "\n" not in line else line for line in lines if line)
    if isinstance(value, dict):
        title = next((value[k] for k in _TITLE_KEYS if isinstance(value.get(k), str)), None)
        details = [
            f"{key.replace('_', ' ')}: {to_text(item)}"
            for key, item in value.items()
            if item not in (None, "", [], {})
            and not isinstance(item, (dict, list))
            and item is not title
            and key not in ("url", "sources", "id")
            and not key.endswith("_id")
        ]
        if title:
            extra = [d for d in details if not d.startswith(("title:", "subject:", "name:"))]
            return title + (f" ({'; '.join(extra[:3])})" if extra else "")
        return "; ".join(details)
    return str(value)


def resolve(value: Any, scope: dict[str, Any]) -> Any:
    """Replace references inside step inputs with data from the scope."""
    if isinstance(value, dict):
        return {key: resolve(item, scope) for key, item in value.items()}
    if isinstance(value, list):
        return [resolve(item, scope) for item in value]
    if not isinstance(value, str) or "{{" not in value:
        return value
    only = _ONLY_REFERENCE.match(value)
    if only:
        return lookup(scope, only.group(1).strip())
    return REFERENCE.sub(lambda m: to_text(lookup(scope, m.group(1).strip())), value)


def is_blank(value: Any) -> bool:
    return (
        value is None
        or (isinstance(value, (str, list, dict)) and not value)
        or (isinstance(value, str) and not value.strip())
    )
