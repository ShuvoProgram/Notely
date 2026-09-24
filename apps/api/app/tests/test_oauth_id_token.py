"""id_token verification with a real RSA signature (the sign-in tests mock this step)."""

from __future__ import annotations

import time
from types import SimpleNamespace
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.core.exceptions import OAuthExchangeFailed
from app.core.oauth import OAuthClient, OAuthClientConfig, OAuthEndpoints

ISSUER = "https://accounts.example.com"
CLIENT_ID = "client-123"
_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> OAuthClient:
    monkeypatch.setattr(
        "app.core.oauth.PyJWKClient.get_signing_key_from_jwt",
        lambda self, token: SimpleNamespace(key=_key.public_key()),
    )
    endpoints = OAuthEndpoints(
        authorize_url=f"{ISSUER}/auth",
        token_url=f"{ISSUER}/token",
        jwks_url=f"{ISSUER}/certs",
        issuer=ISSUER,
    )
    config = OAuthClientConfig(
        provider_id="example",
        client_id=CLIENT_ID,
        client_secret="s",
        scopes=("openid",),
        endpoints=endpoints,
    )
    return OAuthClient(config, "http://localhost/callback")


def token(**overrides: Any) -> str:
    now = int(time.time())
    claims = {"sub": "u1", "aud": CLIENT_ID, "iss": ISSUER, "iat": now, "exp": now + 3600}
    return jwt.encode({**claims, **overrides}, _key, algorithm="RS256")


def test_accepts_a_token_issued_by_a_clock_slightly_ahead_of_ours(client: OAuthClient) -> None:
    """The provider stamps `iat` with its own clock; ours running a few seconds behind (seen
    on dev machines) used to reject every sign-in as "token not yet valid"."""
    claims = client.verify_id_token(token(iat=int(time.time()) + 5), None)
    assert claims["sub"] == "u1"


def test_still_rejects_expired_foreign_and_far_future_tokens(client: OAuthClient) -> None:
    now = int(time.time())
    for bad in (
        token(exp=now - 3600, iat=now - 7200),  # long expired
        token(aud="someone-else"),
        token(iss="https://evil.example.com"),
        token(iat=now + 3600),  # not a clock difference: a forged / broken token
    ):
        with pytest.raises(OAuthExchangeFailed):
            client.verify_id_token(bad, None)


def test_rejects_a_nonce_mismatch(client: OAuthClient) -> None:
    with pytest.raises(OAuthExchangeFailed):
        client.verify_id_token(token(nonce="a"), "b")
