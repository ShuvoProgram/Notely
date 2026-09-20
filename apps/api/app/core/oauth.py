"""Generic OAuth 2.0 / OIDC authorization-code client with PKCE and server-side state.

This is the single OAuth implementation in the codebase. Sign-in providers (Google, Microsoft)
use it today; integration providers (Slack, Notion, ...) reuse it in Phase 4. Nothing here is
provider-specific beyond the endpoint configuration passed in.

Security properties:
- cryptographically random `state` and PKCE `code_verifier` (S256)
- state + verifier + redirect URI stored server-side (KV) with a short TTL, single use
- redirect URI is always built from API_PUBLIC_URL, never taken from the client
- tokens are returned to the caller and never logged
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal
from urllib.parse import urlencode

import httpx
import jwt
from jwt import PyJWKClient

from app.core.config import Settings
from app.core.exceptions import InvalidOAuthState, OAuthExchangeFailed
from app.core.kv import kv
from app.core.logging import get_logger

log = get_logger(__name__)

STATE_TTL_SECONDS = 600

# Tests inject an httpx MockTransport here; production uses real HTTP.
_http_transport: httpx.AsyncBaseTransport | None = None


def set_http_transport(transport: httpx.AsyncBaseTransport | None) -> None:
    global _http_transport
    _http_transport = transport


def transport() -> httpx.AsyncBaseTransport | None:
    return _http_transport


@dataclass(frozen=True)
class OAuthEndpoints:
    authorize_url: str
    token_url: str
    jwks_url: str | None = None  # OIDC id_token verification
    userinfo_url: str | None = None
    issuer: str | None = None
    extra_authorize_params: dict[str, str] = field(default_factory=dict)
    # How the token endpoint wants client credentials and the body encoded.
    token_auth: Literal["body", "basic"] = "body"
    token_format: Literal["form", "json"] = "form"
    # Some providers (Slack) require the scope list under a different query parameter.
    scope_param: str = "scope"
    scope_separator: str = " "
    # Sent with every token request (e.g. RFC 8707 `resource` for MCP servers).
    extra_token_params: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class OAuthClientConfig:
    provider_id: str
    client_id: str
    client_secret: str
    scopes: tuple[str, ...]
    endpoints: OAuthEndpoints
    use_pkce: bool = True
    # Optional override for non-standard token responses (e.g. Slack's `authed_user`).
    token_parser: Callable[[dict[str, Any]], OAuthTokens] | None = None


@dataclass(frozen=True)
class OAuthTokens:
    access_token: str
    refresh_token: str | None
    expires_in: int | None
    id_token: str | None
    scope: str | None
    raw: dict[str, Any]


def callback_slot(provider: Any) -> str:
    """Which `/oauth/{slot}/callback` a provider comes back to. Vendor families that share one
    OAuth app (Gmail/Calendar/Drive → `google`, Teams/Outlook/OneDrive → `microsoft`) share
    one redirect URI too, so an operator registers a single URI per vendor."""
    prefix = getattr(provider, "settings_prefix", None)
    return str(prefix) if prefix else str(provider.manifest.id)


def callback_uri(settings: Settings, path: str) -> str:
    """OAuth callbacks come back through the app's public origin (the web app proxies `/api/*`
    to the API, and the production edge routes it directly). One origin means the session
    cookie is always first-party and the registered redirect URI never depends on where the
    API process happens to listen."""
    return f"{settings.frontend_origin.rstrip('/')}{settings.api_prefix}{path}"


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _state_key(provider_id: str, state: str) -> str:
    return f"oauth:state:{provider_id}:{state}"


async def consume_oauth_state(
    provider_id: str, state: str | None, redirect_uri: str
) -> dict[str, Any]:
    """Validate and delete a state record (single use). Raises on mismatch/expiry."""
    if not state:
        raise InvalidOAuthState()
    key = _state_key(provider_id, state)
    raw = await kv.get(key)
    if raw is None:
        raise InvalidOAuthState()
    await kv.delete(key)
    record: dict[str, Any] = json.loads(raw)
    if record.get("redirect_uri") != redirect_uri:
        raise InvalidOAuthState()
    return record


class OAuthClient:
    def __init__(self, config: OAuthClientConfig, redirect_uri: str) -> None:
        self.config = config
        self.redirect_uri = redirect_uri

    async def begin(self, *, context: dict[str, Any] | None = None) -> str:
        """Create state/PKCE, persist them, and return the provider authorize URL."""
        state = secrets.token_urlsafe(32)
        verifier = _b64url(secrets.token_bytes(64)) if self.config.use_pkce else None
        nonce = secrets.token_urlsafe(16)
        await kv.set(
            _state_key(self.config.provider_id, state),
            json.dumps(
                {
                    "verifier": verifier,
                    "nonce": nonce,
                    "redirect_uri": self.redirect_uri,
                    "context": context or {},
                }
            ),
            STATE_TTL_SECONDS,
        )
        ep = self.config.endpoints
        params: dict[str, str] = {
            "response_type": "code",
            "client_id": self.config.client_id,
            "redirect_uri": self.redirect_uri,
            "state": state,
            **ep.extra_authorize_params,
        }
        if self.config.scopes:
            params[ep.scope_param] = ep.scope_separator.join(self.config.scopes)
        if "openid" in self.config.scopes:
            params["nonce"] = nonce
        if verifier:
            challenge = _b64url(hashlib.sha256(verifier.encode()).digest())
            params["code_challenge"] = challenge
            params["code_challenge_method"] = "S256"
        return f"{self.config.endpoints.authorize_url}?{urlencode(params)}"

    async def consume_state(self, state: str | None) -> dict[str, Any]:
        """Validate and delete the state record (single use). Raises on mismatch/expiry."""
        return await consume_oauth_state(self.config.provider_id, state, self.redirect_uri)

    async def exchange_code(self, code: str, verifier: str | None) -> OAuthTokens:
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.redirect_uri,
        }
        if verifier:
            data["code_verifier"] = verifier
        resp = await self._post_token(data)
        return self._parse_tokens(resp)

    async def refresh(self, refresh_token: str) -> OAuthTokens:
        """Standard refresh_token grant; providers with custom flows do their own."""
        resp = await self._post_token(
            {"grant_type": "refresh_token", "refresh_token": refresh_token}
        )
        return self._parse_tokens(resp)

    async def _post_token(self, data: dict[str, str]) -> httpx.Response:
        ep = self.config.endpoints
        headers = {"Accept": "application/json"}
        auth: httpx.BasicAuth | httpx._client.UseClientDefault = httpx.USE_CLIENT_DEFAULT
        data = {**data, **ep.extra_token_params}
        if ep.token_auth == "basic" and self.config.client_secret:
            auth = httpx.BasicAuth(self.config.client_id, self.config.client_secret)
        else:
            # Public clients (dynamically registered, PKCE-only) send no secret at all.
            data = {**data, "client_id": self.config.client_id}
            if self.config.client_secret:
                data["client_secret"] = self.config.client_secret
        try:
            async with httpx.AsyncClient(timeout=15, transport=_http_transport) as http:
                if ep.token_format == "json":
                    resp = await http.post(ep.token_url, json=data, headers=headers, auth=auth)
                else:
                    resp = await http.post(ep.token_url, data=data, headers=headers, auth=auth)
        except httpx.HTTPError as exc:
            log.warning(
                "oauth_token_exchange_network_error",
                extra={"provider": self.config.provider_id, "reason": type(exc).__name__},
            )
            raise OAuthExchangeFailed() from exc
        if resp.status_code >= 400:
            log.warning(
                "oauth_token_exchange_rejected",
                extra={"provider": self.config.provider_id, "status": resp.status_code},
            )
            raise OAuthExchangeFailed()
        return resp

    def _parse_tokens(self, resp: httpx.Response) -> OAuthTokens:
        payload = resp.json()
        if self.config.token_parser is not None:
            return self.config.token_parser(payload)
        if "access_token" not in payload or payload.get("ok") is False:
            raise OAuthExchangeFailed()
        return OAuthTokens(
            access_token=payload["access_token"],
            refresh_token=payload.get("refresh_token"),
            expires_in=payload.get("expires_in"),
            id_token=payload.get("id_token"),
            scope=payload.get("scope"),
            raw=payload,
        )

    def verify_id_token(self, id_token: str, nonce: str | None) -> dict[str, Any]:
        """Verify an OIDC id_token signature and standard claims using the provider JWKS."""
        endpoints = self.config.endpoints
        if not endpoints.jwks_url:
            raise OAuthExchangeFailed()
        try:
            signing_key = PyJWKClient(endpoints.jwks_url, cache_keys=True).get_signing_key_from_jwt(
                id_token
            )
            claims: dict[str, Any] = jwt.decode(
                id_token,
                signing_key.key,
                algorithms=["RS256"],
                audience=self.config.client_id,
                issuer=endpoints.issuer,
                options={
                    "require": ["sub", "exp", "iat"],
                    "verify_iss": endpoints.issuer is not None,
                },
            )
        except Exception as exc:
            log.warning(
                "oauth_id_token_invalid",
                extra={"provider": self.config.provider_id, "reason": type(exc).__name__},
            )
            raise OAuthExchangeFailed() from exc
        if nonce and claims.get("nonce") != nonce:
            raise OAuthExchangeFailed()
        return claims

    async def fetch_userinfo(self, access_token: str) -> dict[str, Any]:
        if not self.config.endpoints.userinfo_url:
            return {}
        try:
            async with httpx.AsyncClient(timeout=15, transport=_http_transport) as http:
                resp = await http.get(
                    self.config.endpoints.userinfo_url,
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                resp.raise_for_status()
                result: dict[str, Any] = resp.json()
                return result
        except httpx.HTTPError as exc:
            raise OAuthExchangeFailed() from exc
