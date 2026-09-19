"""Integration framework: marketplace, MCP provider, encryption at rest, agent exposure, disconnect,
OAuth flow with PKCE/state, refresh, webhooks, retries, provider contract."""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from langchain_core.messages import AIMessage
from sqlalchemy import select

from app.ai.llm import captured_prompts, set_fake_script
from app.core import crypto
from app.core.config import get_settings
from app.db.base import utcnow
from app.db.session import get_session_factory
from app.integrations.base.errors import ProviderError, ProviderErrorKind
from app.integrations.base.http import ProviderHttpClient
from app.integrations.registry import get_providers
from app.models.integration import ExternalItem, UserConnection, WebhookEvent
from app.tests.conftest import ORIGIN, read_sse, signup
from app.tests.integrations_fixtures import MCP_TOKEN, WEBHOOK_SECRET, FakeOAuthProvider
from app.tests.test_ai import chat, tool_call, types
from app.workers import queue

pytestmark = pytest.mark.usefixtures("client")


async def connect_mcp(client: Any, token: str = MCP_TOKEN) -> dict[str, Any]:
    resp = await client.post(
        "/api/v1/integrations/providers/mcp_server/connect",
        json={"config": {"server_url": "https://mcp.example.com/mcp"}, "token": token},
        headers=ORIGIN,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


# --- marketplace --------------------------------------------------------------------------------


async def test_marketplace_lists_providers_from_registry(client: Any) -> None:
    await signup(client)
    resp = await client.get("/api/v1/integrations/providers")
    assert resp.status_code == 200
    entries = {p["id"]: p for p in resp.json()["data"]}
    mcp = entries["mcp_server"]
    assert mcp["auth"] == "token" and mcp["configured"] is True and mcp["connection"] is None
    assert [f["key"] for f in mcp["config_fields"]] == ["server_url", "token"]
    assert "search" in mcp["capabilities"] and "delete" in mcp["capabilities"]


# --- MCP provider -------------------------------------------------------------------------------


async def test_connect_mcp_server_encrypts_token_and_discovers_tools(
    client: Any, mcp_server: Any
) -> None:
    await signup(client)
    conn = await connect_mcp(client)
    assert conn["status"] == "connected"
    assert conn["external_account_name"] == "Demo Docs"
    assert [t["name"] for t in conn["metadata"]["tools"]] == [
        "search_docs",
        "create_page",
        "delete_page",
        "failing_tool",
    ]
    # No credential ever leaves the API...
    assert "token" not in conn and "access_token" not in str(conn)
    # ...and the database holds ciphertext, not the token.
    async with get_session_factory()() as db:
        row = await db.scalar(select(UserConnection))
        assert row is not None and row.access_token_encrypted
        assert MCP_TOKEN not in row.access_token_encrypted
        assert (
            crypto.decrypt(row.access_token_encrypted, key=get_settings().encryption_key)
            == MCP_TOKEN
        )
    audit = (await client.get("/api/v1/audit")).json()["data"]
    assert [(a["provider"], a["action"]) for a in audit] == [("mcp_server", "connect")]


async def test_connect_requires_server_url_and_rejects_bad_token(
    client: Any, mcp_server: Any
) -> None:
    await signup(client)
    missing = await client.post(
        "/api/v1/integrations/providers/mcp_server/connect", json={"config": {}}, headers=ORIGIN
    )
    assert missing.status_code == 422
    assert "server_url" in missing.json()["error"]["details"]["fields"]

    bad = await client.post(
        "/api/v1/integrations/providers/mcp_server/connect",
        json={"config": {"server_url": "https://mcp.example.com/mcp"}, "token": "wrong"},
        headers=ORIGIN,
    )
    assert bad.status_code == 401
    assert bad.json()["error"]["code"] == "PROVIDER_AUTH_FAILED"
    detail = (await client.get("/api/v1/integrations/providers/mcp_server")).json()["data"]
    assert detail["connection"]["status"] == "error"
    assert detail["connection"]["last_error_code"] == "auth_failed"


async def test_test_connection_reports_steps(client: Any, mcp_server: Any) -> None:
    await signup(client)
    conn = await connect_mcp(client)
    resp = await client.post(f"/api/v1/integrations/connections/{conn['id']}/test", headers=ORIGIN)
    body = resp.json()["data"]
    assert body["healthy"] is True
    assert [s["name"] for s in body["steps"]] == [
        "Configuration",
        "Authentication",
        "API availability",
        "Tool access",
    ]
    assert body["steps"][-1]["detail"] == "4 tool(s) available"


async def test_mcp_tools_flow_through_policy_and_approval(client: Any, mcp_server: Any) -> None:
    await signup(client)
    await connect_mcp(client)
    settings = (await client.get("/api/v1/ai/settings")).json()["data"]
    names = {t["name"]: t for t in settings["tools"]}
    assert names["mcp_demo_docs__search_docs"]["risk"] == "read"
    assert names["mcp_demo_docs__create_page"]["risk"] == "write"
    assert names["mcp_demo_docs__delete_page"]["risk"] == "destructive"

    # Read tool: runs automatically; result wrapped as untrusted data.
    set_fake_script(
        [
            AIMessage(
                content="",
                tool_calls=[tool_call("mcp_demo_docs__search_docs", {"query": "pricing"}, "c1")],
            ),
            AIMessage(content="Found docs."),
        ]
    )
    events = await chat(client, "search the docs for pricing")
    assert "approval_required" not in types(events)
    step = [e for e in events if e["type"] == "step"][-1]
    assert step["status"] == "completed" and step["label"] == "search docs on Demo Docs"
    tool_msgs = [m for call in captured_prompts for m in call if m.type == "tool"]
    assert "untrusted_content" in str(tool_msgs[0].content)
    assert "Ignore previous instructions" in str(tool_msgs[0].content)  # data, not obeyed

    # Write tool: pauses; approving executes on the MCP server with the stored credential.
    set_fake_script(
        [
            AIMessage(
                content="",
                tool_calls=[tool_call("mcp_demo_docs__create_page", {"title": "Pricing"}, "c2")],
            ),
            AIMessage(content="Created."),
        ]
    )
    events = await chat(client, "create a pricing page")
    approval = next(e for e in events if e["type"] == "approval_required")
    assert approval["proposals"][0]["provider"] == "mcp_server"
    set_fake_script([AIMessage(content="Created.")])
    resumed = await read_sse(
        await client.post(
            "/api/v1/ai/approve",
            json={
                "run_id": approval["run_id"],
                "approval_id": approval["approval_id"],
                "approved_call_ids": ["c2"],
            },
            headers=ORIGIN,
        )
    )
    assert [(e["label"], e["status"]) for e in resumed if e["type"] == "step"][-1] == (
        "create page on Demo Docs",
        "completed",
    )
    assert all(token == MCP_TOKEN for _, token in mcp_server.connection_calls)

    # Invalid arguments never reach the server; unknown-schema violations are reported.
    set_fake_script(
        [
            AIMessage(
                content="", tool_calls=[tool_call("mcp_demo_docs__search_docs", {"nope": 1}, "c3")]
            ),
            AIMessage(content="ok"),
        ]
    )
    await chat(client, "x")
    errors = [
        m
        for call in captured_prompts
        for m in call
        if m.type == "tool" and "Invalid arguments" in str(m.content)
    ]
    assert errors

    audit = (await client.get("/api/v1/audit")).json()["data"]
    assert {a["tool_name"] for a in audit if a["tool_name"]} == {
        "mcp_demo_docs__search_docs",
        "mcp_demo_docs__create_page",
    }


async def test_tool_failure_is_contained(client: Any, mcp_server: Any) -> None:
    await signup(client)
    await connect_mcp(client)
    set_fake_script(
        [
            AIMessage(content="", tool_calls=[tool_call("mcp_demo_docs__failing_tool", {}, "c1")]),
            AIMessage(content="It failed."),
        ]
    )
    events = await chat(client, "run the failing tool")
    step = [e for e in events if e["type"] == "step"][-1]
    assert step["status"] == "failed"
    assert events[-1]["status"] == "completed"
    conn = (await client.get("/api/v1/integrations/connections")).json()["data"][0]
    assert conn["status"] == "connected"  # a tool error is not a connection problem


async def test_disconnect_clears_credentials_and_optionally_purges_data(
    client: Any, mcp_server: Any
) -> None:
    await signup(client)
    conn = await connect_mcp(client)
    async with get_session_factory()() as db:
        row = await db.scalar(select(UserConnection))
        assert row is not None
        db.add(
            ExternalItem(
                tenant_id=row.tenant_id,
                user_id=row.user_id,
                connection_id=row.id,
                provider="mcp_server",
                external_id="doc-1",
                kind="page",
                title="Cached page",
                indexed_at=utcnow(),
            )
        )
        await db.commit()
    detail = (await client.get("/api/v1/integrations/providers/mcp_server")).json()["data"]
    assert detail["local_item_count"] == 1

    # Disconnect without purge keeps indexed data.
    resp = await client.delete(f"/api/v1/integrations/connections/{conn['id']}", headers=ORIGIN)
    assert resp.json()["data"]["status"] == "disconnected"
    assert resp.json()["data"]["external_account_name"] is None
    async with get_session_factory()() as db:
        row = await db.scalar(select(UserConnection))
        assert row is not None and row.access_token_encrypted is None
        assert (await db.scalar(select(ExternalItem))) is not None
    # Tools are gone for the agent.
    tools = (await client.get("/api/v1/ai/settings")).json()["data"]["tools"]
    assert not any(t["provider"] == "mcp_server" for t in tools)

    # Reconnect, then disconnect with purge.
    await connect_mcp(client)
    resp = await client.delete(
        f"/api/v1/integrations/connections/{conn['id']}?purge=true", headers=ORIGIN
    )
    assert resp.status_code == 200
    async with get_session_factory()() as db:
        assert (await db.scalar(select(ExternalItem))) is None
    audit = (await client.get("/api/v1/audit")).json()["data"]
    assert [a["action"] for a in audit][:2] == ["disconnect", "connect"]


async def test_connection_tenant_isolation(client: Any, mcp_server: Any) -> None:
    await signup(client, "ada@example.com")
    conn = await connect_mcp(client)
    client.cookies.clear()
    await signup(client, "bob@example.com")
    assert (await client.get(f"/api/v1/integrations/connections/{conn['id']}")).status_code == 404
    assert (
        await client.delete(f"/api/v1/integrations/connections/{conn['id']}", headers=ORIGIN)
    ).status_code == 404
    assert (await client.get("/api/v1/integrations/connections")).json()["data"] == []


# --- OAuth providers ----------------------------------------------------------------------------


async def test_oauth_connect_flow_with_pkce_state_and_encrypted_tokens(
    client: Any, fake_oauth_provider: Any
) -> None:
    await signup(client)
    start = await client.get(
        "/api/v1/oauth/fakeoauth/start-url", params={"scopes": "files:write,bogus"}
    )
    assert start.status_code == 200
    url = start.json()["data"]["authorize_url"]
    q = parse_qs(urlparse(url).query)
    assert q["client_id"] == ["fake-client"]
    assert q["code_challenge_method"] == ["S256"]
    assert q["scope"] == ["files:read files:write"]  # required + selected optional, bogus dropped
    assert q["redirect_uri"] == ["http://localhost:8000/api/v1/oauth/fakeoauth/callback"]
    state = q["state"][0]

    # Wrong/forged state is refused before any token exchange.
    forged = await client.get(
        "/api/v1/oauth/fakeoauth/callback", params={"code": "good-code", "state": "nope"}
    )
    assert forged.status_code == 302 and "error=OAUTH_STATE_INVALID" in forged.headers["location"]

    # The callback must come from the same signed-in user who started the flow.
    other = await client.get("/api/v1/oauth/fakeoauth/start-url")
    other_state = parse_qs(urlparse(other.json()["data"]["authorize_url"]).query)["state"][0]
    client.cookies.clear()
    await signup(client, "mallory@example.com")
    hijack = await client.get(
        "/api/v1/oauth/fakeoauth/callback", params={"code": "good-code", "state": other_state}
    )
    assert "error=OAUTH_STATE_INVALID" in hijack.headers["location"]
    client.cookies.clear()
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "ada@example.com", "password": "correct horse battery"},
        headers=ORIGIN,
    )
    assert resp.status_code == 200

    done = await client.get(
        "/api/v1/oauth/fakeoauth/callback", params={"code": "good-code", "state": state}
    )
    assert done.status_code == 302
    assert (
        done.headers["location"]
        == "http://localhost:3000/app/settings/connections/fakeoauth?connected=1"
    )

    detail = (await client.get("/api/v1/integrations/providers/fakeoauth")).json()["data"]
    conn = detail["connection"]
    assert conn["status"] == "connected"
    assert conn["external_account_name"] == "Ada @ FakeCloud"
    assert conn["scopes"] == ["files:read", "files:write"]
    assert conn["token_expires_at"] is not None
    async with get_session_factory()() as db:
        row = await db.scalar(select(UserConnection).where(UserConnection.provider == "fakeoauth"))
        assert row is not None
        key = get_settings().encryption_key
        assert crypto.decrypt(row.access_token_encrypted or "", key=key) == "access-1"
        assert crypto.decrypt(row.refresh_token_encrypted or "", key=key) == "refresh-1"
        assert "access-1" not in (row.access_token_encrypted or "")

    # State is single-use.
    again = await client.get(
        "/api/v1/oauth/fakeoauth/callback", params={"code": "good-code", "state": state}
    )
    assert "error=OAUTH_STATE_INVALID" in again.headers["location"]


async def test_oauth_denied_marks_connection_error(client: Any, fake_oauth_provider: Any) -> None:
    await signup(client)
    url = (await client.get("/api/v1/oauth/fakeoauth/start-url")).json()["data"]["authorize_url"]
    state = parse_qs(urlparse(url).query)["state"][0]
    resp = await client.get(
        "/api/v1/oauth/fakeoauth/callback", params={"error": "access_denied", "state": state}
    )
    assert "error=PROVIDER_AUTH_FAILED" in resp.headers["location"]
    conn = (await client.get("/api/v1/integrations/providers/fakeoauth")).json()["data"][
        "connection"
    ]
    assert conn["status"] == "error" and conn["last_error_code"] == "auth_failed"


async def test_oauth_token_refresh_near_expiry(client: Any, fake_oauth_provider: Any) -> None:
    await signup(client)
    url = (await client.get("/api/v1/oauth/fakeoauth/start-url")).json()["data"]["authorize_url"]
    state = parse_qs(urlparse(url).query)["state"][0]
    await client.get(
        "/api/v1/oauth/fakeoauth/callback", params={"code": "good-code", "state": state}
    )
    async with get_session_factory()() as db:
        row = await db.scalar(select(UserConnection).where(UserConnection.provider == "fakeoauth"))
        assert row is not None
        row.token_expires_at = utcnow() + timedelta(minutes=1)  # inside the refresh leeway
        await db.commit()
        conn_id = row.id
    resp = await client.post(f"/api/v1/integrations/connections/{conn_id}/test", headers=ORIGIN)
    assert resp.json()["data"]["healthy"] is True
    assert FakeOAuthProvider.refreshed == 1
    async with get_session_factory()() as db:
        row = await db.scalar(select(UserConnection).where(UserConnection.provider == "fakeoauth"))
        assert row is not None
        key = get_settings().encryption_key
        assert crypto.decrypt(row.access_token_encrypted or "", key=key) == "access-refreshed-1"
        # Rotation: the provider sent no new refresh token, so the old one is kept.
        assert crypto.decrypt(row.refresh_token_encrypted or "", key=key) == "refresh-1"
        assert row.token_expires_at and row.token_expires_at > utcnow() + timedelta(minutes=30)


async def test_oauth_provider_tools_receive_credential(
    client: Any, fake_oauth_provider: Any
) -> None:
    await signup(client)
    url = (await client.get("/api/v1/oauth/fakeoauth/start-url")).json()["data"]["authorize_url"]
    state = parse_qs(urlparse(url).query)["state"][0]
    await client.get(
        "/api/v1/oauth/fakeoauth/callback", params={"code": "good-code", "state": state}
    )
    set_fake_script(
        [
            AIMessage(content="", tool_calls=[tool_call("fakecloud__list_files", {}, "c1")]),
            AIMessage(content="ok"),
        ]
    )
    await chat(client, "list my files")
    tool_msgs = [m for call in captured_prompts for m in call if m.type == "tool"]
    assert '"token_seen": true' in str(tool_msgs[0].content)


# --- webhooks -----------------------------------------------------------------------------------


async def test_webhooks_are_verified_stored_once_and_queued(
    client: Any, fake_oauth_provider: Any
) -> None:
    body = {
        "events": [{"id": "evt-1", "type": "file.created"}, {"id": "evt-2", "type": "file.created"}]
    }
    bad = await client.post(
        "/api/v1/webhooks/fakeoauth", json=body, headers={"x-fake-signature": "nope"}
    )
    assert bad.status_code == 401 and bad.json()["error"]["code"] == "WEBHOOK_REJECTED"

    ok_resp = await client.post(
        "/api/v1/webhooks/fakeoauth", json=body, headers={"x-fake-signature": WEBHOOK_SECRET}
    )
    assert ok_resp.status_code == 202 and ok_resp.json() == {"accepted": 2, "duplicates": 0}
    again = await client.post(
        "/api/v1/webhooks/fakeoauth", json=body, headers={"x-fake-signature": WEBHOOK_SECRET}
    )
    assert again.json() == {"accepted": 0, "duplicates": 2}
    assert [name for name, _ in queue.captured_jobs] == ["process_webhook", "process_webhook"]

    # Unknown provider / provider without webhooks → 404, nothing stored.
    assert (await client.post("/api/v1/webhooks/mcp_server", json={})).status_code == 404

    # Worker processing is idempotent.
    from app.workers.jobs.integrations import process_webhook

    async with get_session_factory()() as db:
        row_id = str(
            await db.scalar(select(WebhookEvent.id).where(WebhookEvent.event_id == "evt-1"))
        )
    assert await process_webhook({}, row_id) is True
    assert await process_webhook({}, row_id) is False
    assert [e["id"] for e in FakeOAuthProvider.handled] == ["evt-1"]


# --- HTTP client retries ------------------------------------------------------------------------


async def test_provider_http_client_retries_only_retryable_failures() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path == "/flaky":
            return (
                httpx.Response(503) if len(calls) == 1 else httpx.Response(200, json={"ok": True})
            )
        if request.url.path == "/forbidden":
            return httpx.Response(403, json={"error": "scope"})
        if request.url.path == "/ratelimited":
            return httpx.Response(429, headers={"Retry-After": "0"})
        return httpx.Response(200)

    async with ProviderHttpClient(
        provider="demo",
        base_url="https://api.example",
        transport=httpx.MockTransport(handler),
        max_attempts=2,
    ) as http:
        # Patch backoff to keep the test fast.
        async def no_sleep(*_: Any) -> None:
            return None

        http._backoff = no_sleep  # type: ignore[method-assign, assignment]
        assert (await http.get("/flaky")).json() == {"ok": True}
        assert calls.count("/flaky") == 2

        with pytest.raises(ProviderError) as exc:
            await http.get("/forbidden")
        assert (
            exc.value.kind == ProviderErrorKind.permission_denied and calls.count("/forbidden") == 1
        )
        assert exc.value.as_api_error().status_code == 403

        with pytest.raises(ProviderError) as exc2:
            await http.get("/ratelimited")
        assert (
            exc2.value.kind == ProviderErrorKind.rate_limited and calls.count("/ratelimited") == 2
        )


# --- provider contract (every registered provider) ----------------------------------------------


@pytest.mark.parametrize("provider_id", list(get_providers()))
def test_provider_contract(provider_id: str) -> None:
    provider = get_providers()[provider_id]
    m = provider.manifest
    assert m.id == provider_id and m.name and m.category
    assert m.capabilities, "a provider must advertise capabilities"
    if m.auth.value == "oauth2":
        assert m.permissions, "OAuth providers must declare requestable permissions"
        assert provider.scopes_for(None) == [p.scope for p in m.permissions if p.required]
    for f in m.config_fields:
        assert f.key and f.label
    assert isinstance(provider.is_configured(get_settings()), bool)
