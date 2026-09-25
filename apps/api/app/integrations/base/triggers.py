"""Connector triggers: "when something happens in an app", for automations.

A provider declares triggers next to its tools. Each one knows how to *poll* its vendor for
items that appeared after a moment in time; the automation scheduler (app/automation/triggers.py)
calls it every few minutes, keeps the high-water mark, de-duplicates by item id and starts one
run per new item with the item's fields as `{{trigger.<field>}}` data.

Polling (rather than webhooks) works on any deployment without a public URL, needs only the read
permission the user already granted, and survives downtime: nothing that happened while the
worker was down is lost, it is picked up by the next poll.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel

from app.ai.tools.base import OutputField
from app.integrations.base.provider import ProviderContext


class NoParams(BaseModel):
    """This trigger needs no settings."""


@dataclass(frozen=True)
class TriggerEvent:
    """One thing that happened. `id` is stable across polls (the vendor's own id)."""

    id: str
    occurred_at: datetime
    # Flat, lowercase keys: they become `{{trigger.<key>}}` in the workflow.
    data: dict[str, Any] = field(default_factory=dict)


Poller = Callable[[ProviderContext, Any, datetime], Awaitable[list[TriggerEvent]]]


def parse_time(value: Any) -> datetime | None:
    """A vendor timestamp as an aware UTC datetime: ISO 8601 (with or without `Z`) or epoch
    seconds (Slack's `ts`, e.g. "1727712000.000200"). None when absent or unreadable."""
    if value in (None, ""):
        return None
    if isinstance(value, int | float) or (isinstance(value, str) and _EPOCH.fullmatch(value)):
        return datetime.fromtimestamp(float(value), tz=UTC)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


_EPOCH = re.compile(r"\d{9,11}(\.\d+)?")


@dataclass(frozen=True)
class ProviderTrigger:
    name: str
    label: str
    description: str
    poll: Poller  # (ctx, params, since) -> events that happened after `since`
    params_model: type[BaseModel] = NoParams
    outputs: tuple[OutputField, ...] = ()
    # Read permission the poll needs; like tools, a trigger is only offered when it is granted.
    scope: str | None = None
