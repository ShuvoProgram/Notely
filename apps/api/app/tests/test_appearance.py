from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy import select

from app.db.session import get_session_factory
from app.models.user import User
from app.tests.conftest import ORIGIN, signup

DEFAULT = {
    "background": "starry-moss",
    "glass": "medium",
    "blur": None,
    "opacity": None,
    "border": None,
}


async def test_appearance_defaults_persist_and_sync(client: AsyncClient) -> None:
    await signup(client)
    me = await client.get("/api/v1/users/me")
    assert me.json()["data"]["appearance"] == DEFAULT

    chosen = {**DEFAULT, "background": "mountain-lake", "glass": "strong", "blur": 70}
    resp = await client.patch("/api/v1/users/me", json={"appearance": chosen}, headers=ORIGIN)
    assert resp.status_code == 200
    assert resp.json()["data"]["appearance"] == {**chosen, "opacity": None, "border": None}

    # Other preference groups survive an appearance update, and vice versa.
    await client.patch(
        "/api/v1/users/me", json={"sound": {"enabled": False, "volume": 0.3}}, headers=ORIGIN
    )
    data = (await client.get("/api/v1/users/me")).json()["data"]
    assert data["appearance"]["background"] == "mountain-lake"
    assert data["sound"] == {"enabled": False, "volume": 0.3}

    resp = await client.patch("/api/v1/users/me", json={"appearance": DEFAULT}, headers=ORIGIN)
    assert resp.json()["data"]["appearance"] == DEFAULT


async def test_only_approved_backgrounds_are_accepted(client: AsyncClient) -> None:
    await signup(client)
    # Retired presets, colour/gradient fills and uploads are all gone.
    for bad in (
        {"background": "custom"},
        {"background": "aurora"},
        {"background": "solid"},
        {"background": "https://example.com/me.png"},
        {"glass": "extreme"},
        {"blur": 120},
    ):
        resp = await client.patch(
            "/api/v1/users/me", json={"appearance": {**DEFAULT, **bad}}, headers=ORIGIN
        )
        assert resp.status_code == 422, bad


async def test_retired_stored_background_falls_back_but_keeps_glass(client: AsyncClient) -> None:
    await signup(client)
    async with get_session_factory()() as db:
        user = (await db.execute(select(User))).scalar_one()
        user.preferences = {
            **(user.preferences or {}),
            "appearance": {"background": "custom", "color": "#123456", "glass": "subtle"},
        }
        await db.commit()
    resp = await client.get("/api/v1/users/me")
    assert resp.status_code == 200
    assert resp.json()["data"]["appearance"] == {**DEFAULT, "glass": "subtle"}
