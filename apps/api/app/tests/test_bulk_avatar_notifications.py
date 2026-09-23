from __future__ import annotations

import io
from typing import Any

from PIL import Image
from sqlalchemy import select

from app.db.session import get_session_factory
from app.models.notification import Notification, NotificationKind
from app.models.user import User
from app.tests.conftest import ORIGIN, signup


async def make(client: Any, title: str) -> str:
    resp = await client.post("/api/v1/notes", json={"title": title}, headers=ORIGIN)
    assert resp.status_code == 201, resp.text
    return str(resp.json()["data"]["id"])


async def view(client: Any, name: str) -> list[str]:
    data = (await client.get(f"/api/v1/notes?view={name}")).json()["data"]
    items = data["items"] if isinstance(data, dict) else data
    return [n["title"] for n in items]


async def test_bulk_restore_and_purge_only_touch_trashed_notes(client: Any) -> None:
    await signup(client)
    a, b, live = await make(client, "A"), await make(client, "B"), await make(client, "Live")
    await client.post("/api/v1/notes/bulk/trash", json={"ids": [a, b]}, headers=ORIGIN)
    assert sorted(await view(client, "trash")) == ["A", "B"]

    restored = await client.post("/api/v1/notes/bulk/restore", json={"ids": [a]}, headers=ORIGIN)
    assert restored.json()["data"] == {"restored": 1}
    assert await view(client, "trash") == ["B"]

    # A stale selection that includes a live note never deletes it permanently.
    purged = await client.post(
        "/api/v1/notes/bulk/purge", json={"ids": [b, live, a]}, headers=ORIGIN
    )
    assert purged.json()["data"] == {"deleted": 1}
    assert await view(client, "trash") == []
    assert sorted(await view(client, "active")) == ["A", "Live"]


async def test_bulk_leave_drops_only_the_callers_access(client: Any) -> None:
    await signup(client, email="owner@example.com")
    nid = await make(client, "Team plan")
    await client.post(
        f"/api/v1/notes/{nid}/collaborators", json={"email": "bob@example.com"}, headers=ORIGIN
    )
    await client.post("/api/v1/auth/logout", headers=ORIGIN)
    await signup(client, email="bob@example.com")
    assert await view(client, "shared") == ["Team plan"]

    # Bob can't trash or purge the owner's note; he can leave it.
    await client.post("/api/v1/notes/bulk/trash", json={"ids": [nid]}, headers=ORIGIN)
    left = await client.post("/api/v1/notes/bulk/leave", json={"ids": [nid]}, headers=ORIGIN)
    assert left.json()["data"] == {"left": 1}
    assert await view(client, "shared") == []
    assert (await client.get(f"/api/v1/notes/{nid}")).status_code == 404


async def test_dismissed_notifications_leave_the_inbox_and_stay_gone(client: Any) -> None:
    await signup(client)
    async with get_session_factory()() as db:
        user = (await db.execute(select(User))).scalar_one()
        for i in range(2):
            db.add(
                Notification(
                    tenant_id=user.tenant_id,
                    user_id=user.id,
                    kind=NotificationKind.automation,
                    title=f"Run {i}",
                    dedupe_key=f"test:{i}",
                )
            )
        await db.commit()
    inbox = (await client.get("/api/v1/notifications")).json()["data"]
    assert inbox["unread"] == 2
    first = inbox["items"][0]["id"]

    await client.post(f"/api/v1/notifications/{first}/read", headers=ORIGIN)
    again = await client.post(f"/api/v1/notifications/{first}/unread", headers=ORIGIN)
    assert again.json()["data"]["read_at"] is None

    gone = await client.delete(f"/api/v1/notifications/{first}", headers=ORIGIN)
    assert gone.json()["data"] == {"dismissed": True}
    inbox = (await client.get("/api/v1/notifications")).json()["data"]
    assert [n["id"] for n in inbox["items"]] != [] and first not in [
        n["id"] for n in inbox["items"]
    ]
    assert inbox["unread"] == 1
    # Dismissed items can't be acted on again.
    assert (
        await client.post(f"/api/v1/notifications/{first}/read", headers=ORIGIN)
    ).status_code == 404


def png(width: int = 600, height: int = 400, colour: tuple[int, int, int] = (40, 160, 90)) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (width, height), colour).save(out, format="PNG")
    return out.getvalue()


async def test_avatar_upload_replace_serve_and_remove(client: Any) -> None:
    user = await signup(client)
    assert user["avatar_url"] is None

    up = await client.put(
        "/api/v1/users/me/avatar", files={"file": ("me.png", png(), "image/png")}, headers=ORIGIN
    )
    assert up.status_code == 200, up.text
    url = up.json()["data"]["avatar_url"]
    assert url.startswith(f"/api/v1/users/{user['id']}/avatar?v=")

    served = await client.get(url)
    assert served.status_code == 200 and served.headers["content-type"] == "image/webp"
    with Image.open(io.BytesIO(served.content)) as img:
        assert img.size == (256, 256)  # normalised to a square

    # Replacing changes the versioned URL so browsers don't show the old picture.
    again = await client.put(
        "/api/v1/users/me/avatar",
        files={"file": ("me2.png", png(300, 900, (200, 60, 60)), "image/png")},
        headers=ORIGIN,
    )
    assert again.json()["data"]["avatar_url"] != url

    removed = await client.delete("/api/v1/users/me/avatar", headers=ORIGIN)
    assert removed.json()["data"]["avatar_url"] is None
    assert (await client.get(url)).status_code == 404


async def test_avatar_rejects_non_images_and_oversized_files(client: Any) -> None:
    await signup(client)
    fake = await client.put(
        "/api/v1/users/me/avatar",
        files={"file": ("me.png", b"<svg onload=alert(1)>", "image/png")},
        headers=ORIGIN,
    )
    assert fake.status_code == 422 and fake.json()["error"]["code"] == "AVATAR_UNREADABLE"
    huge = await client.put(
        "/api/v1/users/me/avatar",
        files={"file": ("big.png", b"\x89PNG" + b"0" * (5 * 1024 * 1024 + 10), "image/png")},
        headers=ORIGIN,
    )
    # The request-size limit (or the service's own check) refuses it before any decoding.
    assert huge.status_code in (413, 422)
