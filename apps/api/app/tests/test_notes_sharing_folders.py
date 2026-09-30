"""Folders and sharing between real accounts: filing is the owner's, access is enforced."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.main import create_app
from app.tests.conftest import ORIGIN, signup


@pytest.fixture
async def bob() -> AsyncIterator[AsyncClient]:
    """A second person in their own browser."""
    transport = ASGITransport(app=create_app(get_settings()))
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        await signup(c, email="bob@example.com")
        yield c


async def note(client: AsyncClient, title: str, **extra: Any) -> dict[str, Any]:
    resp = await client.post("/api/v1/notes", json={"title": title, **extra}, headers=ORIGIN)
    assert resp.status_code == 201, resp.text
    data: dict[str, Any] = resp.json()["data"]
    return data


async def folder(client: AsyncClient, name: str) -> str:
    resp = await client.post("/api/v1/folders", json={"name": name}, headers=ORIGIN)
    assert resp.status_code == 201, resp.text
    return str(resp.json()["data"]["id"])


async def in_folder(client: AsyncClient, folder_id: str) -> list[str]:
    resp = await client.get("/api/v1/notes", params={"folder_id": folder_id})
    return [n["title"] for n in resp.json()["data"]]


async def share(client: AsyncClient, note_id: str, email: str, role: str = "viewer") -> Any:
    return await client.post(
        f"/api/v1/notes/{note_id}/collaborators",
        json={"email": email, "role": role},
        headers=ORIGIN,
    )


# --- folders ------------------------------------------------------------------------------------


async def test_move_between_folders_and_back(client: AsyncClient) -> None:
    await signup(client, email="ada@example.com")
    work, home = await folder(client, "Work"), await folder(client, "Home")
    n = await note(client, "Plan")

    moved = await client.patch(f"/api/v1/notes/{n['id']}", json={"folder_id": work}, headers=ORIGIN)
    assert moved.json()["data"]["folder_id"] == work
    assert await in_folder(client, work) == ["Plan"]

    await client.patch(f"/api/v1/notes/{n['id']}", json={"folder_id": home}, headers=ORIGIN)
    assert await in_folder(client, work) == []
    assert await in_folder(client, home) == ["Plan"]
    counts = {f["name"]: f["note_count"] for f in (await client.get("/api/v1/folders")).json()["data"]}
    assert counts == {"Home": 1, "Work": 0}

    out = await client.patch(f"/api/v1/notes/{n['id']}", json={"clear_folder": True}, headers=ORIGIN)
    assert out.json()["data"]["folder_id"] is None
    assert (await client.get(f"/api/v1/notes/{n['id']}")).json()["data"]["folder_id"] is None


async def test_moving_into_a_deleted_or_foreign_folder_is_refused(
    client: AsyncClient, bob: AsyncClient
) -> None:
    await signup(client, email="ada@example.com")
    gone = await folder(client, "Old")
    n = await note(client, "Plan", folder_id=gone)
    await client.delete(f"/api/v1/folders/{gone}", headers=ORIGIN)
    # Deleting a folder keeps its notes, now unfiled.
    assert (await client.get(f"/api/v1/notes/{n['id']}")).json()["data"]["folder_id"] is None
    resp = await client.patch(f"/api/v1/notes/{n['id']}", json={"folder_id": gone}, headers=ORIGIN)
    assert resp.status_code == 404 and resp.json()["error"]["code"] == "FOLDER_NOT_FOUND"
    bobs = await folder(bob, "Bob's")
    resp = await client.patch(f"/api/v1/notes/{n['id']}", json={"folder_id": bobs}, headers=ORIGIN)
    assert resp.status_code == 404


async def test_bulk_move_is_atomic_and_skips_foreign_notes(
    client: AsyncClient, bob: AsyncClient
) -> None:
    await signup(client, email="ada@example.com")
    work = await folder(client, "Work")
    mine = [(await note(client, f"N{i}"))["id"] for i in range(3)]
    theirs = (await note(bob, "Bob's note"))["id"]
    resp = await client.post(
        "/api/v1/notes/bulk/move",
        json={"ids": [*mine, mine[0], theirs], "folder_id": work},
        headers=ORIGIN,
    )
    assert resp.json()["data"] == {"moved": 3}
    assert sorted(await in_folder(client, work)) == ["N0", "N1", "N2"]
    assert (await bob.get(f"/api/v1/notes/{theirs}")).json()["data"]["folder_id"] is None
    back = await client.post(
        "/api/v1/notes/bulk/move", json={"ids": mine, "folder_id": None}, headers=ORIGIN
    )
    assert back.json()["data"] == {"moved": 3}
    assert await in_folder(client, work) == []


async def test_only_the_owner_files_a_shared_note(client: AsyncClient, bob: AsyncClient) -> None:
    await signup(client, email="ada@example.com")
    work = await folder(client, "Work")
    n = await note(client, "Shared plan", folder_id=work)
    assert (await share(client, n["id"], "bob@example.com", "editor")).status_code == 201

    as_bob = (await bob.get(f"/api/v1/notes/{n['id']}")).json()["data"]
    assert as_bob["folder_id"] is None  # the owner's folder is theirs alone
    bobs = await folder(bob, "Mine")
    refused = await bob.patch(f"/api/v1/notes/{n['id']}", json={"folder_id": bobs}, headers=ORIGIN)
    assert refused.status_code == 403 and refused.json()["error"]["code"] == "NOT_OWNER"
    refused = await bob.patch(
        f"/api/v1/notes/{n['id']}", json={"clear_folder": True}, headers=ORIGIN
    )
    assert refused.status_code == 403
    # Editing the content is still fine for an editor, and the owner's folder is untouched.
    assert (
        await bob.patch(f"/api/v1/notes/{n['id']}", json={"title": "Plan v2"}, headers=ORIGIN)
    ).status_code == 200
    assert await in_folder(client, work) == ["Plan v2"]


# --- sharing ------------------------------------------------------------------------------------


async def test_sharing_with_an_account_gives_access_immediately(
    client: AsyncClient, bob: AsyncClient
) -> None:
    await signup(client, email="ada@example.com")
    n = await note(client, "Roadmap")
    resp = await share(client, n["id"], "BOB@example.com", "editor")
    assert resp.status_code == 201
    person = resp.json()["data"]["collaborator"]
    assert person["status"] == "accepted" and person["display_name"] == "Ada"  # signup name

    shared = (await bob.get("/api/v1/notes", params={"view": "shared"})).json()["data"]
    assert [x["title"] for x in shared] == ["Roadmap"]
    detail = (await bob.get(f"/api/v1/notes/{n['id']}")).json()["data"]
    assert detail["access"] == "editor"
    assert detail["owner"]["email"] == "ada@example.com"
    # Already has access: a second invite is refused rather than duplicated.
    again = await share(client, n["id"], "bob@example.com")
    assert again.status_code == 409 and again.json()["error"]["code"] == "INVITE_ALREADY_ACCEPTED"
    assert len((await client.get(f"/api/v1/notes/{n['id']}")).json()["data"]["collaborators"]) == 1


async def test_permissions_are_enforced_server_side(client: AsyncClient, bob: AsyncClient) -> None:
    await signup(client, email="ada@example.com")
    n = await note(client, "Budget")
    await share(client, n["id"], "bob@example.com", "viewer")
    nid = n["id"]

    assert (await bob.patch(f"/api/v1/notes/{nid}", json={"title": "x"}, headers=ORIGIN)).json()[
        "error"
    ]["code"] == "NOTE_READ_ONLY"
    # Neither a viewer nor an editor can trash, restore, delete forever or re-share.
    for method, path, body in (
        ("DELETE", f"/api/v1/notes/{nid}", None),
        ("POST", f"/api/v1/notes/{nid}/restore", None),
        ("DELETE", f"/api/v1/notes/{nid}/permanent", None),
        ("POST", f"/api/v1/notes/{nid}/collaborators", {"email": "eve@example.com"}),
    ):
        resp = await bob.request(method, path, json=body, headers=ORIGIN)
        assert resp.status_code == 403, (path, resp.text)
        assert resp.json()["error"]["code"] == "NOTE_NOT_OWNER"
    people = (await client.get(f"/api/v1/notes/{nid}")).json()["data"]["collaborators"]
    promote = await bob.patch(
        f"/api/v1/notes/{nid}/collaborators/{people[0]['id']}",
        json={"role": "editor"},
        headers=ORIGIN,
    )
    assert promote.status_code == 403
    assert (await client.get(f"/api/v1/notes/{nid}")).json()["data"]["deleted_at"] is None

    # A guest's copy is theirs, without the owner's folder or tags.
    copy = (await bob.post(f"/api/v1/notes/{nid}/duplicate", headers=ORIGIN)).json()["data"]
    assert copy["access"] == "owner" and copy["folder_id"] is None and copy["tags"] == []


async def test_revoking_access_takes_effect_immediately(
    client: AsyncClient, bob: AsyncClient
) -> None:
    await signup(client, email="ada@example.com")
    n = await note(client, "Secret")
    person = (await share(client, n["id"], "bob@example.com", "editor")).json()["data"][
        "collaborator"
    ]
    assert (await bob.get(f"/api/v1/notes/{n['id']}")).status_code == 200
    removed = await client.delete(
        f"/api/v1/notes/{n['id']}/collaborators/{person['id']}", headers=ORIGIN
    )
    assert removed.json()["data"] == {"removed": True}
    assert (await bob.get(f"/api/v1/notes/{n['id']}")).status_code == 404
    assert (
        await bob.patch(f"/api/v1/notes/{n['id']}", json={"title": "x"}, headers=ORIGIN)
    ).status_code == 404
    assert (await bob.get("/api/v1/notes", params={"view": "shared"})).json()["data"] == []


async def test_share_suggestions_only_come_from_existing_shares(
    client: AsyncClient, bob: AsyncClient
) -> None:
    await signup(client, email="ada@example.com")
    n = await note(client, "Plan")
    assert (await client.get("/api/v1/notes/share-suggestions")).json()["data"] == []
    await share(client, n["id"], "bob@example.com")
    await share(client, n["id"], "carol@example.com")  # no account yet: still suggested
    found = (await client.get("/api/v1/notes/share-suggestions", params={"q": "bo"})).json()
    assert found["data"] == [{"email": "bob@example.com", "display_name": "Ada"}]
    # Bob sees Ada (who shared with him), never unrelated accounts.
    back = (await bob.get("/api/v1/notes/share-suggestions")).json()["data"]
    assert [p["email"] for p in back] == ["ada@example.com"]
