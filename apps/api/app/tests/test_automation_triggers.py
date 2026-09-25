"""Event-triggered automations: "when something happens in <app>" → workflow.

Driven end to end: a real OAuth connection (to the recording Slack stand-in), the builder
catalog, saving, the every-minute cron, the check, filters and a Notely action.
"""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient

from app.automation.triggers import MAX_RUNS_PER_CHECK, parse_config
from app.core.exceptions import ValidationFailed
from app.db.session import get_session_factory
from app.integrations.base.triggers import parse_time
from app.models.automation import Automation
from app.tests.conftest import ORIGIN, signup
from app.tests.test_automations import API, action, body, rule, task_titles
from app.tests.test_providers import CASES, connect_via_oauth
from app.tests.test_providers import vendor as vendor  # noqa: F401
from app.tests.vendor_mocks import VendorMock
from app.workers.jobs.automations import run_due_automations

EVENT = {
    "provider": "slack",
    "trigger": "message_posted",
    "params": {"channel": "#general"},
    "every_minutes": 5,
}


def message(text: str, seconds_ago: float = 0) -> dict[str, Any]:
    # A Slack message's id is its channel + `ts`, unique per channel: give each its own.
    return {"ts": f"{time.time() - seconds_ago:.6f}", "user": "U2", "text": text}


def post(vendor: VendorMock, *messages: dict[str, Any]) -> None:
    # Slack returns newest first.
    history = [*messages, *vendor.state.get("slack_history", [])]
    vendor.state["slack_history"] = sorted(history, key=lambda m: float(m["ts"]), reverse=True)


async def make_due(automation_id: str) -> None:
    async with get_session_factory()() as db:
        row = await db.get(Automation, uuid.UUID(automation_id))
        assert row is not None
        row.next_run_at = datetime.now(UTC) - timedelta(seconds=1)
        await db.commit()


async def check(automation_id: str) -> int:
    await make_due(automation_id)
    return await run_due_automations({})


async def urgent_to_task(client: AsyncClient, **overrides: Any) -> dict[str, Any]:
    steps = [
        {
            "kind": "filter",
            "id": "only_urgent",
            "condition": {
                "match": "all",
                "rules": [rule("{{trigger.text}}", "contains", "urgent")],
            },
        },
        action(
            "task", "notely.create_task", {"title": "Slack ({{trigger.user}}): {{trigger.text}}"}
        ),
    ]
    payload = body(steps, schedule_kind="event", schedule_config=EVENT, enabled=True, **overrides)
    response = await client.post(API, json=payload, headers=ORIGIN)
    assert response.status_code == 201, response.text
    return dict(response.json()["data"])


@pytest.mark.parametrize("vendor", ["slack"], indirect=True)
async def test_slack_message_to_notely_task(client: AsyncClient, vendor: VendorMock) -> None:
    await signup(client)
    await connect_via_oauth(client, "slack", CASES["slack"])

    catalog = (await client.get(f"{API}/catalog")).json()["data"]
    trigger = next(t for t in catalog["triggers"] if t["id"] == "slack.message_posted")
    assert trigger["available"] is True and trigger["app_name"] == "Slack"
    assert [p["key"] for p in trigger["params"]] == ["channel"]
    assert {"text", "user", "channel", "fired_at"} <= {o["key"] for o in trigger["outputs"]}

    post(vendor, message("urgent: old news", seconds_ago=3600))
    automation = await urgent_to_task(client)
    assert automation["schedule_kind"] == "event" and automation["enabled"]
    assert automation["trigger_status"]["status"] == "waiting"

    # First check: a baseline. What was already in the channel never fires.
    assert await check(automation["id"]) == 0
    assert await task_titles(client) == []

    post(vendor, message("urgent: server is down", seconds_ago=2), message("lunch anyone?", 1))
    assert await check(automation["id"]) == 2  # two runs; the filter stops the lunch one
    assert await task_titles(client) == ["Slack (sam): urgent: server is down"]

    # Checking again finds nothing new: an item never fires twice.
    assert await check(automation["id"]) == 0
    runs = (await client.get(f"{API}/{automation['id']}/runs")).json()["data"]
    assert {r["run_mode"] for r in runs} == {"event"}
    assert {r["trigger"]["channel"] for r in runs} == {"general"}

    status = (await client.get(f"{API}/{automation['id']}")).json()["data"]["trigger_status"]
    assert status["status"] == "ok" and status["runs_started"] == 2 and status["last_error"] is None


@pytest.mark.parametrize("vendor", ["slack"], indirect=True)
async def test_a_burst_is_worked_through_over_several_checks(
    client: AsyncClient, vendor: VendorMock
) -> None:
    await signup(client)
    await connect_via_oauth(client, "slack", CASES["slack"])
    automation = await urgent_to_task(client)
    assert await check(automation["id"]) == 0  # baseline
    burst = MAX_RUNS_PER_CHECK + 3
    post(vendor, *(message(f"urgent #{i}", seconds_ago=burst - i) for i in range(burst)))
    assert await check(automation["id"]) == MAX_RUNS_PER_CHECK
    assert await check(automation["id"]) == 3  # the rest, nothing lost
    assert await check(automation["id"]) == 0
    titles = await task_titles(client)
    assert len(titles) == burst and len(set(titles)) == burst


@pytest.mark.parametrize("vendor", ["slack"], indirect=True)
async def test_a_revoked_connection_is_reported_and_nothing_runs(
    client: AsyncClient, vendor: VendorMock
) -> None:
    await signup(client)
    await connect_via_oauth(client, "slack", CASES["slack"])
    automation = await urgent_to_task(client)
    assert await check(automation["id"]) == 0
    vendor.fail_auth = True
    post(vendor, message("urgent: after revoke"))
    assert await check(automation["id"]) == 0
    status = (await client.get(f"{API}/{automation['id']}")).json()["data"]["trigger_status"]
    assert status["status"] == "needs_attention"
    assert status["last_error"].startswith("Slack")
    connection = (await client.get("/api/v1/integrations/providers/slack")).json()["data"]
    assert connection["connection"]["status"] == "expired"
    # The next check still happens (the schedule never stalls); it says the same thing.
    assert await check(automation["id"]) == 0


async def test_an_unconnected_app_cannot_be_switched_on(client: AsyncClient) -> None:
    await signup(client)
    steps = [action("task", "notely.create_task", {"title": "x"})]
    draft = await client.post(
        API,
        json=body(steps, schedule_kind="event", schedule_config=EVENT, enabled=False),
        headers=ORIGIN,
    )
    assert draft.status_code == 201  # drafts may be saved before connecting
    turned_on = await client.post(
        API,
        json=body(steps, schedule_kind="event", schedule_config=EVENT, enabled=True),
        headers=ORIGIN,
    )
    assert turned_on.status_code == 422
    assert "Connect Slack" in turned_on.text


def test_trigger_settings_are_validated() -> None:
    config = parse_config({**EVENT, "every_minutes": 15})
    assert config.every_minutes == 15 and config.params == {"channel": "#general"}
    for bad in (
        {**EVENT, "trigger": "nope"},
        {**EVENT, "provider": "nope"},
        {**EVENT, "params": {}},  # the channel is required
        {**EVENT, "every_minutes": 1},
    ):
        with pytest.raises(ValidationFailed):
            parse_config(bad)


def test_vendor_timestamps_parse() -> None:
    assert parse_time("2026-09-25T08:00:00Z") == datetime(2026, 9, 25, 8, tzinfo=UTC)
    assert parse_time("1727712000.000200") == datetime.fromtimestamp(1727712000.0002, tz=UTC)
    assert parse_time("2026-09-25T08:00:00") == datetime(2026, 9, 25, 8, tzinfo=UTC)
    assert parse_time(None) is None and parse_time("soon") is None


@pytest.mark.parametrize("vendor", ["zoom"], indirect=True)
async def test_ai_drafts_an_event_triggered_automation(
    client: AsyncClient, vendor: VendorMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ "When a Zoom meeting ends, create a follow-up task" becomes an event automation, and the
    unconnected Zoom is named so the user can connect it."""
    import json

    from app.tests.test_automations import fake_ai

    await signup(client)
    reply = {
        "name": "Zoom follow-ups",
        "description": "Creates a follow-up task after each Zoom meeting.",
        "schedule": {"kind": "event", "trigger": "zoom.meeting_ended", "params": {}},
        "steps": [
            action("task", "notely.create_task", {"title": "Follow up: {{trigger.topic}}"}),
        ],
        "missing_apps": [],
        "unsupported": [],
        "questions": [],
    }
    model = fake_ai(monkeypatch, lambda _: json.dumps(reply))
    draft = (
        await client.post(
            f"{API}/draft",
            json={"prompt": "When a Zoom meeting ends, create a follow-up task", "timezone": "UTC"},
            headers=ORIGIN,
        )
    ).json()["data"]
    assert '"zoom.meeting_ended"' in model.prompts[0]  # the planner is told about triggers
    assert draft["schedule_kind"] == "event"
    assert draft["schedule_config"] == {
        "provider": "zoom",
        "trigger": "meeting_ended",
        "params": {},
        "every_minutes": 5,
    }
    assert [m["app"] for m in draft["missing_apps"]] == ["zoom"]
    assert draft["questions"] == []

    # A trigger the model made up is caught, not saved.
    reply["schedule"] = {"kind": "event", "trigger": "zoom.meeting_exploded"}
    bad = (
        await client.post(
            f"{API}/draft", json={"prompt": "After Zoom calls", "timezone": "UTC"}, headers=ORIGIN
        )
    ).json()["data"]
    assert bad["questions"] and bad["schedule_kind"] == "event"


@pytest.mark.parametrize("vendor", ["slack"], indirect=True)
async def test_connections_page_lists_real_abilities_and_missing_permissions(
    client: AsyncClient, vendor: VendorMock
) -> None:
    await signup(client)
    before = (await client.get("/api/v1/integrations/providers/slack")).json()["data"]
    labels = {a["label"]: a for a in before["abilities"]}
    assert labels["Post a message to a channel as you."]["permission"] == "Send messages as you"
    assert all(a["granted"] is None for a in before["abilities"])  # not connected yet
    assert any(
        a["kind"] == "trigger" and a["label"].startswith("New message in a channel")
        for a in before["abilities"]
    )

    await connect_via_oauth(
        client, "slack", CASES["slack"]
    )  # grants chat:write, not channels:manage
    after = {
        a["label"]: a
        for a in (await client.get("/api/v1/integrations/providers/slack")).json()["data"][
            "abilities"
        ]
    }
    assert after["Post a message to a channel as you."]["granted"] is True
    assert after["Create a public Slack channel."]["granted"] is False
    assert after["Create a public Slack channel."]["permission"] == "Create public channels"
    assert after["Search Slack messages."]["permission"] is None  # needs nothing optional
