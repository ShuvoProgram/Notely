"""Tasks ↔ Google Calendar and the in-app notification inbox."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pytest

from app.tests.conftest import ORIGIN, signup
from app.tests.test_providers import CASES, VendorMock, connect, vendor  # noqa: F401, F811


async def test_notifications_inbox_marks_read_and_reminds_about_tasks(client: Any) -> None:
    await signup(client)
    inbox = (await client.get("/api/v1/notifications")).json()["data"]
    assert inbox == {"items": [], "unread": 0}

    # A task due today raises "due soon"; one due yesterday raises "overdue" — each exactly once.
    await client.post(
        "/api/v1/tasks",
        json={"title": "Ship it", "due_date": date.today().isoformat(), "timezone": "UTC"},
        headers=ORIGIN,
    )
    await client.post(
        "/api/v1/tasks",
        json={"title": "Old one", "due_date": (date.today() - timedelta(days=1)).isoformat()},
        headers=ORIGIN,
    )
    for _ in range(2):  # a second poll must not duplicate
        inbox = (await client.get("/api/v1/notifications")).json()["data"]
    kinds = sorted(n["kind"] for n in inbox["items"])
    assert kinds == ["task_due_soon", "task_overdue"]
    assert inbox["unread"] == 2

    first = inbox["items"][0]["id"]
    marked = (await client.post(f"/api/v1/notifications/{first}/read", headers=ORIGIN)).json()
    assert marked["data"]["read_at"]
    inbox = (await client.get("/api/v1/notifications")).json()["data"]
    assert inbox["unread"] == 1
    assert (await client.post("/api/v1/notifications/read-all", headers=ORIGIN)).json()["data"] == {
        "marked": 1
    }
    assert (await client.get("/api/v1/notifications")).json()["data"]["unread"] == 0


async def test_notification_preferences_switch_kinds_off(client: Any) -> None:
    await signup(client)
    await client.patch(
        "/api/v1/users/me",
        json={"notifications": {"task_reminders": False}},
        headers=ORIGIN,
    )
    await client.post(
        "/api/v1/tasks",
        json={"title": "Quiet", "due_date": (date.today() - timedelta(days=1)).isoformat()},
        headers=ORIGIN,
    )
    assert (await client.get("/api/v1/notifications")).json()["data"]["items"] == []


async def test_calendar_requires_a_connection(client: Any) -> None:
    await signup(client)
    status = (await client.get("/api/v1/tasks/calendar/status")).json()["data"]
    assert status == {
        "connected": False,
        "healthy": False,
        "can_write": False,
        "account": None,
        "status": None,
    }
    task = (
        await client.post(
            "/api/v1/tasks", json={"title": "Plan", "due_date": "2026-10-01"}, headers=ORIGIN
        )
    ).json()["data"]
    resp = await client.post(f"/api/v1/tasks/{task['id']}/calendar", json={}, headers=ORIGIN)
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "CALENDAR_NOT_CONNECTED"


@pytest.mark.parametrize("vendor", ["google_calendar"], indirect=True)
async def test_task_syncs_to_google_calendar_once_and_follows_edits(
    client: Any,
    vendor: VendorMock,  # noqa: F811
) -> None:
    await signup(client)
    await connect(
        client,
        "google_calendar",
        CASES["google_calendar"],
        scopes=["https://www.googleapis.com/auth/calendar.events"],
    )
    status = (await client.get("/api/v1/tasks/calendar/status")).json()["data"]
    assert status["connected"] and status["can_write"] and status["account"] == "ada@acme.io"

    # A task without a due date can't become an event.
    bare = (await client.post("/api/v1/tasks", json={"title": "Someday"}, headers=ORIGIN)).json()[
        "data"
    ]
    resp = await client.post(f"/api/v1/tasks/{bare['id']}/calendar", json={}, headers=ORIGIN)
    assert resp.status_code == 422

    task = (
        await client.post(
            "/api/v1/tasks",
            json={
                "title": "Pricing review",
                "due_date": "2026-10-01",
                "due_time": "10:00:00",
                "timezone": "Asia/Dhaka",
                "priority": "high",
            },
            headers=ORIGIN,
        )
    ).json()["data"]
    linked = (
        await client.post(f"/api/v1/tasks/{task['id']}/calendar", json={}, headers=ORIGIN)
    ).json()["data"]
    assert linked["calendar_event_id"] == "e2"
    assert linked["calendar_event_url"] == "https://calendar.google.com/e2"
    assert linked["calendar_synced_at"] and linked["calendar_error"] is None
    body = vendor.state["gcal_last_body"]
    assert body["start"] == {"dateTime": "2026-10-01T10:00:00", "timeZone": "Asia/Dhaka"}
    assert body["end"] == {"dateTime": "2026-10-01T11:00:00", "timeZone": "Asia/Dhaka"}
    assert body["extendedProperties"]["private"]["notely_task_id"] == task["id"]

    # Syncing again and editing the task PATCH the same event — never a second one.
    await client.post(f"/api/v1/tasks/{task['id']}/calendar", json={}, headers=ORIGIN)
    edited = (
        await client.patch(
            f"/api/v1/tasks/{task['id']}",
            json={"title": "Pricing review (final)", "clear_due_time": True},
            headers=ORIGIN,
        )
    ).json()["data"]
    assert edited["due_time"] is None and edited["calendar_event_id"] == "e2"
    assert vendor.state["gcal_created"] == 1 and vendor.state["gcal_patched"] == 2
    assert vendor.state["gcal_last_body"]["summary"] == "Pricing review (final)"
    assert vendor.state["gcal_last_body"]["start"] == {"date": "2026-10-01"}  # all-day now

    # Completing prefixes the event; the inbox saw the sync.
    await client.patch(f"/api/v1/tasks/{task['id']}", json={"status": "done"}, headers=ORIGIN)
    assert vendor.state["gcal_last_body"]["summary"].startswith("✓ ")
    kinds = {n["kind"] for n in (await client.get("/api/v1/notifications")).json()["data"]["items"]}
    assert {"integration_connected", "calendar_synced", "task_completed"} <= kinds

    # Unlinking deletes the event; deleting a linked task also cleans up.
    unlinked = (await client.delete(f"/api/v1/tasks/{task['id']}/calendar", headers=ORIGIN)).json()[
        "data"
    ]
    assert unlinked["calendar_event_id"] is None and vendor.state["gcal_deleted"] == 1
    await client.post(f"/api/v1/tasks/{task['id']}/calendar", json={}, headers=ORIGIN)
    await client.delete(f"/api/v1/tasks/{task['id']}", headers=ORIGIN)
    assert vendor.state["gcal_deleted"] == 2
