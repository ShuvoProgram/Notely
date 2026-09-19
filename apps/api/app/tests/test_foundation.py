"""Envelope, CSRF, rate limiting, health, crypto, OAuth state handling."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.core import crypto
from app.core.exceptions import InvalidOAuthState
from app.core.oauth import OAuthClient, OAuthClientConfig, OAuthEndpoints
from app.tests.conftest import ORIGIN, signup


async def test_health_endpoints(client: AsyncClient) -> None:
    assert (await client.get("/health")).json() == {"status": "ok"}
    assert (await client.get("/health/live")).json() == {"status": "ok"}
    ready = await client.get("/health/ready")
    body = ready.json()
    # Redis is intentionally unreachable in tests, so readiness must report degraded.
    assert ready.status_code == 503
    assert body["checks"]["database"] is True
    assert body["checks"]["redis"] is False
    assert body["checks"]["configuration"] is True
    assert "database_url" not in ready.text and "secret" not in ready.text.lower()


async def test_unknown_route_uses_error_envelope(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/does-not-exist")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


async def test_request_id_and_security_headers(client: AsyncClient) -> None:
    resp = await client.get("/health", headers={"X-Request-ID": "abc123"})
    assert resp.headers["X-Request-ID"] == "abc123"
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"


async def test_csrf_rejects_foreign_origin(client: AsyncClient) -> None:
    await signup(client)
    resp = await client.post("/api/v1/auth/logout", headers={"Origin": "https://evil.example"})
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "CSRF_ORIGIN_REJECTED"
    resp = await client.post("/api/v1/auth/logout", headers={"Sec-Fetch-Site": "cross-site"})
    assert resp.status_code == 403
    # Still signed in: the rejected requests never reached the handler.
    assert (await client.get("/api/v1/users/me")).status_code == 200


async def test_auth_rate_limit(client: AsyncClient) -> None:
    statuses = []
    for _ in range(12):
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "x@example.com", "password": "whatever-password"},
            headers=ORIGIN,
        )
        statuses.append(resp.status_code)
    assert statuses[:10] == [401] * 10
    assert statuses[10] == 429
    assert resp.json()["error"]["code"] == "RATE_LIMITED"
    assert "Retry-After" in resp.headers


def test_crypto_roundtrip_and_key_validation() -> None:
    key = crypto.generate_key()
    assert crypto.is_valid_key(key)
    assert not crypto.is_valid_key("not-a-key")
    token = crypto.encrypt("xoxb-secret", key=key)
    assert token != "xoxb-secret"
    assert crypto.decrypt(token, key=key) == "xoxb-secret"
    with pytest.raises(crypto.EncryptionError):
        crypto.decrypt(token, key=crypto.generate_key())
    with pytest.raises(crypto.EncryptionError):
        crypto.encrypt("x", key="")


def _client() -> OAuthClient:
    return OAuthClient(
        OAuthClientConfig(
            provider_id="test",
            client_id="cid",
            client_secret="sec",
            scopes=("openid", "email"),
            endpoints=OAuthEndpoints(
                authorize_url="https://idp.example/authorize", token_url="https://idp.example/token"
            ),
        ),
        redirect_uri="http://localhost:8000/cb",
    )


async def test_oauth_begin_builds_pkce_url_and_state_is_single_use() -> None:
    client = _client()
    url = await client.begin(context={"k": "v"})
    assert url.startswith("https://idp.example/authorize?")
    assert "code_challenge_method=S256" in url
    assert "code_challenge=" in url and "nonce=" in url
    state = url.split("state=")[1].split("&")[0]
    record = await client.consume_state(state)
    assert record["context"] == {"k": "v"}
    assert record["verifier"]
    with pytest.raises(InvalidOAuthState):
        await client.consume_state(state)
    with pytest.raises(InvalidOAuthState):
        await client.consume_state("forged")
    with pytest.raises(InvalidOAuthState):
        await client.consume_state(None)


def test_settings_parse_comma_separated_origins(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import Settings

    monkeypatch.setenv("ALLOWED_ORIGINS", "http://a.example, https://b.example")
    assert Settings().allowed_origins == ["http://a.example", "https://b.example"]
