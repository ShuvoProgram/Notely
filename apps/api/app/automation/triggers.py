"""Event triggers: automations that start when something happens in a connected app.

An automation with ``schedule_kind == "event"`` stores its trigger in ``schedule_config``::

    {"provider": "outlook", "trigger": "email_received", "params": {...}, "every_minutes": 5}

The scheduler treats ``next_run_at`` as the next *check*. A check (``poll_due_trigger``):

1. claims the automation and moves the next check forward first (a failing check never
   stalls the schedule, and a second worker can't take the same one);
2. asks the connector for items after the high-water mark, looking back a short overlap
   window so a clock difference with the vendor can't lose an item;
3. starts one run per unseen item (oldest first, at most ``MAX_RUNS_PER_CHECK``). Each run's
   idempotency key is derived from the vendor's item id, so an item can never fire twice,
   even if the stored state were lost;
4. records progress, or a readable problem, in ``trigger_state``.

The very first check only takes a baseline: what is already there never fires, so turning an
automation on doesn't replay a whole inbox.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.ai.tools.base import OutputField
from app.automation.actions import InputField
from app.automation.validation import Issue
from app.core.config import Settings
from app.core.exceptions import ValidationFailed
from app.core.logging import get_logger
from app.db.base import utcnow
from app.integrations.base.errors import ProviderError
from app.integrations.base.rest import RestOAuthProvider
from app.integrations.base.triggers import ProviderTrigger, parse_time
from app.integrations.registry import get_providers
from app.models.automation import Automation, AutomationExecution
from app.models.user import User
from app.services.connection_service import ConnectionService

log = get_logger(__name__)

EVENT = "event"
MIN_EVERY_MINUTES = 5
MAX_EVERY_MINUTES = 60
MAX_RUNS_PER_CHECK = 10
OVERLAP = timedelta(minutes=2)
SEEN_LIMIT = 500

# Every run started by an event carries these; the provider's own fields sit beside them.
BASE_OUTPUTS = (
    OutputField("fired_at", "When it was noticed", "date"),
    OutputField("occurred_at", "When it happened", "date"),
    OutputField("event_id", "Item ID"),
)


@dataclass(frozen=True)
class EventConfig:
    provider: str
    trigger: str
    params: dict[str, Any]
    every_minutes: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "trigger": self.trigger,
            "params": self.params,
            "every_minutes": self.every_minutes,
        }


def _fix_path(provider_id: str) -> str:
    return f"/app/settings/connections/{provider_id}"


def definition(provider_id: str, name: str) -> tuple[RestOAuthProvider, ProviderTrigger]:
    provider = get_providers().get(provider_id)
    trigger = (
        next((t for t in provider.build_triggers() if t.name == name), None)
        if isinstance(provider, RestOAuthProvider)
        else None
    )
    if provider is None or trigger is None:
        raise ValidationFailed("Choose what should start this automation.", code="INVALID_TRIGGER")
    assert isinstance(provider, RestOAuthProvider)
    return provider, trigger


def parse_config(raw: dict[str, Any]) -> EventConfig:
    """Structure only: the trigger exists and its settings are valid. Raises ValidationFailed."""
    provider_id = str(raw.get("provider") or "")
    name = str(raw.get("trigger") or "")
    _, trigger = definition(provider_id, name)
    try:
        params = trigger.params_model.model_validate(raw.get("params") or {})
    except ValidationError as exc:
        message = str(exc.errors()[0]["msg"]).removeprefix("Value error, ")
        raise ValidationFailed(f"Check the trigger's settings: {message}") from exc
    try:
        every = int(raw.get("every_minutes") or MIN_EVERY_MINUTES)
    except (TypeError, ValueError) as exc:
        raise ValidationFailed("Choose how often to check.") from exc
    if not MIN_EVERY_MINUTES <= every <= MAX_EVERY_MINUTES:
        raise ValidationFailed(
            f"Check every {MIN_EVERY_MINUTES} to {MAX_EVERY_MINUTES} minutes.",
            code="INVALID_SCHEDULE",
        )
    return EventConfig(provider_id, name, params.model_dump(mode="json"), every)


def next_check(config: dict[str, Any], after: datetime) -> datetime:
    every = int(config.get("every_minutes") or MIN_EVERY_MINUTES)
    return after + timedelta(minutes=max(MIN_EVERY_MINUTES, min(every, MAX_EVERY_MINUTES)))


async def connection_issues(
    connections: ConnectionService, user: User, config: EventConfig
) -> list[Issue]:
    """What stops this trigger from working for this user right now (empty = ready)."""
    provider, trigger = definition(config.provider, config.trigger)
    name = provider.manifest.name
    fix = _fix_path(config.provider)
    conn = await connections.get_by_provider(user, config.provider)
    if conn is None:
        return [
            Issue(
                f"Connect {name} to use this trigger.",
                kind="connect",
                app=config.provider,
                fix_path=fix,
            )
        ]
    if not conn.is_usable:
        return [
            Issue(
                f"{name} needs to be reconnected.",
                kind="connect",
                app=config.provider,
                fix_path=fix,
            )
        ]
    offered = provider.triggers(connections.context(user, conn))
    if not any(t.name == trigger.name for t in offered):
        return [
            Issue(
                f"{name} hasn't granted the permission this trigger needs. Reconnect {name} "
                "and allow it.",
                kind="connect",
                app=config.provider,
                fix_path=fix,
            )
        ]
    return []


def catalog_triggers(
    connections: ConnectionService, user: User, usable: dict[str, Any], offered_apps: list[str]
) -> list[dict[str, Any]]:
    """Triggers for the builder: every offered app's triggers, available when connected with
    the permission they need (like actions)."""
    from app.automation.catalog import fields_from_schema

    out: list[dict[str, Any]] = []
    for provider_id in offered_apps:
        provider = get_providers().get(provider_id)
        if not isinstance(provider, RestOAuthProvider):
            continue
        conn = usable.get(provider_id)
        granted = (
            {t.name for t in provider.triggers(connections.context(user, conn))} if conn else set()
        )
        for trigger in provider.build_triggers():
            out.append(
                {
                    "id": f"{provider_id}.{trigger.name}",
                    "app": provider_id,
                    "app_name": provider.manifest.name,
                    "app_logo": provider.manifest.logo_url,
                    "name": trigger.name,
                    "label": trigger.label,
                    "description": trigger.description,
                    "available": trigger.name in granted,
                    "params": [
                        _param(f)
                        for f in fields_from_schema(trigger.params_model.model_json_schema())
                    ],
                    "outputs": [f.to_dict() for f in (*trigger.outputs, *BASE_OUTPUTS)],
                }
            )
    return out


def _param(field: InputField) -> dict[str, Any]:
    # Trigger settings are fixed values, never data from earlier steps (there are none yet).
    return {**field.to_dict(), "mappable": False}


# --- checking -----------------------------------------------------------------------------------


def _key(config: EventConfig, event_id: str) -> str:
    digest = hashlib.sha256(f"{config.provider}:{config.trigger}:{event_id}".encode()).hexdigest()
    return f"evt:{digest[:48]}"


async def poll_due_trigger(
    db: Any, automation_id: Any, settings: Settings
) -> list[AutomationExecution]:
    """One check of one due event automation. Returns the runs it started (not yet dispatched)."""
    from app.automation.runner import AutomationRunner

    row = await db.scalar(
        select(Automation).where(Automation.id == automation_id).with_for_update(skip_locked=True)
    )
    now = utcnow()
    if row is None or not row.enabled or row.next_run_at is None or row.next_run_at > now:
        return []
    row.next_run_at = next_check(row.schedule_config or {}, now)
    state: dict[str, Any] = dict(row.trigger_state or {})
    state["last_checked_at"] = now.isoformat()

    async def problem(message: str) -> list[AutomationExecution]:
        state.update(status="needs_attention", last_error=message)
        row.trigger_state = state
        await db.commit()
        return []

    try:
        config = parse_config(row.schedule_config or {})
    except ValidationFailed as exc:
        return await problem(exc.message)
    user = await db.get(User, row.user_id)
    connections = ConnectionService(db, settings)
    issues = await connection_issues(connections, user, config)
    if issues:
        return await problem(issues[0].message)
    conn = await connections.get_by_provider(user, config.provider)
    assert conn is not None
    provider, trigger = definition(config.provider, config.trigger)
    try:
        await connections.refresh_if_needed(user, conn)
        ctx = connections.context(user, conn)
        params = trigger.params_model.model_validate(config.params)
        since = parse_time(state.get("since"))
        events = await trigger.poll(ctx, params, (since or now) - OVERLAP)
    except ProviderError as exc:
        await connections.record_tool_failure(conn, exc, user=user)
        return await problem(f"{provider.manifest.name}: {exc.user_message()[1]}")

    seen: list[str] = list(state.get("seen") or [])
    fresh = sorted((e for e in events if e.id not in set(seen)), key=lambda e: e.occurred_at)
    started: list[AutomationExecution] = []
    if since is None:
        # Baseline: everything already there counts as seen; nothing fires.
        seen.extend(e.id for e in fresh)
        state["since"] = now.isoformat()
    else:
        batch = fresh[:MAX_RUNS_PER_CHECK]
        runner = AutomationRunner(db)
        for index, event in enumerate(batch):
            data = {
                **event.data,
                "event_id": event.id,
                "occurred_at": event.occurred_at.isoformat(),
                "app": config.provider,
                "event": config.trigger,
            }
            try:
                async with db.begin_nested():
                    execution = await runner.create_execution(
                        row,
                        run_mode=EVENT,
                        occurrence=now + timedelta(microseconds=index),
                        idempotency_key=_key(config, event.id),
                        trigger_data=data,
                    )
                started.append(execution)
            except IntegrityError:
                pass  # this item already started a run (another worker, or lost state)
            seen.append(event.id)
        # Advance only past what was handled, so a burst larger than one check's limit is
        # worked through over the next checks instead of being dropped.
        high_water = batch[-1].occurred_at if batch else None
        if high_water and len(fresh) > len(batch):
            state["since"] = high_water.isoformat()
        elif fresh:
            state["since"] = max(since, fresh[-1].occurred_at).isoformat()
        state["runs_started"] = int(state.get("runs_started") or 0) + len(started)
    state["seen"] = seen[-SEEN_LIMIT:]
    state.update(status="ok", last_error=None)
    row.trigger_state = state
    await db.commit()
    return started
