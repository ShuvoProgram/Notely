"""Notes: stable ordering, version history, colour, reminders and collaboration."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.tests.conftest import ORIGIN, signup

DOC = {
    "type": "doc",
    "content": [{"type": "paragraph", "content": [{"type": "text", "text": "hi"}]}],
}


async def make(client: Any, title: str, text: str = "hi") -> dict[str, Any]:
    doc = {
        "type": "doc",
        "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}],
    }
    r = await client.post(
        "/api/v1/notes", json={"title": title, "content_json": doc}, headers=ORIGIN
    )
    assert r.status_code == 201, r.text
    return dict(r.json()["data"])


async def titles(client: Any, view: str = "active") -> list[str]:
    return [n["title"] for n in (await client.get(f"/api/v1/notes?view={view}")).json()["data"]]


async def test_resending_identical_content_is_not_an_edit(client: Any) -> None:
    """Opening a note (whose editor may PATCH the unchanged body back) must not reorder the list
    or bump the version; a real edit does both."""
    await signup(client)
    a = await make(client, "A")
    b = await make(client, "B")
    c = await make(client, "C")
    assert await titles(client) == ["C", "B", "A"]

    # The editor "opens" A and echoes its body: nothing changes.
    echoed = (
        await client.patch(
            f"/api/v1/notes/{a['id']}",
            json={"content_json": a["content_json"], "title": a["title"], "expected_version": 1},
            headers=ORIGIN,
        )
    ).json()["data"]
    assert echoed["version"] == 1 and echoed["updated_at"] == a["updated_at"]
    assert await titles(client) == ["C", "B", "A"]

    # A real edit moves A to the top and bumps the version.
    edited = (
        await client.patch(
            f"/api/v1/notes/{a['id']}",
            json={
                "content_json": {
                    **DOC,
                    "content": [
                        {"type": "paragraph", "content": [{"type": "text", "text": "changed"}]}
                    ],
                },
                "expected_version": 1,
            },
            headers=ORIGIN,
        )
    ).json()["data"]
    assert edited["version"] == 2 and edited["updated_at"] > a["updated_at"]
    assert await titles(client) == ["A", "C", "B"]
    assert b["id"] and c["id"]


async def test_colour_and_reminder_persist_and_remind(client: Any) -> None:
    await signup(client)
    note = await make(client, "Groceries")
    when = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
    updated = (
        await client.patch(
            f"/api/v1/notes/{note['id']}",
            json={"color": "green", "reminder_at": when},
            headers=ORIGIN,
        )
    ).json()["data"]
    assert updated["color"] == "green" and updated["reminder_at"]
    # Appearance/reminder are metadata, not edits: the version is untouched.
    assert updated["version"] == 1
    row = (await client.get("/api/v1/notes")).json()["data"][0]
    assert row["color"] == "green" and row["reminder_at"]

    inbox = (await client.get("/api/v1/notifications")).json()["data"]
    assert [n["kind"] for n in inbox["items"]] == ["note_reminder"]
    assert inbox["items"][0]["href"] == f"/app/notes/{note['id']}"
    # Polling again does not repeat it; clearing removes the reminder.
    assert len((await client.get("/api/v1/notifications")).json()["data"]["items"]) == 1
    cleared = (
        await client.patch(
            f"/api/v1/notes/{note['id']}", json={"clear_reminder": True}, headers=ORIGIN
        )
    ).json()["data"]
    assert cleared["reminder_at"] is None

    bad = await client.patch(f"/api/v1/notes/{note['id']}", json={"color": "neon"}, headers=ORIGIN)
    assert bad.status_code == 422


async def test_checklist_progress_in_summary(client: Any) -> None:
    await signup(client)
    doc = {
        "type": "doc",
        "content": [
            {
                "type": "taskList",
                "content": [
                    {
                        "type": "taskItem",
                        "attrs": {"checked": True},
                        "content": [
                            {"type": "paragraph", "content": [{"type": "text", "text": "a"}]}
                        ],
                    },
                    {
                        "type": "taskItem",
                        "attrs": {"checked": False},
                        "content": [
                            {"type": "paragraph", "content": [{"type": "text", "text": "b"}]}
                        ],
                    },
                ],
            }
        ],
    }
    await client.post("/api/v1/notes", json={"title": "List", "content_json": doc}, headers=ORIGIN)
    row = (await client.get("/api/v1/notes")).json()["data"][0]
    assert row["checklist"] == {"done": 1, "total": 2}


async def test_version_history_snapshots_and_restores(client: Any) -> None:
    await signup(client)
    note = await make(client, "Draft", "first")
    nid = note["id"]
    assert (await client.get(f"/api/v1/notes/{nid}/versions")).json()["data"] == []

    def body(text: str) -> dict[str, Any]:
        return {
            "type": "doc",
            "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}],
        }

    # First edit snapshots the original; a burst of further edits within the interval does not.
    for i, text in enumerate(["second", "third", "fourth"], start=1):
        r = await client.patch(
            f"/api/v1/notes/{nid}",
            json={"content_json": body(text), "expected_version": i},
            headers=ORIGIN,
        )
        assert r.status_code == 200, r.text
    versions = (await client.get(f"/api/v1/notes/{nid}/versions")).json()["data"]
    assert [v["plain_text"] for v in versions] == ["first"]
    assert versions[0]["note_version"] == 1 and versions[0]["reason"] == "edit"

    detail = (await client.get(f"/api/v1/notes/{nid}/versions/{versions[0]['id']}")).json()["data"]
    assert detail["content_json"] == body("first")

    # Restore: the current state is kept as a version, so the restore is reversible.
    restored = (
        await client.post(
            f"/api/v1/notes/{nid}/versions/{versions[0]['id']}/restore", headers=ORIGIN
        )
    ).json()["data"]
    assert restored["plain_text"] == "first" and restored["version"] == 5
    versions = (await client.get(f"/api/v1/notes/{nid}/versions")).json()["data"]
    assert [v["plain_text"] for v in versions] == ["fourth", "first"]
    assert versions[0]["reason"] == "before_restore"


async def test_collaborators_invite_access_and_shared_view(client: Any) -> None:
    await signup(client, email="owner@example.com")
    note = await make(client, "Team plan")
    nid = note["id"]

    # Inviting yourself is refused; inviting a colleague (existing or not) works.
    me = await client.post(
        f"/api/v1/notes/{nid}/collaborators", json={"email": "owner@example.com"}, headers=ORIGIN
    )
    assert me.status_code == 422
    inv = await client.post(
        f"/api/v1/notes/{nid}/collaborators",
        json={"email": "Bob@Example.com", "role": "viewer"},
        headers=ORIGIN,
    )
    assert inv.status_code == 201, inv.text
    collab = inv.json()["data"]
    assert collab["email"] == "bob@example.com" and collab["user_id"] is None
    detail = (await client.get(f"/api/v1/notes/{nid}")).json()["data"]
    assert detail["shared"] is True and detail["access"] == "owner"
    assert [c["email"] for c in detail["collaborators"]] == ["bob@example.com"]

    # Bob signs up: the pending invite binds to his new account, so the note is his to view.
    await client.post("/api/v1/auth/logout", headers=ORIGIN)
    await signup(client, email="bob@example.com")
    assert (await client.get(f"/api/v1/notes/{nid}")).json()["data"]["access"] == "viewer"

    await client.post("/api/v1/auth/logout", headers=ORIGIN)
    await client.post(
        "/api/v1/auth/login",
        json={"email": "owner@example.com", "password": "correct horse battery"},
        headers=ORIGIN,
    )
    promoted = await client.post(
        f"/api/v1/notes/{nid}/collaborators",
        json={"email": "bob@example.com", "role": "viewer"},
        headers=ORIGIN,
    )
    assert promoted.json()["data"]["role"] == "viewer"
    assert promoted.json()["data"]["user_id"]

    await client.post("/api/v1/auth/logout", headers=ORIGIN)
    await client.post(
        "/api/v1/auth/login",
        json={"email": "bob@example.com", "password": "correct horse battery"},
        headers=ORIGIN,
    )
    as_bob = (await client.get(f"/api/v1/notes/{nid}")).json()["data"]
    assert as_bob["access"] == "viewer" and as_bob["title"] == "Team plan"
    assert await titles(client, "shared") == ["Team plan"]
    assert await titles(client, "active") == []
    denied = await client.patch(f"/api/v1/notes/{nid}", json={"title": "Hacked"}, headers=ORIGIN)
    assert denied.status_code == 409 and denied.json()["error"]["code"] == "NOTE_READ_ONLY"
    inbox = (await client.get("/api/v1/notifications")).json()["data"]
    assert [n["kind"] for n in inbox["items"]] == ["note_shared"]

    # Owner promotes Bob to editor; Bob edits; owner removes him and the note disappears for Bob.
    await client.post("/api/v1/auth/logout", headers=ORIGIN)
    await client.post(
        "/api/v1/auth/login",
        json={"email": "owner@example.com", "password": "correct horse battery"},
        headers=ORIGIN,
    )
    cid = promoted.json()["data"]["id"]
    assert (
        await client.patch(
            f"/api/v1/notes/{nid}/collaborators/{cid}", json={"role": "editor"}, headers=ORIGIN
        )
    ).json()["data"]["role"] == "editor"
    await client.post("/api/v1/auth/logout", headers=ORIGIN)
    await client.post(
        "/api/v1/auth/login",
        json={"email": "bob@example.com", "password": "correct horse battery"},
        headers=ORIGIN,
    )
    ok_edit = await client.patch(
        f"/api/v1/notes/{nid}", json={"title": "Team plan v2"}, headers=ORIGIN
    )
    assert ok_edit.status_code == 200
    await client.post("/api/v1/auth/logout", headers=ORIGIN)
    await client.post(
        "/api/v1/auth/login",
        json={"email": "owner@example.com", "password": "correct horse battery"},
        headers=ORIGIN,
    )
    removed = await client.delete(f"/api/v1/notes/{nid}/collaborators/{cid}", headers=ORIGIN)
    assert removed.json()["data"] == {"removed": True}
    assert (await client.get(f"/api/v1/notes/{nid}")).json()["data"]["shared"] is False
