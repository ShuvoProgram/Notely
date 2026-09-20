"""Every vendor adapter, end to end against its mocked API: OAuth (vendor-specific token endpoint
style), identity, health test, unified search, a read tool (auto) and a write tool (approval)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest
from langchain_core.messages import AIMessage

from app.ai.llm import captured_prompts, set_fake_script
from app.core import oauth as core_oauth
from app.integrations.base import http as provider_http
from app.tests.conftest import ORIGIN, read_sse, signup
from app.tests.test_ai import chat, tool_call, types
from app.tests.vendor_mocks import VendorMock, combined_transport

# Per provider: expected authorize host, scope query param, account name, search hit title,
# read tool + args, write tool + args + (method, path fragment, payload assertion).
CASES: dict[str, dict[str, Any]] = {
    "slack": {
        "authorize_host": "slack.com",
        "scope_param": "user_scope",
        "account": "ada @ Acme",
        "search_title": "#launch",
        "read": ("slack__list_channels", {}, "general"),
        "write": (
            "slack__post_message",
            {"channel_id": "C1", "text": "Ship it"},
            "POST",
            "chat.postMessage",
            "external_communication",
        ),
    },
    "notion": {
        "authorize_host": "api.notion.com",
        "scope_param": None,
        "account": "Ada @ Acme Wiki",
        "search_title": "Launch plan",
        "read": ("notion__read_page", {"page_id": "p1"}, "Ship Friday."),
        "write": (
            "notion__create_page",
            {"parent_page_id": "p1", "title": "Retro", "body": "went well"},
            "POST",
            "/v1/pages",
            "write",
        ),
    },
    "todoist": {
        "authorize_host": "todoist.com",
        "scope_param": "scope",
        "account": "Todoist account",
        "search_title": "Finalize pricing",
        "read": ("todoist__list_tasks", {}, "Finalize pricing"),
        "write": (
            "todoist__create_task",
            {"content": "Email the team", "priority": 3},
            "POST",
            "/rest/v2/tasks",
            "write",
        ),
    },
    "asana": {
        "authorize_host": "app.asana.com",
        "scope_param": "scope",
        "account": "Ada @ Acme",
        "search_title": "Launch pricing page",
        "read": ("asana__my_tasks", {}, "Launch pricing page"),
        "write": ("asana__complete_task", {"task_gid": "t1"}, "PUT", "/tasks/t1", "write"),
    },
    "jira": {
        "authorize_host": "auth.atlassian.com",
        "scope_param": "scope",
        "account": "Ada @ Acme",
        "search_title": "PROJ-482: Pricing page",
        "read": ("jira__read_issue", {"issue_key": "PROJ-482"}, "Finalize the pricing page."),
        "write": (
            "jira__create_issue",
            {"project_key": "PROJ", "summary": "Fix typo", "description": "On the pricing page"},
            "POST",
            "/rest/api/3/issue",
            "write",
        ),
    },
    "microsoft_teams": {
        "authorize_host": "login.microsoftonline.com",
        "scope_param": "scope",
        "account": "Ada Lovelace (ada@acme.io)",
        "search_title": None,
        "read": (
            "microsoft_teams__read_channel",
            {"team_id": "team-1", "channel_id": "chan-1"},
            "Launch is Friday",
        ),
        "write": (
            "microsoft_teams__send_channel_message",
            {"team_id": "team-1", "channel_id": "chan-1", "text": "Hi"},
            "POST",
            "/channels/chan-1/messages",
            "external_communication",
        ),
    },
    "outlook": {
        "authorize_host": "login.microsoftonline.com",
        "scope_param": "scope",
        "account": "Ada Lovelace (ada@acme.io)",
        "search_title": "Q4 Launch Pricing",
        "read": ("outlook__read_mail", {"message_id": "mail-1"}, "finalize pricing"),
        "write": (
            "outlook__send_mail",
            {"to": ["bob@acme.io"], "subject": "Hi", "body": "Hello"},
            "POST",
            "/me/sendMail",
            "external_communication",
        ),
    },
    "gmail": {
        "authorize_host": "accounts.google.com",
        "scope_param": "scope",
        "account": "ada@acme.io",
        "search_title": "Q4 Launch Pricing",
        "read": ("gmail__read_mail", {"message_id": "m1"}, "finalize pricing"),
        "write": (
            "gmail__send_mail",
            {"to": ["bob@acme.io"], "subject": "Hi", "body": "Hello"},
            "POST",
            "/messages/send",
            "external_communication",
        ),
    },
    "google_calendar": {
        "authorize_host": "accounts.google.com",
        "scope_param": "scope",
        "account": "ada@acme.io",
        "search_title": "Pricing review",
        "read": ("google_calendar__list_events", {"days": 7}, "Pricing review"),
        "write": (
            "google_calendar__create_event",
            {
                "summary": "Launch follow-up",
                "start": "2026-09-23T10:00:00+00:00",
                "end": "2026-09-23T10:30:00+00:00",
                "attendees": ["bob@acme.io"],
            },
            "POST",
            "/calendars/primary/events",
            "write",
        ),
    },
    "google_drive": {
        "authorize_host": "accounts.google.com",
        "scope_param": "scope",
        "account": "ada@acme.io",
        "search_title": "Pricing plan",
        "read": ("google_drive__read_text_file", {"file_id": "f1"}, "# Pricing plan"),
        "write": (
            "google_drive__upload_text_file",
            {"name": "summary.md", "content": "hello"},
            "POST",
            "/upload/drive/v3/files",
            "write",
        ),
    },
    "onedrive": {
        "authorize_host": "login.microsoftonline.com",
        "scope_param": "scope",
        "account": "Ada Lovelace (ada@acme.io)",
        "search_title": "pricing.md",
        "read": ("onedrive__read_text_file", {"item_id": "it-1"}, "# Pricing"),
        "write": (
            "onedrive__upload_text_file",
            {"path": "Notes/summary.md", "content": "hello"},
            "PUT",
            "/me/drive/root:/Notes/summary.md:/content",
            "write",
        ),
    },
    "clickup": {
        "authorize_host": "app.clickup.com",
        "scope_param": "scope",
        "account": "ada @ Acme",
        "search_title": "Finalize pricing",
        "read": ("clickup__read_task", {"task_id": "task-1"}, "Pricing page"),
        "write": (
            "clickup__create_task",
            {"list_id": "list-1", "name": "Email the team"},
            "POST",
            "/list/list-1/task",
            "write",
        ),
    },
    "dropbox": {
        "authorize_host": "www.dropbox.com",
        "scope_param": "scope",
        "account": "Ada (ada@acme.io)",
        "search_title": "plan.md",
        "read": ("dropbox__read_text_file", {"path": "/plan.md"}, "# Plan"),
        "write": (
            "dropbox__upload_text_file",
            {"path": "/notes/summary.md", "content": "hello"},
            "POST",
            "/2/files/upload",
            "write",
        ),
    },
}


def write_capability(provider_id: str, tool_name: str) -> str:
    from app.integrations.registry import get_provider

    provider = get_provider(provider_id)
    assert provider is not None
    for tool in provider.build_tools():  # type: ignore[attr-defined]
        if f"{provider_id}__{tool.name}" == tool_name:
            return str(tool.capability.value)
    raise AssertionError(tool_name)


# Which OAuth client settings each provider reads.
SETTINGS_PREFIX: dict[str, str | None] = {
    "microsoft_teams": "microsoft",
    "outlook": "microsoft",
    "onedrive": "microsoft",
    "gmail": "google",
    "google_calendar": "google",
    "google_drive": "google",
}


async def connect(client: Any, provider_id: str, case: dict[str, Any]) -> dict[str, Any]:
    return await connect_via_oauth(client, provider_id, case)


@pytest.fixture
def vendor(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> Iterator[VendorMock]:
    provider_id: str = request.param
    from app.core.config import get_settings

    settings = get_settings()
    prefix = SETTINGS_PREFIX.get(provider_id, provider_id)
    if prefix is not None:
        monkeypatch.setattr(settings, f"oauth_{prefix}_client_id", "test-id")
        monkeypatch.setattr(settings, f"oauth_{prefix}_client_secret", "test-secret")
    mock = VendorMock(provider_id)
    transport = combined_transport({provider_id: mock})
    core_oauth.set_http_transport(transport)
    provider_http.set_transport_override(lambda _pid: transport)
    yield mock
    core_oauth.set_http_transport(None)
    provider_http.set_transport_override(None)


async def connect_via_oauth(client: Any, provider_id: str, case: dict[str, Any]) -> dict[str, Any]:
    start = await client.get(f"/api/v1/oauth/{provider_id}/start-url")
    assert start.status_code == 200, start.text
    url = start.json()["data"]["authorize_url"]
    parsed = urlparse(url)
    q = parse_qs(parsed.query)
    assert parsed.hostname == case["authorize_host"]
    assert q["client_id"] == ["test-id"] and q["state"]
    if case["scope_param"]:
        assert case["scope_param"] in q and q[case["scope_param"]][0]
    cb = await client.get(
        f"/api/v1/oauth/{provider_id}/callback",
        params={"code": "good-code", "state": q["state"][0]},
    )
    assert cb.status_code == 302, cb.text
    assert cb.headers["location"].endswith("?connected=1"), cb.headers["location"]
    detail = (await client.get(f"/api/v1/integrations/providers/{provider_id}")).json()["data"]
    return detail


@pytest.mark.parametrize("vendor", list(CASES), indirect=True)
async def test_provider_end_to_end(client: Any, vendor: VendorMock) -> None:
    provider_id = vendor.provider
    case = CASES[provider_id]
    await signup(client)

    # Not connected yet, but configured (client id/secret present).
    listing = {
        p["id"]: p for p in (await client.get("/api/v1/integrations/providers")).json()["data"]
    }
    assert listing[provider_id]["configured"] is True

    detail = await connect(client, provider_id, case)
    conn = detail["connection"]
    assert conn["status"] == "connected", conn
    assert conn["external_account_name"] == case["account"]
    assert conn["auth_type"] == "oauth2"

    # Health test reports the standard four steps.
    test = (
        await client.post(f"/api/v1/integrations/connections/{conn['id']}/test", headers=ORIGIN)
    ).json()["data"]
    assert test["healthy"] is True, test
    assert [s["name"] for s in test["steps"]] == [
        "Authentication",
        "Permissions",
        "API availability",
        "Tool access",
    ]

    # Unified search includes the provider as a source.
    search = (await client.get("/api/v1/search", params={"q": "pricing"})).json()["data"]
    statuses = {s["source"]: s for s in search["sources"]}
    assert statuses[provider_id]["ok"] is True
    if case["search_title"]:
        assert any(
            h["source"] == provider_id and h["title"] == case["search_title"]
            for h in search["hits"]
        )

    # Tools are exposed with the right risk levels.
    tools = {
        t["name"]: t for t in (await client.get("/api/v1/ai/settings")).json()["data"]["tools"]
    }
    read_name, read_args, read_expect = case["read"]
    write_name, write_args, method, path_part, write_risk = case["write"]
    assert tools[read_name]["risk"] == "read"
    assert tools[write_name]["risk"] == write_risk

    # Read tool runs automatically and returns untrusted-wrapped content.
    set_fake_script(
        [
            AIMessage(content="", tool_calls=[tool_call(read_name, read_args, "c1")]),
            AIMessage(content="ok"),
        ]
    )
    events = await chat(client, "read something")
    assert "approval_required" not in types(events), types(events)
    last_step = [e for e in events if e["type"] == "step"][-1]
    assert last_step["status"] == "completed", last_step
    tool_msg = [m for call in captured_prompts for m in call if m.type == "tool"][0]
    assert read_expect in str(tool_msg.content)
    assert "untrusted_content" in str(tool_msg.content)

    # Write tool pauses; approval executes it against the vendor with the right request.
    before = len(vendor.captured.requests)
    set_fake_script(
        [
            AIMessage(content="", tool_calls=[tool_call(write_name, write_args, "c2")]),
            AIMessage(content="done"),
        ]
    )
    events = await chat(client, "write something")
    approval = next(e for e in events if e["type"] == "approval_required")
    assert approval["proposals"][0]["provider"] == provider_id
    assert len(vendor.captured.requests) == before, "nothing may reach the vendor before approval"
    set_fake_script([AIMessage(content="done")])
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
    assert [e for e in resumed if e["type"] == "step"][-1]["status"] == "completed"
    sent = vendor.captured.find(method, path_part)
    assert sent is not None, [f"{r.method} {r.url}" for r in vendor.captured.requests]

    # Phase 6: every provider write is read back and the outcome streamed + persisted.
    verification = next(e for e in resumed if e["type"] == "verification")
    assert verification["status"] == "verified", verification
    run = (await client.get(f"/api/v1/ai/runs/{approval['run_id']}")).json()["data"]
    written = next(tc for tc in run["tool_calls"] if tc["call_id"] == "c2")
    assert written["status"] == "executed"
    assert written["verification"]["status"] == "verified"

    audit = (await client.get("/api/v1/audit")).json()["data"]
    assert {a["tool_name"] for a in audit if a["tool_name"]} == {read_name, write_name}
    assert all(a["provider"] == provider_id for a in audit)
    assert {(a["action"], a["status"]) for a in audit if a["tool_name"] == write_name} == {
        (write_capability(provider_id, write_name), "completed"),
        ("verify", "verified"),
    }


@pytest.mark.parametrize("vendor", ["slack", "jira"], indirect=True)
async def test_provider_auth_failure_marks_connection_expired(
    client: Any, vendor: VendorMock
) -> None:
    await signup(client)
    await connect_via_oauth(client, vendor.provider, CASES[vendor.provider])
    vendor.fail_auth = True
    search = (await client.get("/api/v1/search", params={"q": "x"})).json()["data"]
    status = next(s for s in search["sources"] if s["source"] == vendor.provider)
    assert status["ok"] is False and status["error"]
    conn = (await client.get("/api/v1/integrations/connections")).json()["data"][0]
    assert conn["status"] == "expired"
    assert conn["last_error_code"] in ("expired", "auth_failed")
    # Tools disappear until the user reconnects.
    tools = (await client.get("/api/v1/ai/settings")).json()["data"]["tools"]
    assert not any(t["provider"] == vendor.provider for t in tools)


def test_vendor_payload_shapes() -> None:
    """Pure helpers that shape vendor payloads."""
    from app.integrations.jira.provider import _adf, _adf_text
    from app.integrations.notion.provider import _rich_text, _title_of
    from app.integrations.slack.provider import parse_slack_tokens

    doc = _adf("Hello\n\nWorld")
    assert doc["version"] == 1 and len(doc["content"]) == 2
    assert _adf_text(doc).split() == ["Hello", "World"]
    assert (
        _title_of({"properties": {"N": {"type": "title", "title": [{"plain_text": "T"}]}}}) == "T"
    )
    assert (
        _rich_text([{"type": "heading_1", "heading_1": {"rich_text": [{"plain_text": "H"}]}}])
        == "H"
    )
    tokens = parse_slack_tokens(
        {"ok": True, "authed_user": {"access_token": "xoxp", "scope": "search:read"}}
    )
    assert tokens.access_token == "xoxp" and tokens.scope == "search:read"
    from app.core.exceptions import OAuthExchangeFailed

    with pytest.raises(OAuthExchangeFailed):
        parse_slack_tokens({"ok": False, "error": "invalid_code"})
