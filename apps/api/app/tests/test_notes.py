from __future__ import annotations

from typing import Any

from httpx import AsyncClient

from app.services.rich_text import to_plain_text
from app.tests.conftest import ORIGIN, signup


def doc(*paragraphs: str) -> dict[str, Any]:
    return {
        "type": "doc",
        "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": p}]} for p in paragraphs
        ],
    }


async def create_note(
    client: AsyncClient, title: str = "Launch plan", *paras: str
) -> dict[str, Any]:
    resp = await client.post(
        "/api/v1/notes",
        json={"title": title, "content_json": doc(*paras) if paras else None},
        headers=ORIGIN,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


def test_plain_text_extraction() -> None:
    d = {
        "type": "doc",
        "content": [
            {
                "type": "heading",
                "attrs": {"level": 1},
                "content": [{"type": "text", "text": "Title"}],
            },
            {
                "type": "bulletList",
                "content": [
                    {
                        "type": "listItem",
                        "content": [
                            {"type": "paragraph", "content": [{"type": "text", "text": "one"}]}
                        ],
                    },
                    {
                        "type": "listItem",
                        "content": [
                            {
                                "type": "paragraph",
                                "content": [
                                    {"type": "text", "text": "two"},
                                    {"type": "hardBreak"},
                                    {"type": "text", "text": "three"},
                                ],
                            }
                        ],
                    },
                ],
            },
            {"type": "paragraph"},
        ],
    }
    assert to_plain_text(d) == "Title\none\ntwo\nthree"
    assert to_plain_text(None) == ""
    assert to_plain_text({"type": "doc"}) == ""


async def test_create_get_list_note(client: AsyncClient) -> None:
    await signup(client)
    note = await create_note(client, "Launch plan", "Ship pricing page", "Email the team")
    assert note["plain_text"] == "Ship pricing page\nEmail the team"
    assert note["version"] == 1
    assert note["tags"] == []

    got = await client.get(f"/api/v1/notes/{note['id']}")
    assert got.status_code == 200
    assert got.json()["data"]["content_json"]["type"] == "doc"

    listed = await client.get("/api/v1/notes")
    rows = listed.json()["data"]
    assert [r["id"] for r in rows] == [note["id"]]
    assert rows[0]["excerpt"].startswith("Ship pricing page")
    assert "content_json" not in rows[0]
    assert listed.json()["meta"]["next_cursor"] is None


async def test_empty_note_defaults_to_empty_doc(client: AsyncClient) -> None:
    await signup(client)
    note = await create_note(client, "")
    assert note["content_json"] == {"type": "doc", "content": [{"type": "paragraph"}]}
    assert note["plain_text"] == ""


async def test_invalid_doc_rejected(client: AsyncClient) -> None:
    await signup(client)
    resp = await client.post(
        "/api/v1/notes", json={"title": "x", "content_json": {"type": "paragraph"}}, headers=ORIGIN
    )
    assert resp.status_code == 422
    assert "content_json" in resp.json()["error"]["details"]["fields"]


async def test_autosave_versioning_and_conflict(client: AsyncClient) -> None:
    await signup(client)
    note = await create_note(client, "Draft")
    resp = await client.patch(
        f"/api/v1/notes/{note['id']}",
        json={"content_json": doc("v2"), "expected_version": 1},
        headers=ORIGIN,
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["version"] == 2
    assert resp.json()["data"]["plain_text"] == "v2"

    stale = await client.patch(
        f"/api/v1/notes/{note['id']}",
        json={"content_json": doc("from another tab"), "expected_version": 1},
        headers=ORIGIN,
    )
    assert stale.status_code == 409
    body = stale.json()["error"]
    assert body["code"] == "NOTE_VERSION_CONFLICT"
    assert body["details"]["current_version"] == 2

    # Metadata-only changes don't bump the content version.
    fav = await client.patch(
        f"/api/v1/notes/{note['id']}", json={"is_favorite": True}, headers=ORIGIN
    )
    assert fav.json()["data"]["version"] == 2
    assert fav.json()["data"]["is_favorite"] is True


async def test_views_archive_trash_restore_purge(client: AsyncClient) -> None:
    await signup(client)
    a = await create_note(client, "A")
    b = await create_note(client, "B")
    nid = a["id"]

    await client.patch(f"/api/v1/notes/{nid}", json={"archived": True}, headers=ORIGIN)
    assert [n["id"] for n in (await client.get("/api/v1/notes")).json()["data"]] == [b["id"]]
    archived = (await client.get("/api/v1/notes", params={"view": "archived"})).json()["data"]
    assert [n["id"] for n in archived] == [nid]

    assert (await client.delete(f"/api/v1/notes/{nid}", headers=ORIGIN)).status_code == 200
    trash = (await client.get("/api/v1/notes", params={"view": "trash"})).json()["data"]
    assert [n["id"] for n in trash] == [nid]
    # Editing a trashed note is refused.
    edit = await client.patch(f"/api/v1/notes/{nid}", json={"title": "x"}, headers=ORIGIN)
    assert edit.status_code == 409 and edit.json()["error"]["code"] == "NOTE_IN_TRASH"
    # Purging a live note is refused.
    assert (
        await client.delete(f"/api/v1/notes/{b['id']}/permanent", headers=ORIGIN)
    ).status_code == 409

    restored = await client.post(f"/api/v1/notes/{nid}/restore", headers=ORIGIN)
    assert restored.json()["data"]["deleted_at"] is None

    await client.delete(f"/api/v1/notes/{nid}", headers=ORIGIN)
    assert (
        await client.delete(f"/api/v1/notes/{nid}/permanent", headers=ORIGIN)
    ).status_code == 200
    assert (await client.get(f"/api/v1/notes/{nid}")).status_code == 404


async def test_duplicate_note_copies_content_and_tags(client: AsyncClient) -> None:
    await signup(client)
    tag = (await client.post("/api/v1/tags", json={"name": "work"}, headers=ORIGIN)).json()["data"]
    note = await create_note(client, "Original", "body")
    await client.patch(f"/api/v1/notes/{note['id']}", json={"tag_ids": [tag["id"]]}, headers=ORIGIN)
    dup = await client.post(f"/api/v1/notes/{note['id']}/duplicate", headers=ORIGIN)
    assert dup.status_code == 201
    data = dup.json()["data"]
    assert data["title"] == "Original (copy)"
    assert data["plain_text"] == "body"
    assert [t["id"] for t in data["tags"]] == [tag["id"]]
    assert data["metadata"]["duplicated_from"] == note["id"]


async def test_folders_crud_and_note_assignment(client: AsyncClient) -> None:
    await signup(client)
    folder = (
        await client.post("/api/v1/folders", json={"name": "Projects"}, headers=ORIGIN)
    ).json()["data"]
    dup = await client.post("/api/v1/folders", json={"name": " projects "}, headers=ORIGIN)
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "FOLDER_NAME_TAKEN"
    child = (
        await client.post(
            "/api/v1/folders", json={"name": "Q4", "parent_id": folder["id"]}, headers=ORIGIN
        )
    ).json()["data"]

    # Cycle protection.
    cycle = await client.patch(
        f"/api/v1/folders/{folder['id']}", json={"parent_id": child["id"]}, headers=ORIGIN
    )
    assert cycle.status_code == 422

    note = await create_note(client, "In folder")
    moved = await client.patch(
        f"/api/v1/notes/{note['id']}", json={"folder_id": child["id"]}, headers=ORIGIN
    )
    assert moved.json()["data"]["folder_id"] == child["id"]
    folders = (await client.get("/api/v1/folders")).json()["data"]
    counts = {f["name"]: f["note_count"] for f in folders}
    assert counts == {"Projects": 0, "Q4": 1}

    in_folder = (await client.get("/api/v1/notes", params={"folder_id": child["id"]})).json()[
        "data"
    ]
    assert [n["id"] for n in in_folder] == [note["id"]]

    cleared = await client.patch(
        f"/api/v1/notes/{note['id']}", json={"clear_folder": True}, headers=ORIGIN
    )
    assert cleared.json()["data"]["folder_id"] is None

    # Deleting a folder keeps its notes.
    await client.patch(
        f"/api/v1/notes/{note['id']}", json={"folder_id": folder["id"]}, headers=ORIGIN
    )
    assert (
        await client.delete(f"/api/v1/folders/{folder['id']}", headers=ORIGIN)
    ).status_code == 200
    still = await client.get(f"/api/v1/notes/{note['id']}")
    assert still.status_code == 200 and still.json()["data"]["folder_id"] is None
    assert (await client.get("/api/v1/folders")).json()["data"] == []  # child cascaded


async def test_tags_crud_and_filtering(client: AsyncClient) -> None:
    await signup(client)
    bad = await client.post("/api/v1/tags", json={"name": "x", "color": "red"}, headers=ORIGIN)
    assert bad.status_code == 422
    t1 = (
        await client.post("/api/v1/tags", json={"name": "Work", "color": "#22C55E"}, headers=ORIGIN)
    ).json()["data"]
    assert t1["color"] == "#22c55e"
    assert (
        await client.post("/api/v1/tags", json={"name": "work"}, headers=ORIGIN)
    ).status_code == 409
    t2 = (await client.post("/api/v1/tags", json={"name": "Ideas"}, headers=ORIGIN)).json()["data"]

    n1 = await create_note(client, "Tagged")
    n2 = await create_note(client, "Other")
    await client.patch(
        f"/api/v1/notes/{n1['id']}", json={"tag_ids": [t1["id"], t2["id"]]}, headers=ORIGIN
    )
    await client.patch(f"/api/v1/notes/{n2['id']}", json={"tag_ids": [t2["id"]]}, headers=ORIGIN)

    tags = (await client.get("/api/v1/tags")).json()["data"]
    assert {t["name"]: t["note_count"] for t in tags} == {"Ideas": 2, "Work": 1}
    by_tag = (await client.get("/api/v1/notes", params={"tag_id": t1["id"]})).json()["data"]
    assert [n["id"] for n in by_tag] == [n1["id"]]

    renamed = await client.patch(f"/api/v1/tags/{t1['id']}", json={"name": "Job"}, headers=ORIGIN)
    assert renamed.json()["data"]["name"] == "Job"
    assert (await client.delete(f"/api/v1/tags/{t2['id']}", headers=ORIGIN)).status_code == 200
    note = (await client.get(f"/api/v1/notes/{n1['id']}")).json()["data"]
    assert [t["name"] for t in note["tags"]] == ["Job"]


async def test_search_and_list_filter(client: AsyncClient) -> None:
    await signup(client)
    a = await create_note(client, "Q4 launch", "Pricing discussion with sales")
    await create_note(client, "Grocery list", "milk, eggs")
    b = await create_note(client, "Untitled", "the launch retro went well")

    resp = await client.get("/api/v1/search", params={"q": "launch"})
    body = resp.json()["data"]
    ids = {h["id"] for h in body["hits"]}
    assert ids == {a["id"], b["id"]}
    assert body["sources"] == ["notely"]
    assert all(h["source"] == "notely" and h["url"].startswith("/app/notes/") for h in body["hits"])
    assert (await client.get("/api/v1/search", params={"q": ""})).status_code == 422

    filtered = (await client.get("/api/v1/notes", params={"q": "eggs"})).json()["data"]
    assert [n["title"] for n in filtered] == ["Grocery list"]


async def test_pagination_cursor(client: AsyncClient) -> None:
    await signup(client)
    for i in range(5):
        await create_note(client, f"Note {i}")
    page1 = await client.get("/api/v1/notes", params={"limit": 2})
    rows1 = page1.json()["data"]
    cursor = page1.json()["meta"]["next_cursor"]
    assert len(rows1) == 2 and cursor
    page2 = await client.get("/api/v1/notes", params={"limit": 2, "cursor": cursor})
    rows2 = page2.json()["data"]
    assert len(rows2) == 2
    assert {r["id"] for r in rows1}.isdisjoint({r["id"] for r in rows2})
    page3 = await client.get(
        "/api/v1/notes", params={"limit": 2, "cursor": page2.json()["meta"]["next_cursor"]}
    )
    assert len(page3.json()["data"]) == 1
    assert page3.json()["meta"]["next_cursor"] is None


async def test_tenant_isolation(client: AsyncClient) -> None:
    await signup(client, "ada@example.com")
    note = await create_note(client, "Ada's secret", "confidential")
    folder = (
        await client.post("/api/v1/folders", json={"name": "Private"}, headers=ORIGIN)
    ).json()["data"]
    tag = (await client.post("/api/v1/tags", json={"name": "secret"}, headers=ORIGIN)).json()[
        "data"
    ]

    client.cookies.clear()
    await signup(client, "bob@example.com")
    assert (await client.get(f"/api/v1/notes/{note['id']}")).status_code == 404
    assert (
        await client.patch(f"/api/v1/notes/{note['id']}", json={"title": "pwned"}, headers=ORIGIN)
    ).status_code == 404
    assert (await client.delete(f"/api/v1/notes/{note['id']}", headers=ORIGIN)).status_code == 404
    assert (await client.get("/api/v1/notes")).json()["data"] == []
    assert (await client.get("/api/v1/search", params={"q": "confidential"})).json()["data"][
        "hits"
    ] == []
    assert (
        await client.delete(f"/api/v1/folders/{folder['id']}", headers=ORIGIN)
    ).status_code == 404
    # Bob cannot attach Ada's folder or tag to his own note.
    mine = await create_note(client, "Bob")
    assert (
        await client.patch(
            f"/api/v1/notes/{mine['id']}", json={"folder_id": folder["id"]}, headers=ORIGIN
        )
    ).status_code == 404
    assert (
        await client.patch(
            f"/api/v1/notes/{mine['id']}", json={"tag_ids": [tag["id"]]}, headers=ORIGIN
        )
    ).status_code == 404


async def test_notes_require_auth(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/notes")).status_code == 401
    assert (
        await client.post("/api/v1/notes", json={"title": "x"}, headers=ORIGIN)
    ).status_code == 401
