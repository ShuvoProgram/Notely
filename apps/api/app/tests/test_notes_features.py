"""Notes: stable ordering, version history, colour, reminders and collaboration."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select

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
    collab = inv.json()["data"]["collaborator"]
    assert collab["email"] == "bob@example.com" and collab["user_id"] is None
    assert collab["status"] == "pending" and collab["invite_expires_at"]
    # No SMTP in tests: the API says so instead of pretending the email went out.
    delivery = inv.json()["data"]["delivery"]
    assert delivery["sent"] is False and "SMTP_HOST" in delivery["error"]
    # A second click does not create or send a second invitation.
    again = await client.post(
        f"/api/v1/notes/{nid}/collaborators", json={"email": "bob@example.com"}, headers=ORIGIN
    )
    assert again.status_code == 409 and again.json()["error"]["code"] == "INVITE_ALREADY_SENT"
    resent = await client.post(
        f"/api/v1/notes/{nid}/collaborators",
        json={"email": "bob@example.com", "resend": True},
        headers=ORIGIN,
    )
    assert resent.status_code == 201
    assert resent.json()["data"]["collaborator"]["id"] == collab["id"]
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
    # Signing up accepted the invitation; inviting again is refused, roles change via PATCH.
    dup = await client.post(
        f"/api/v1/notes/{nid}/collaborators",
        json={"email": "bob@example.com", "role": "viewer"},
        headers=ORIGIN,
    )
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "INVITE_ALREADY_ACCEPTED"
    people = (await client.get(f"/api/v1/notes/{nid}")).json()["data"]["collaborators"]
    assert people[0]["status"] == "accepted" and people[0]["user_id"]
    cid = people[0]["id"]

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


async def test_invitation_link_accept_expiry_and_wrong_account(
    client: Any, monkeypatch: Any
) -> None:
    from app.core import mailer

    sent: list[tuple[str, str]] = []

    async def fake_send(to: str, subject: str, text: str, html: str | None = None) -> Any:
        sent.append((to, subject))
        assert "/invite/" in text and html and "Open the note" in html
        return mailer.Delivery.ok()

    monkeypatch.setattr("app.services.note_service.mailer.send", fake_send)
    await signup(client, email="owner@example.com")
    note = await make(client, "Launch checklist")
    nid = note["id"]
    inv = await client.post(
        f"/api/v1/notes/{nid}/collaborators",
        json={"email": "cara@example.com", "role": "editor"},
        headers=ORIGIN,
    )
    assert inv.status_code == 201 and inv.json()["data"]["delivery"] == {
        "sent": True,
        "error": None,
    }
    assert sent == [("cara@example.com", "Ada shared \u201cLaunch checklist\u201d with you")]

    # The link is public to *describe*, but accepting needs the invited account.
    from app.db.session import get_session_factory
    from app.models.note import NoteCollaborator

    async with get_session_factory()() as db:
        row = await db.scalar(
            select(NoteCollaborator).where(NoteCollaborator.email == "cara@example.com")
        )
        assert row is not None and row.invite_token
        token = row.invite_token
    public = await client.get(f"/api/v1/invitations/{token}")
    assert public.status_code == 200
    assert public.json()["data"]["note_title"] == "Launch checklist"
    assert public.json()["data"]["status"] == "pending"
    assert (await client.get("/api/v1/invitations/nope")).status_code == 404

    wrong = await client.post(f"/api/v1/invitations/{token}/accept", headers=ORIGIN)
    assert wrong.status_code == 403 and wrong.json()["error"]["code"] == "INVITE_WRONG_ACCOUNT"

    await client.post("/api/v1/auth/logout", headers=ORIGIN)
    await signup(client, email="dave@example.com")
    assert (
        await client.post(f"/api/v1/invitations/{token}/accept", headers=ORIGIN)
    ).status_code == 403

    # Expired links are refused with a distinct code so the UI can offer "ask to resend".
    async with get_session_factory()() as db:
        row = await db.scalar(
            select(NoteCollaborator).where(NoteCollaborator.email == "cara@example.com")
        )
        assert row is not None
        row.invite_expires_at = datetime.now(UTC) - timedelta(minutes=1)
        await db.commit()
    assert (await client.get(f"/api/v1/invitations/{token}")).json()["data"]["status"] == "expired"
    await client.post("/api/v1/auth/logout", headers=ORIGIN)
    await client.post(
        "/api/v1/auth/login",
        json={"email": "owner@example.com", "password": "correct horse battery"},
        headers=ORIGIN,
    )
    detail = (await client.get(f"/api/v1/notes/{nid}")).json()["data"]
    assert detail["collaborators"][0]["status"] == "expired"
    # Owner resends: new token, new expiry.
    resent = await client.post(
        f"/api/v1/notes/{nid}/collaborators",
        json={"email": "cara@example.com", "role": "editor", "resend": True},
        headers=ORIGIN,
    )
    assert resent.status_code == 201 and len(sent) == 2
    async with get_session_factory()() as db:
        row = await db.scalar(
            select(NoteCollaborator).where(NoteCollaborator.email == "cara@example.com")
        )
        assert row is not None and row.invite_token and row.invite_token != token
        token2 = row.invite_token
    assert (await client.get(f"/api/v1/invitations/{token}")).status_code == 404  # old link dead

    # Cara accepts with the right account and can edit; the link is single-use.
    await client.post("/api/v1/auth/logout", headers=ORIGIN)
    await signup(client, email="cara@example.com")  # signup binds + accepts
    assert (await client.get(f"/api/v1/notes/{nid}")).json()["data"]["access"] == "editor"
    assert (await client.get(f"/api/v1/invitations/{token2}")).status_code == 404


async def test_custom_colours_and_bulk_trash(client: Any) -> None:
    await signup(client)
    a = await make(client, "A")
    b = await make(client, "B")
    c = await make(client, "C")
    ok_hex = await client.patch(
        f"/api/v1/notes/{a['id']}", json={"color": "#3B82F6"}, headers=ORIGIN
    )
    assert ok_hex.status_code == 200 and ok_hex.json()["data"]["color"] == "#3b82f6"
    preset = await client.patch(
        f"/api/v1/notes/{a['id']}", json={"color": "lavender"}, headers=ORIGIN
    )
    assert preset.json()["data"]["color"] == "lavender"
    bad = await client.patch(f"/api/v1/notes/{a['id']}", json={"color": "red"}, headers=ORIGIN)
    assert bad.status_code == 422

    moved = await client.post(
        "/api/v1/notes/bulk/trash",
        json={"ids": [a["id"], b["id"], b["id"], "00000000-0000-0000-0000-000000000000"]},
        headers=ORIGIN,
    )
    assert moved.status_code == 200 and moved.json()["data"] == {"moved": 2}
    assert await titles(client, "active") == ["C"]
    assert sorted(await titles(client, "trash")) == ["A", "B"]
    assert c["id"]


async def test_bulk_delete_tasks(client: Any) -> None:
    await signup(client)
    ids = []
    for t in ("one", "two", "three"):
        r = await client.post("/api/v1/tasks", json={"title": t}, headers=ORIGIN)
        ids.append(r.json()["data"]["id"])
    r = await client.post("/api/v1/tasks/bulk/delete", json={"ids": ids[:2]}, headers=ORIGIN)
    assert r.status_code == 200 and r.json()["data"] == {"deleted": 2}
    left = (await client.get("/api/v1/tasks")).json()["data"]
    assert [t["title"] for t in left] == ["three"]
