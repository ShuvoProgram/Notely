"""One-click OAuth for remote MCP servers (MCP authorization spec: OAuth 2.1 + RFC 9728
protected-resource metadata + RFC 8414 server metadata + RFC 7591 dynamic client registration).

This is how hosts like ChatGPT/Claude connect to Notion, Linear, Atlassian, Sentry… without
the operator registering an app per vendor: the server tells us where its authorization
server is, we register Notely as a client *once per deployment*, and every user then goes
through the normal consent screen. Registered clients are cached in `oauth_dynamic_clients`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from mcp.client.auth.utils import (
    build_oauth_authorization_server_metadata_discovery_urls,
    build_protected_resource_metadata_discovery_urls,
)
from mcp.shared.auth import OAuthMetadata, ProtectedResourceMetadata
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import crypto
from app.core import oauth as core_oauth
from app.core.config import Settings
from app.core.logging import get_logger
from app.core.oauth import OAuthClientConfig, OAuthEndpoints
from app.db.base import utcnow
from app.integrations.base.errors import ProviderError, ProviderErrorKind
from app.models.integration import OAuthDynamicClient

log = get_logger(__name__)

DISCOVERY_TIMEOUT = 10.0
CLIENT_NAME = "Notely AI"


@dataclass(frozen=True)
class MCPAuthServer:
    """What we learned about a server's authorization requirements."""

    resource: str  # the MCP server URL (RFC 8707 `resource` value)
    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    registration_endpoint: str | None
    scopes: tuple[str, ...]
    supports_pkce: bool

    def endpoints(self) -> OAuthEndpoints:
        return OAuthEndpoints(
            authorize_url=self.authorization_endpoint,
            token_url=self.token_endpoint,
            issuer=self.issuer,
            extra_authorize_params={"resource": self.resource},
            extra_token_params={"resource": self.resource},
        )


def _http() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=DISCOVERY_TIMEOUT,
        transport=core_oauth.transport(),
        headers={"Accept": "application/json"},
        follow_redirects=False,
    )


def _resource_metadata_url(www_authenticate: str | None) -> str | None:
    if not www_authenticate:
        return None
    match = re.search(r'resource_metadata="?([^",\s]+)"?', www_authenticate)
    return match.group(1) if match else None


async def discover(server_url: str) -> MCPAuthServer | None:
    """Ask the server how to authorize. Returns None when it answers without demanding auth
    (public server); raises `ProviderError(misconfigured)` when it demands auth but publishes
    no usable OAuth metadata (the user can still connect with a token)."""
    async with _http() as http:
        try:
            probe = await http.post(
                server_url,
                json={"jsonrpc": "2.0", "id": 0, "method": "ping"},
                headers={"Accept": "application/json, text/event-stream"},
            )
        except httpx.HTTPError as exc:
            raise ProviderError(
                ProviderErrorKind.unavailable, type(exc).__name__, provider="mcp"
            ) from exc
        if probe.status_code != 401:
            return None
        prm = await _protected_resource(
            http, server_url, _resource_metadata_url(probe.headers.get("www-authenticate"))
        )
        auth_server = (
            str(prm.authorization_servers[0]) if prm and prm.authorization_servers else None
        )
        metadata = await _auth_server_metadata(http, auth_server, server_url)
    if metadata is None:
        raise ProviderError(
            ProviderErrorKind.misconfigured,
            "server requires auth but publishes no OAuth metadata",
            provider="mcp",
        )
    scopes: tuple[str, ...] = tuple(prm.scopes_supported or []) if prm else ()
    resource = str(prm.resource) if prm and prm.resource else server_url
    return MCPAuthServer(
        resource=resource,
        issuer=str(metadata.issuer),
        authorization_endpoint=str(metadata.authorization_endpoint),
        token_endpoint=str(metadata.token_endpoint),
        registration_endpoint=(
            str(metadata.registration_endpoint) if metadata.registration_endpoint else None
        ),
        scopes=scopes,
        supports_pkce="S256" in (metadata.code_challenge_methods_supported or ["S256"]),
    )


async def _protected_resource(
    http: httpx.AsyncClient, server_url: str, hinted: str | None
) -> ProtectedResourceMetadata | None:
    for url in build_protected_resource_metadata_discovery_urls(hinted, server_url):
        try:
            resp = await http.get(url)
        except httpx.HTTPError:
            continue
        if resp.status_code == 200:
            try:
                return ProtectedResourceMetadata.model_validate_json(resp.content)
            except ValueError:
                continue
    return None


async def _auth_server_metadata(
    http: httpx.AsyncClient, auth_server: str | None, server_url: str
) -> OAuthMetadata | None:
    for url in build_oauth_authorization_server_metadata_discovery_urls(auth_server, server_url):
        try:
            resp = await http.get(url)
        except httpx.HTTPError:
            continue
        if resp.status_code == 200:
            try:
                return OAuthMetadata.model_validate_json(resp.content)
            except ValueError:
                continue
    return None


async def dynamic_client(
    db: AsyncSession, settings: Settings, auth: MCPAuthServer, redirect_uri: str, provider_id: str
) -> OAuthClientConfig:
    """The deployment's client for this authorization server: reused when already registered,
    otherwise registered now (RFC 7591) and cached."""
    row = await db.scalar(
        select(OAuthDynamicClient).where(OAuthDynamicClient.issuer == auth.issuer)
    )
    if row is not None and row.expires_at is not None and row.expires_at <= utcnow():
        await db.delete(row)
        await db.flush()
        row = None
    if row is None or redirect_uri not in row.redirect_uris:
        if auth.registration_endpoint is None:
            raise ProviderError(
                ProviderErrorKind.misconfigured,
                "authorization server does not support dynamic registration",
                provider=provider_id,
            )
        client_id, client_secret, expires_at = await _register(
            auth.registration_endpoint, redirect_uri, provider_id
        )
        if row is None:
            row = OAuthDynamicClient(issuer=auth.issuer)
            db.add(row)
        row.server_url = auth.resource
        row.client_id = client_id
        row.client_secret_encrypted = (
            crypto.encrypt(client_secret, key=settings.encryption_key) if client_secret else None
        )
        row.redirect_uris = sorted({*(row.redirect_uris or []), redirect_uri})
        row.registered_at = utcnow()
        row.expires_at = expires_at
        row.metadata_ = {"registration_endpoint": auth.registration_endpoint}
        await db.commit()
    secret = (
        crypto.decrypt(row.client_secret_encrypted, key=settings.encryption_key)
        if row.client_secret_encrypted
        else ""
    )
    return OAuthClientConfig(
        provider_id=provider_id,
        client_id=row.client_id,
        client_secret=secret,
        scopes=auth.scopes,
        endpoints=auth.endpoints(),
        use_pkce=True,
    )


async def _register(
    registration_endpoint: str, redirect_uri: str, provider_id: str
) -> tuple[str, str | None, Any]:
    body = {
        "client_name": CLIENT_NAME,
        "client_uri": urljoin(redirect_uri, "/"),
        "redirect_uris": [redirect_uri],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",  # public client + PKCE
    }
    async with _http() as http:
        try:
            resp = await http.post(registration_endpoint, json=body)
        except httpx.HTTPError as exc:
            raise ProviderError(
                ProviderErrorKind.unavailable, type(exc).__name__, provider=provider_id
            ) from exc
    if resp.status_code not in (200, 201):
        log.warning(
            "mcp_client_registration_rejected",
            extra={"provider": provider_id, "status": resp.status_code},
        )
        raise ProviderError(
            ProviderErrorKind.misconfigured,
            f"client registration rejected ({resp.status_code})",
            provider=provider_id,
        )
    data = resp.json()
    client_id = str(data.get("client_id") or "")
    if not client_id:
        raise ProviderError(
            ProviderErrorKind.misconfigured,
            "registration returned no client_id",
            provider=provider_id,
        )
    expires_at = None
    if data.get("client_secret_expires_at"):
        from datetime import UTC, datetime

        expires_at = datetime.fromtimestamp(int(data["client_secret_expires_at"]), UTC)
    return (
        client_id,
        (str(data["client_secret"]) if data.get("client_secret") else None),
        expires_at,
    )


def server_host(url: str) -> str:
    return urlparse(url).netloc
