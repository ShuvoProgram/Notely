"""One-click connect through a vendor's official MCP server: discovery (RFC 9728 / 8414),
dynamic client registration (RFC 7591), PKCE consent, token exchange, tools, refresh.

The authorization server is an httpx MockTransport; the MCP server is the in-memory demo server
from `integrations_fixtures`, which only accepts the token the mock AS issues."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from langchain_core.messages import AIMessage
from sqlalchemy import select

from app.ai.llm import set_fake_script
from app.core import oauth as core_oauth
from app.models.integration import OAuthDynamicClient
from app.tests.conftest import ORIGIN, signup
from app.tests.integrations_fixtures import MCP_TOKEN
from app.tests.test_ai import chat, tool_call

SERVER = "https://mcp.notion.com/mcp"
ISSUER = "https://auth.notion.example"


class FakeAuthServer:
    """Just enough of an OAuth 2.1 authorization server for the MCP flow."""

    def __init__(self) -> None:
        self.registrations: list[dict[str, Any]] = []
        self.token_requests: list[dict[str, str]] = []
        self.refreshes = 0
        self.require_auth = True

    def handle(self, r: httpx.Request) -> httpx.Response:
        host, path = r.url.host, r.url.path
        if host == "mcp.notion.com" and path == "/mcp":
            if not self.require_auth:
                return httpx.Response(200, json={"jsonrpc": "2.0", "id": 0, "result": {}})
            return httpx.Response(
                401,
                headers={
                    "WWW-Authenticate": (
                        'Bearer resource_metadata="https://mcp.notion.com/.well-known/'
                        'oauth-protected-resource/mcp"'
                    )
                },
            )
        if host == "mcp.notion.com" and path == "/.well-known/oauth-protected-resource/mcp":
            return httpx.Response(
                200,
                json={
                    "resource": SERVER,
                    "authorization_servers": [ISSUER],
                    "scopes_supported": ["read", "write"],
                },
            )
        if host == "auth.notion.example" and path == "/.well-known/oauth-authorization-server":
            return httpx.Response(
                200,
                json={
                    "issuer": ISSUER,
                    "authorization_endpoint": f"{ISSUER}/authorize",
                    "token_endpoint": f"{ISSUER}/token",
                    "registration_endpoint": f"{ISSUER}/register",
                    "code_challenge_methods_supported": ["S256"],
                    "response_types_supported": ["code"],
                },
            )
        if host == "auth.notion.example" and path == "/register":
            body = json.loads(r.content)
            self.registrations.append(body)
            assert body["token_endpoint_auth_method"] == "none"
            assert body["redirect_uris"] == ["http://localhost:8000/api/v1/oauth/notion/callback"]
            return httpx.Response(
                201,
                json={"client_id": f"dyn-{len(self.registrations)}", "client_secret_expires_at": 0},
            )
        if host == "auth.notion.example" and path == "/token":
            form = dict(httpx.QueryParams(r.content.decode()))
            self.token_requests.append(form)
            assert "client_secret" not in form, "public clients never send a secret"
            assert form["client_id"].startswith("dyn-")
            assert form["resource"] == SERVER
            if form["grant_type"] == "refresh_token":
                self.refreshes += 1
                assert form["refresh_token"] == "mcp-refresh"
            else:
                assert form["code"] == "good-code" and form["code_verifier"]
            return httpx.Response(
                200,
                json={
                    "access_token": MCP_TOKEN,
                    "refresh_token": "mcp-refresh",
                    "expires_in": 3600,
                    "token_type": "Bearer",
                },
            )
        return httpx.Response(404, json={"error": f"unmocked {host}{path}"})


@pytest.fixture
def auth_server() -> Iterator[FakeAuthServer]:
    fake = FakeAuthServer()
    core_oauth.set_http_transport(httpx.MockTransport(fake.handle))
    yield fake
    core_oauth.set_http_transport(None)


async def start(client: Any, provider: str) -> dict[str, Any]:
    resp = await client.get(f"/api/v1/oauth/{provider}/start-url", params={"method": "mcp"})
    assert resp.status_code == 200, resp.text
    return dict(resp.json()["data"])


async def test_notion_connects_with_one_click_through_its_mcp_server(
    client: Any, mcp_server: Any, auth_server: FakeAuthServer
) -> None:
    await signup(client)
    detail = (await client.get("/api/v1/integrations/providers/notion")).json()["data"]
    # No Notion OAuth app is configured on this deployment, yet the click path exists.
    assert detail["configured"] is False
    assert detail["connect_methods"] == ["mcp", "token"]

    url = (await start(client, "notion"))["authorize_url"]
    parsed = urlparse(url)
    q = parse_qs(parsed.query)
    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == f"{ISSUER}/authorize"
    assert q["client_id"] == ["dyn-1"] and q["code_challenge_method"] == ["S256"]
    assert q["resource"] == [SERVER] and q["scope"] == ["read write"]
    assert len(auth_server.registrations) == 1

    cb = await client.get(
        "/api/v1/oauth/notion/callback", params={"code": "good-code", "state": q["state"][0]}
    )
    assert cb.status_code == 302 and cb.headers["location"].endswith("?connected=1"), cb.text
    conn = (await client.get("/api/v1/integrations/providers/notion")).json()["data"]["connection"]
    assert conn["status"] == "connected" and conn["auth_type"] == "mcp"
    assert conn["external_account_name"] == "Demo Docs"  # the MCP server's name
    assert conn["scopes"] == ["read", "write"]

    # Tools come from the MCP server but carry the vendor's identity.
    tools = (await client.get("/api/v1/ai/settings")).json()["data"]["tools"]
    names = {t["name"]: t for t in tools if t["provider"] == "notion"}
    assert {"notion__search_docs", "notion__create_page", "notion__delete_page"} <= set(names)
    assert names["notion__search_docs"]["risk"] == "read"
    assert names["notion__delete_page"]["risk"] == "destructive"

    # The assistant can use them; the MCP server only ever sees the token the AS issued.
    set_fake_script(
        [
            AIMessage(
                content="", tool_calls=[tool_call("notion__search_docs", {"query": "x"}, "c1")]
            ),
            AIMessage(content="ok"),
        ]
    )
    events = await chat(client, "search notion")
    assert [e for e in events if e["type"] == "step"][-1]["status"] == "completed"
    assert all(token == MCP_TOKEN for _, token in mcp_server.connection_calls)
    audit = (await client.get("/api/v1/audit")).json()["data"]
    assert audit[0]["provider"] == "notion" and audit[0]["tool_name"] == "notion__search_docs"

    # The dynamically registered client is cached for the deployment and reused.
    url2 = (await start(client, "notion"))["authorize_url"]
    assert parse_qs(urlparse(url2).query)["client_id"] == ["dyn-1"]
    assert len(auth_server.registrations) == 1

    # Health test and refresh go through MCP + the dynamic client.
    from app.db.session import get_session_factory

    async with get_session_factory()() as db:
        rows = list(await db.scalars(select(OAuthDynamicClient)))
        assert len(rows) == 1 and rows[0].issuer == ISSUER and rows[0].client_id == "dyn-1"
    test = (
        await client.post(f"/api/v1/integrations/connections/{conn['id']}/test", headers=ORIGIN)
    ).json()["data"]
    assert test["healthy"] is True, test


async def test_public_mcp_server_connects_without_consent(
    client: Any, mcp_server: Any, auth_server: FakeAuthServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mcp.client import Client

    from app.mcp import client as mcp_client

    auth_server.require_auth = False
    # A public server: the MCP fixture insists on a token, so accept none for this test.
    mcp_client.set_client_factory(lambda url, token: Client(mcp_server))
    await signup(client)
    resp = await client.get(
        "/api/v1/oauth/mcp_server/start-url",
        params={"method": "mcp", "server_url": SERVER},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["authorize_url"].endswith("/connections/mcp_server?connected=1")
    conn = (await client.get("/api/v1/integrations/connections")).json()["data"][0]
    assert conn["status"] == "connected" and conn["auth_type"] == "mcp"
    assert conn["config"]["server_url"] == SERVER


async def test_server_without_registration_falls_back_cleanly(
    client: Any, auth_server: FakeAuthServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    await signup(client)
    original = auth_server.handle

    def no_registration(r: httpx.Request) -> httpx.Response:
        resp = original(r)
        if r.url.path == "/.well-known/oauth-authorization-server":
            body = resp.json()
            body.pop("registration_endpoint")
            return httpx.Response(200, json=body)
        return resp

    core_oauth.set_http_transport(httpx.MockTransport(no_registration))
    resp = await client.get("/api/v1/oauth/notion/start-url", params={"method": "mcp"})
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "PROVIDER_MISCONFIGURED"
    conn = (await client.get("/api/v1/integrations/providers/notion")).json()["data"]["connection"]
    assert conn["status"] == "error"


def test_remote_mcp_catalog_is_registered() -> None:
    from app.integrations.registry import get_providers

    providers = get_providers()
    for pid in ("sentry", "stripe", "supabase", "vercel", "figma", "zapier", "huggingface"):
        m = providers[pid].manifest
        assert m.mcp_server_url and m.mcp_server_url.startswith("https://")
        assert m.auth.value == "oauth2" and m.permissions
    assert providers["huggingface"].manifest.token_auth is not None
    assert list(providers)[-1] == "mcp_server"
