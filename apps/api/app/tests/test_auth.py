from __future__ import annotations

from httpx import AsyncClient

from app.tests.conftest import ORIGIN, signup


async def test_signup_sets_httponly_cookie_and_returns_envelope(client: AsyncClient) -> None:
    data = await signup(client)
    assert data["email"] == "ada@example.com"
    assert data["has_password"] is True
    assert "password" not in data and "password_hash" not in data
    cookie = client.cookies.get("notely_session")
    assert cookie and len(cookie) > 30


async def test_signup_duplicate_email_conflicts(client: AsyncClient) -> None:
    await signup(client)
    resp = await client.post(
        "/api/v1/auth/signup",
        json={"email": "ADA@example.com", "password": "another long password", "display_name": "X"},
        headers=ORIGIN,
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "EMAIL_TAKEN"


async def test_signup_validation_error_shape(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/signup",
        json={"email": "not-an-email", "password": "short", "display_name": ""},
        headers=ORIGIN,
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert set(body["error"]["details"]["fields"]) >= {"email", "password", "display_name"}


async def test_login_and_me(client: AsyncClient) -> None:
    await signup(client)
    client.cookies.clear()
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "ada@example.com", "password": "correct horse battery"},
        headers=ORIGIN,
    )
    assert resp.status_code == 200
    me = await client.get("/api/v1/users/me")
    assert me.status_code == 200
    assert me.json()["data"]["display_name"] == "Ada"


async def test_login_wrong_password_is_generic_401(client: AsyncClient) -> None:
    await signup(client)
    for email in ("ada@example.com", "nobody@example.com"):
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "wrong password!!"},
            headers=ORIGIN,
        )
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "INVALID_CREDENTIALS"


async def test_me_requires_session(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/users/me")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHORIZED"


async def test_forged_cookie_is_rejected(client: AsyncClient) -> None:
    client.cookies.set("notely_session", "A" * 43)
    resp = await client.get("/api/v1/users/me")
    assert resp.status_code == 401


async def test_logout_revokes_session(client: AsyncClient) -> None:
    await signup(client)
    token = client.cookies.get("notely_session")
    resp = await client.post("/api/v1/auth/logout", headers=ORIGIN)
    assert resp.status_code == 200
    # Reusing the old token must fail even if the client kept it.
    client.cookies.set("notely_session", token or "")
    assert (await client.get("/api/v1/users/me")).status_code == 401


async def test_sessions_list_and_revoke_other(client: AsyncClient) -> None:
    await signup(client)
    first_cookie = client.cookies.get("notely_session")
    client.cookies.clear()
    await client.post(
        "/api/v1/auth/login",
        json={"email": "ada@example.com", "password": "correct horse battery"},
        headers=ORIGIN,
    )
    sessions = (await client.get("/api/v1/auth/sessions")).json()["data"]
    assert len(sessions) == 2
    current = [s for s in sessions if s["current"]]
    other = [s for s in sessions if not s["current"]]
    assert len(current) == 1 and len(other) == 1

    resp = await client.delete(f"/api/v1/auth/sessions/{other[0]['id']}", headers=ORIGIN)
    assert resp.status_code == 200
    client.cookies.set("notely_session", first_cookie or "")
    assert (await client.get("/api/v1/users/me")).status_code == 401


async def test_change_password_revokes_other_sessions(client: AsyncClient) -> None:
    await signup(client)
    first_cookie = client.cookies.get("notely_session")
    client.cookies.clear()
    await client.post(
        "/api/v1/auth/login",
        json={"email": "ada@example.com", "password": "correct horse battery"},
        headers=ORIGIN,
    )
    bad = await client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "nope nope nope", "new_password": "a brand new password"},
        headers=ORIGIN,
    )
    assert bad.status_code == 422
    good = await client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "correct horse battery", "new_password": "a brand new password"},
        headers=ORIGIN,
    )
    assert good.status_code == 200
    # Current session survives; the earlier one is gone.
    assert (await client.get("/api/v1/users/me")).status_code == 200
    client.cookies.set("notely_session", first_cookie or "")
    assert (await client.get("/api/v1/users/me")).status_code == 401
    # New password works.
    client.cookies.clear()
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "ada@example.com", "password": "a brand new password"},
        headers=ORIGIN,
    )
    assert resp.status_code == 200


async def test_update_profile(client: AsyncClient) -> None:
    await signup(client)
    resp = await client.patch(
        "/api/v1/users/me", json={"display_name": "  Ada L.  "}, headers=ORIGIN
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["display_name"] == "Ada L."


async def test_providers_empty_when_unconfigured(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/auth/providers")
    assert resp.status_code == 200
    assert resp.json()["data"] == []
    start = await client.get("/api/v1/auth/oauth/google/start")
    assert start.status_code == 404
    assert start.json()["error"]["code"] == "PROVIDER_NOT_CONFIGURED"
