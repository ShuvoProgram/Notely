from __future__ import annotations

from typing import Any

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


async def test_continue_with_google_signs_up_then_signs_in_via_the_shared_callback(
    client: AsyncClient, monkeypatch: Any
) -> None:
    """Sign-in and the Google connectors share ONE redirect URI (/api/v1/oauth/google/callback);
    the callback route tells the flows apart by the state record, so an operator registers a
    single URI in Google Cloud and `redirect_uri_mismatch` cannot come from Notely's side."""
    from urllib.parse import parse_qs, urlparse

    import httpx

    from app.core import oauth as core_oauth
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "oauth_google_client_id", "google-id")
    monkeypatch.setattr(settings, "oauth_google_client_secret", "google-secret")

    token_calls: list[dict[str, list[str]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "oauth2.googleapis.com" and request.url.path == "/token":
            token_calls.append(parse_qs(request.content.decode()))
            return httpx.Response(
                200,
                json={"access_token": "at", "id_token": "signed-by-google", "token_type": "Bearer"},
            )
        return httpx.Response(404)

    core_oauth.set_http_transport(httpx.MockTransport(handler))
    monkeypatch.setattr(
        core_oauth.OAuthClient,
        "verify_id_token",
        lambda self, token, nonce: {
            "sub": "google-uid-1",
            "email": "Grace@Example.com",
            "email_verified": True,
            "name": "Grace Hopper",
            "picture": "https://example.com/g.png",
        },
    )
    try:
        listing = (await client.get("/api/v1/auth/providers")).json()["data"]
        assert listing[0]["id"] == "google"

        async def continue_with_google() -> dict[str, Any]:
            start = await client.get("/api/v1/auth/oauth/google/start", follow_redirects=False)
            assert start.status_code == 302
            q = parse_qs(urlparse(start.headers["location"]).query)
            redirect = q["redirect_uri"][0]
            # The one URI to register — identical to the Gmail/Calendar/Drive connectors'.
            assert redirect == "http://localhost:3000/api/v1/oauth/google/callback"
            assert q["scope"] == ["openid email profile"] and q["nonce"]
            cb = await client.get(
                redirect.removeprefix("http://localhost:3000"),
                params={"code": "auth-code", "state": q["state"][0]},
                follow_redirects=False,
            )
            assert cb.status_code == 302, cb.text
            assert cb.headers["location"] == "http://localhost:3000/app"
            assert settings.session_cookie_name in cb.headers.get("set-cookie", "")
            me = await client.get("/api/v1/users/me")
            assert me.status_code == 200, me.text
            return dict(me.json()["data"])

        # First time: the account is created from the Google profile.
        first = await continue_with_google()
        assert first["email"] == "grace@example.com"
        assert first["display_name"] == "Grace Hopper"
        assert token_calls[-1]["redirect_uri"] == [
            "http://localhost:3000/api/v1/oauth/google/callback"
        ]

        # Next time: same Google subject → same account, no duplicate.
        await client.post("/api/v1/auth/logout", headers=ORIGIN)
        second = await continue_with_google()
        assert second["id"] == first["id"]

        # A stale/replayed state lands on the login page with a readable reason, never a 4xx.
        await client.post("/api/v1/auth/logout", headers=ORIGIN)
        stale = await client.get(
            "/api/v1/oauth/google/callback",
            params={"code": "x", "state": "no-such-state"},
            follow_redirects=False,
        )
        assert stale.status_code == 302
        assert stale.headers["location"] == "http://localhost:3000/login?error=oauth_expired"

        # The user pressing "Cancel" on Google's screen is told so.
        start = await client.get("/api/v1/auth/oauth/google/start", follow_redirects=False)
        state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
        denied = await client.get(
            "/api/v1/oauth/google/callback",
            params={"error": "access_denied", "state": state},
            follow_redirects=False,
        )
        assert denied.headers["location"] == "http://localhost:3000/login?error=oauth_denied"
    finally:
        core_oauth.set_http_transport(None)


async def test_sound_preference_persists_and_validates(client: AsyncClient) -> None:
    await signup(client)
    me = await client.get("/api/v1/users/me")
    assert me.json()["data"]["sound"] == {"enabled": True, "volume": 0.6}

    resp = await client.patch(
        "/api/v1/users/me", json={"sound": {"enabled": False, "volume": 0.25}}, headers=ORIGIN
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["sound"] == {"enabled": False, "volume": 0.25}
    # Other preference groups are untouched by a sound update.
    resp = await client.patch(
        "/api/v1/users/me", json={"notifications": {"sharing": False}}, headers=ORIGIN
    )
    data = resp.json()["data"]
    assert data["sound"] == {"enabled": False, "volume": 0.25}
    assert data["notifications"] == {"sharing": False}

    out_of_range = await client.patch(
        "/api/v1/users/me", json={"sound": {"enabled": True, "volume": 1.5}}, headers=ORIGIN
    )
    assert out_of_range.status_code == 422
