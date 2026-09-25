"""Connector tools added for Outlook, OneDrive, Dropbox, Slack, Teams, Asana and Todoist.

Each tool runs its real handler against a recording stand-in for the vendor's official API:
the tests assert the exact request the vendor receives, what the tool returns, and that the
read-back verification agrees. Permission gating is checked through `tools()`, which is what
the assistant and the automation catalog are offered.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from urllib.parse import parse_qs

import httpx
import pytest

from app.core.config import get_settings
from app.integrations.base import http as provider_http
from app.integrations.base.errors import ProviderError, ProviderErrorKind
from app.integrations.base.provider import ProviderContext, ProviderCredentials
from app.integrations.base.rest import ProviderTool, RestOAuthProvider
from app.integrations.registry import get_provider

Responder = Callable[[httpx.Request], Any]


@dataclass
class Vendor:
    """Routes (METHOD, path suffix) to a JSON body (or a callable returning one)."""

    routes: dict[tuple[str, str], Any] = field(default_factory=dict)
    requests: list[httpx.Request] = field(default_factory=list)

    def on(self, method: str, path: str, body: Any) -> Vendor:
        self.routes[(method, path)] = body
        return self

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        for (method, path), body in self.routes.items():
            if request.method == method and request.url.path.endswith(path):
                payload = body(request) if callable(body) else body
                if isinstance(payload, httpx.Response):
                    return payload
                return httpx.Response(200, json=payload)
        return httpx.Response(404, json={"error": f"unrouted {request.method} {request.url}"})

    def sent(self, method: str, path: str) -> httpx.Request:
        found = [r for r in self.requests if r.method == method and r.url.path.endswith(path)]
        assert found, f"no {method} {path}: {[f'{r.method} {r.url}' for r in self.requests]}"
        return found[-1]

    def json(self, method: str, path: str) -> Any:
        return json.loads(self.sent(method, path).content or b"null")

    def form(self, method: str, path: str) -> dict[str, str]:
        raw = parse_qs(self.sent(method, path).content.decode())
        return {k: v[0] for k, v in raw.items()}


@pytest.fixture
def vendor() -> Iterator[Vendor]:
    v = Vendor()
    transport = httpx.MockTransport(v.handle)
    provider_http.set_transport_override(lambda _pid: transport)
    yield v
    provider_http.set_transport_override(None)


def ctx_for(scopes: list[str] | None = None, metadata: dict[str, Any] | None = None) -> Any:
    connection = SimpleNamespace(id=uuid.uuid4(), scopes=scopes or [], metadata_=metadata or {})
    return ProviderContext(
        user=None,  # type: ignore[arg-type]
        db=None,  # type: ignore[arg-type]
        connection=connection,  # type: ignore[arg-type]
        credentials=ProviderCredentials(access_token="token"),
        settings=get_settings(),
    )


def tool(provider_id: str, name: str) -> tuple[RestOAuthProvider, ProviderTool]:
    provider = get_provider(provider_id)
    assert isinstance(provider, RestOAuthProvider)
    found = next(t for t in provider.build_tools() if t.name == name)
    return provider, found


async def run(provider_id: str, name: str, args: dict[str, Any], ctx: Any = None) -> Any:
    _, t = tool(provider_id, name)
    return await t.handler(ctx or ctx_for(), t.args_model.model_validate(args))


async def verify(provider_id: str, name: str, args: dict[str, Any], result: dict[str, Any]) -> Any:
    _, t = tool(provider_id, name)
    assert t.verify is not None
    return await t.verify(ctx_for(), t.args_model.model_validate(args), result)


async def offered(provider_id: str, scopes: list[str]) -> set[str]:
    provider = get_provider(provider_id)
    assert provider is not None
    return {s.name.split("__", 1)[1] for s in await provider.tools(ctx_for(scopes))}


# --- least privilege: optional permissions gate their tools -----------------------------------


@pytest.mark.parametrize(
    ("provider_id", "base", "optional", "gated"),
    [
        (
            "outlook",
            ["User.Read", "Mail.Read", "Calendars.Read", "offline_access"],
            {
                "Mail.ReadWrite": {"draft_mail"},
                "Mail.Send": {"send_mail"},
                "Calendars.ReadWrite": {"create_event"},
                "People.Read": {"find_people"},
            },
            {"draft_mail", "send_mail", "create_event", "find_people"},
        ),
        (
            "onedrive",
            ["User.Read", "Files.Read", "offline_access"],
            {"Files.ReadWrite": {"upload_text_file", "create_folder", "move"}},
            {"upload_text_file", "create_folder", "move"},
        ),
        (
            "dropbox",
            ["account_info.read", "files.metadata.read", "files.content.read"],
            {"files.content.write": {"upload_text_file", "create_folder", "move"}},
            {"upload_text_file", "create_folder", "move"},
        ),
        (
            "slack",
            ["search:read", "channels:read", "channels:history", "users:read"],
            {"chat:write": {"post_message"}, "channels:manage": {"create_channel"}},
            {"post_message", "create_channel"},
        ),
        (
            "microsoft_teams",
            [
                "User.Read",
                "Team.ReadBasic.All",
                "Channel.ReadBasic.All",
                "ChannelMessage.Read.All",
                "offline_access",
            ],
            {
                "ChannelMessage.Send": {"send_channel_message", "reply_to_message"},
                "OnlineMeetings.ReadWrite": {"create_meeting"},
            },
            {"send_channel_message", "reply_to_message", "create_meeting"},
        ),
        (
            "todoist",
            ["data:read", "task:add"],
            {"data:read_write": {"update_task", "move_task", "complete_task"}},
            {"update_task", "move_task", "complete_task"},
        ),
    ],
)
async def test_optional_permissions_gate_exactly_their_tools(
    provider_id: str, base: list[str], optional: dict[str, set[str]], gated: set[str]
) -> None:
    without = await offered(provider_id, base)
    assert not (without & gated), f"offered without permission: {without & gated}"
    for scope, tools in optional.items():
        assert tools <= await offered(provider_id, [*base, scope]), scope
    provider = get_provider(provider_id)
    assert provider is not None
    declared = {p.scope for p in provider.manifest.permissions}
    assert set(optional) <= declared, "every gating scope is a permission the user can grant"


# --- Todoist ------------------------------------------------------------------------------------


async def test_todoist_update_task_sends_only_changed_fields(vendor: Vendor) -> None:
    vendor.on(
        "POST",
        "/tasks/t1",
        {"id": "t1", "content": "Ship", "priority": 4, "due": {"date": "2026-10-01"}},
    )
    vendor.on(
        "GET",
        "/tasks/t1",
        {"id": "t1", "content": "Ship", "priority": 4, "due": {"date": "2026-10-01"}},
    )
    args = {"task_id": "t1", "priority": 4, "due_date": "2026-10-01"}
    result = await run("todoist", "update_task", args)
    assert vendor.json("POST", "/tasks/t1") == {"priority": 4, "due_date": "2026-10-01"}
    assert result["due"] == "2026-10-01"
    assert (await verify("todoist", "update_task", args, result)).status == "verified"


async def test_todoist_update_task_with_nothing_to_change_is_refused(vendor: Vendor) -> None:
    with pytest.raises(ProviderError) as err:
        await run("todoist", "update_task", {"task_id": "t1"})
    assert err.value.kind == ProviderErrorKind.invalid_request
    assert vendor.requests == []


async def test_todoist_move_task_uses_the_sync_item_move_command(vendor: Vendor) -> None:
    def sync(request: httpx.Request) -> dict[str, Any]:
        command = json.loads(request.content)["commands"][0]
        return {"sync_status": {command["uuid"]: "ok"}}

    vendor.on("POST", "/sync/v9/sync", sync)
    vendor.on("GET", "/tasks/t1", {"id": "t1", "project_id": "p2"})
    result = await run("todoist", "move_task", {"task_id": "t1", "project_id": "p2"})
    command = vendor.json("POST", "/sync/v9/sync")["commands"][0]
    assert command["type"] == "item_move" and command["args"] == {"id": "t1", "project_id": "p2"}
    verdict = await verify("todoist", "move_task", {"task_id": "t1", "project_id": "p2"}, result)
    assert verdict.status == "verified"


async def test_todoist_move_task_reports_a_refused_move(vendor: Vendor) -> None:
    vendor.on("POST", "/sync/v9/sync", {"sync_status": {}})
    with pytest.raises(ProviderError):
        await run("todoist", "move_task", {"task_id": "t1", "project_id": "p2"})


async def test_todoist_list_tasks_combines_filter_and_search(vendor: Vendor) -> None:
    vendor.on("GET", "/tasks", [])
    await run("todoist", "list_tasks", {"filter": "today", "search": "invoice"})
    assert vendor.sent("GET", "/tasks").url.params["filter"] == "(today) & (search: invoice)"


# --- Asana --------------------------------------------------------------------------------------


async def test_asana_create_task_assigns_someone_else(vendor: Vendor) -> None:
    vendor.on("POST", "/tasks", {"data": {"gid": "9", "permalink_url": "https://app.asana.com/9"}})
    ctx = ctx_for(metadata={"workspace_gid": "w1"})
    await run(
        "asana",
        "create_task",
        {"name": "Review requirements", "assignee": "sarah@acme.io", "due_on": "2026-10-02"},
        ctx,
    )
    assert vendor.json("POST", "/tasks")["data"] == {
        "name": "Review requirements",
        "assignee": "sarah@acme.io",
        "workspace": "w1",
        "due_on": "2026-10-02",
    }


async def test_asana_find_people_and_projects_use_typeahead(vendor: Vendor) -> None:
    def typeahead(request: httpx.Request) -> dict[str, Any]:
        kind = request.url.params["resource_type"]
        if kind == "user":
            return {"data": [{"gid": "u7", "name": "Sarah Lee", "email": "sarah@acme.io"}]}
        return {
            "data": [
                {"gid": "p1", "name": "Alpha", "archived": False},
                {"gid": "p0", "name": "Old", "archived": True},
            ]
        }

    vendor.on("GET", "/workspaces/w1/typeahead", typeahead)
    ctx = ctx_for(metadata={"workspace_gid": "w1"})
    people = await run("asana", "find_people", {"query": "Sarah"}, ctx)
    assert people["people"] == [{"gid": "u7", "name": "Sarah Lee", "email": "sarah@acme.io"}]
    projects = await run("asana", "search_projects", {"query": "Al"}, ctx)
    assert [p["gid"] for p in projects["projects"]] == ["p1"]  # archived projects left out


async def test_asana_update_task_clears_or_sets_due_date(vendor: Vendor) -> None:
    vendor.on("PUT", "/tasks/9", {"data": {"gid": "9", "name": "X", "due_on": None}})
    await run("asana", "update_task", {"task_gid": "9", "clear_due_date": True, "assignee": "me"})
    assert vendor.json("PUT", "/tasks/9") == {"data": {"assignee": "me", "due_on": None}}


async def test_asana_read_task_keeps_only_comments(vendor: Vendor) -> None:
    vendor.on(
        "GET",
        "/tasks/9",
        {
            "data": {
                "gid": "9",
                "name": "X",
                "assignee": {"name": "Ada"},
                "projects": [{"name": "Alpha"}],
            }
        },
    )
    vendor.on(
        "GET",
        "/tasks/9/stories",
        {
            "data": [
                {"type": "system", "text": "Ada created this task"},
                {"type": "comment", "text": "Looks good", "created_by": {"name": "Sarah"}},
            ]
        },
    )
    task = await run("asana", "read_task", {"task_gid": "9"})
    assert task["assignee"] == "Ada" and task["projects"] == ["Alpha"]
    assert [c["author"] for c in task["comments"]] == ["Sarah"]
    assert "Looks good" in task["comments"][0]["text"]


async def test_asana_add_comment_posts_a_story(vendor: Vendor) -> None:
    vendor.on("POST", "/tasks/9/stories", {"data": {"gid": "s1"}})
    vendor.on("GET", "/tasks/9/stories", {"data": [{"gid": "s1", "type": "comment"}]})
    args = {"task_gid": "9", "text": "Done on our side"}
    result = await run("asana", "add_comment", args)
    assert vendor.json("POST", "/tasks/9/stories") == {"data": {"text": "Done on our side"}}
    assert (await verify("asana", "add_comment", args, result)).status == "verified"


# --- Dropbox ------------------------------------------------------------------------------------


async def test_dropbox_create_folder_and_move(vendor: Vendor) -> None:
    vendor.on(
        "POST",
        "/files/create_folder_v2",
        {"metadata": {"path_display": "/Projects/Alpha", "id": "id:1"}},
    )
    vendor.on(
        "POST",
        "/files/move_v2",
        {"metadata": {"path_display": "/Projects/Alpha/spec.md", "id": "id:2"}},
    )

    def meta(request: httpx.Request) -> dict[str, Any]:
        return {"path_display": json.loads(request.content)["path"]}

    vendor.on("POST", "/files/get_metadata", meta)
    folder = await run("dropbox", "create_folder", {"path": "/Projects/Alpha"})
    assert vendor.json("POST", "/files/create_folder_v2") == {
        "path": "/Projects/Alpha",
        "autorename": False,
    }
    assert (
        await verify("dropbox", "create_folder", {"path": "/Projects/Alpha"}, folder)
    ).status == "verified"

    args = {"from_path": "/spec.md", "to_path": "/Projects/Alpha/spec.md"}
    moved = await run("dropbox", "move", args)
    assert vendor.json("POST", "/files/move_v2") == {**args, "autorename": False}
    assert (await verify("dropbox", "move", args, moved)).status == "verified"


# --- OneDrive -----------------------------------------------------------------------------------


async def test_onedrive_create_folder_never_overwrites(vendor: Vendor) -> None:
    vendor.on(
        "POST", "/me/drive/items/parent1/children", {"id": "f1", "name": "Alpha", "folder": {}}
    )
    vendor.on("GET", "/me/drive/items/f1", {"id": "f1", "name": "Alpha", "folder": {}})
    args = {"name": "Alpha", "parent_item_id": "parent1"}
    result = await run("onedrive", "create_folder", args)
    assert vendor.json("POST", "/children") == {
        "name": "Alpha",
        "folder": {},
        "@microsoft.graph.conflictBehavior": "fail",
    }
    assert (await verify("onedrive", "create_folder", args, result)).status == "verified"


async def test_onedrive_move_renames_and_relocates_in_one_patch(vendor: Vendor) -> None:
    item = {"id": "i1", "name": "spec-v2.md", "parentReference": {"id": "dest"}}
    vendor.on("PATCH", "/me/drive/items/i1", item)
    vendor.on("GET", "/me/drive/items/i1", item)
    args = {"item_id": "i1", "new_name": "spec-v2.md", "destination_folder_id": "dest"}
    result = await run("onedrive", "move", args)
    assert vendor.json("PATCH", "/me/drive/items/i1") == {
        "name": "spec-v2.md",
        "parentReference": {"id": "dest"},
    }
    assert (await verify("onedrive", "move", args, result)).status == "verified"
    with pytest.raises(ProviderError):
        await run("onedrive", "move", {"item_id": "i1"})


# --- Outlook ------------------------------------------------------------------------------------


async def test_outlook_list_mail_filters_unread_since_a_time(vendor: Vendor) -> None:
    vendor.on(
        "GET",
        "/me/mailFolders/inbox/messages",
        {
            "value": [
                {
                    "id": "m1",
                    "subject": "Contract",
                    "from": {"emailAddress": {"address": "ceo@client.io"}},
                    "isRead": False,
                    "importance": "high",
                    "bodyPreview": "Please sign",
                    "receivedDateTime": "2026-09-25T08:00:00Z",
                }
            ]
        },
    )
    since = datetime(2026, 9, 25, tzinfo=UTC).isoformat()
    result = await run("outlook", "list_mail", {"unread_only": True, "received_after": since})
    params = vendor.sent("GET", "/me/mailFolders/inbox/messages").url.params
    assert params["$filter"] == "isRead eq false and receivedDateTime ge 2026-09-25T00:00:00Z"
    assert params["$orderby"] == "receivedDateTime desc" and "$search" not in params
    email = result["emails"][0]
    assert (
        email["unread"] is True and email["important"] is True and email["from"] == "ceo@client.io"
    )


async def test_outlook_find_people(vendor: Vendor) -> None:
    vendor.on(
        "GET",
        "/me/people",
        {
            "value": [
                {"displayName": "Sarah Lee", "scoredEmailAddresses": [{"address": "sarah@acme.io"}]}
            ]
        },
    )
    result = await run("outlook", "find_people", {"query": "Sarah"})
    assert result["people"][0]["email"] == "sarah@acme.io"
    assert vendor.sent("GET", "/me/people").url.params["$search"] == '"Sarah"'


# --- Teams --------------------------------------------------------------------------------------


async def test_teams_create_meeting_defaults_to_thirty_minutes(vendor: Vendor) -> None:
    vendor.on(
        "POST", "/me/onlineMeetings", {"id": "om1", "joinWebUrl": "https://teams.microsoft.com/l/1"}
    )
    vendor.on(
        "GET",
        "/me/onlineMeetings/om1",
        {"id": "om1", "joinWebUrl": "https://teams.microsoft.com/l/1"},
    )
    args = {"subject": "Client sync", "start": "2026-09-26T15:00:00+00:00"}
    result = await run("microsoft_teams", "create_meeting", args)
    sent = vendor.json("POST", "/me/onlineMeetings")
    assert sent["endDateTime"] == "2026-09-26T15:30:00+00:00"
    assert result["join_url"] == "https://teams.microsoft.com/l/1"
    assert (await verify("microsoft_teams", "create_meeting", args, result)).status == "verified"


async def test_teams_reply_goes_to_the_thread(vendor: Vendor) -> None:
    vendor.on("POST", "/messages/m1/replies", {"id": "r1"})
    await run(
        "microsoft_teams",
        "reply_to_message",
        {"team_id": "t", "channel_id": "c", "message_id": "m1", "text": "On it"},
    )
    assert (
        vendor.sent("POST", "/replies").url.path == "/v1.0/teams/t/channels/c/messages/m1/replies"
    )


# --- Slack --------------------------------------------------------------------------------------


def slack_api(pages: list[list[dict[str, Any]]]) -> Callable[[httpx.Request], dict[str, Any]]:
    def conversations_list(request: httpx.Request) -> dict[str, Any]:
        cursor = parse_qs(request.content.decode()).get("cursor", ["0"])[0]
        index = int(cursor)
        nxt = str(index + 1) if index + 1 < len(pages) else ""
        return {"ok": True, "channels": pages[index], "response_metadata": {"next_cursor": nxt}}

    return conversations_list


async def test_slack_posts_to_a_channel_by_name_across_pages(vendor: Vendor) -> None:
    vendor.on(
        "POST",
        "/conversations.list",
        slack_api([[{"id": "C1", "name": "general"}], [{"id": "C2", "name": "marketing"}]]),
    )
    vendor.on("POST", "/chat.postMessage", lambda r: {"ok": True, "ts": "1.1", "channel": "C2"})
    result = await run("slack", "post_message", {"channel": "#Marketing", "text": "Update"})
    assert vendor.form("POST", "/chat.postMessage") == {"channel": "C2", "text": "Update"}
    assert result["channel"] == "C2"


async def test_slack_saved_automations_with_channel_id_still_work(vendor: Vendor) -> None:
    vendor.on("POST", "/chat.postMessage", {"ok": True, "ts": "1.1", "channel": "C0123ABCDE"})
    await run("slack", "post_message", {"channel_id": "C0123ABCDE", "text": "hi"})
    assert vendor.form("POST", "/chat.postMessage")["channel"] == "C0123ABCDE"
    assert not [r for r in vendor.requests if r.url.path.endswith("/conversations.list")]


async def test_slack_unknown_channel_is_not_found(vendor: Vendor) -> None:
    vendor.on("POST", "/conversations.list", slack_api([[{"id": "C1", "name": "general"}]]))
    with pytest.raises(ProviderError) as err:
        await run("slack", "post_message", {"channel": "nope", "text": "x"})
    assert err.value.kind == ProviderErrorKind.not_found


async def test_slack_read_channel_shows_author_names(vendor: Vendor) -> None:
    vendor.on("POST", "/conversations.list", slack_api([[{"id": "C2", "name": "marketing"}]]))
    vendor.on(
        "POST",
        "/conversations.history",
        {"ok": True, "messages": [{"ts": "1", "user": "U9", "text": "Launch?"}]},
    )
    vendor.on(
        "POST",
        "/users.info",
        {"ok": True, "user": {"real_name": "Sarah Lee", "profile": {"display_name": "sarah"}}},
    )
    result = await run("slack", "read_channel", {"channel": "marketing"})
    assert result["messages"][0]["user"] == "sarah"


async def test_slack_create_channel_sets_its_purpose(vendor: Vendor) -> None:
    vendor.on(
        "POST", "/conversations.create", {"ok": True, "channel": {"id": "C7", "name": "alpha"}}
    )
    vendor.on("POST", "/conversations.setPurpose", {"ok": True})
    vendor.on("POST", "/conversations.info", {"ok": True, "channel": {"id": "C7", "name": "alpha"}})
    args = {"name": "#alpha", "purpose": "Project Alpha"}
    result = await run("slack", "create_channel", args)
    assert vendor.form("POST", "/conversations.create") == {"name": "alpha"}
    assert vendor.form("POST", "/conversations.setPurpose") == {
        "channel": "C7",
        "purpose": "Project Alpha",
    }
    assert (await verify("slack", "create_channel", args, result)).status == "verified"


# --- triggers: each asks its vendor for new items and keeps only those after `since` -----------

SINCE = datetime(2026, 9, 25, 8, 0, tzinfo=UTC)
OLD = "2026-09-25T07:59:00Z"
NEW = "2026-09-25T08:05:00Z"


async def poll(provider_id: str, name: str, params: dict[str, Any] | None = None) -> list[Any]:
    provider = get_provider(provider_id)
    assert isinstance(provider, RestOAuthProvider)
    trigger = next(t for t in provider.build_triggers() if t.name == name)
    ctx = ctx_for(metadata={"workspace_gid": "w1"})
    return await trigger.poll(ctx, trigger.params_model.model_validate(params or {}), SINCE)


async def test_outlook_email_received_asks_graph_for_mail_after_since(vendor: Vendor) -> None:
    vendor.on(
        "GET",
        "/me/mailFolders/inbox/messages",
        {
            "value": [
                {
                    "id": "m1",
                    "subject": "Hi",
                    "receivedDateTime": NEW,
                    "from": {"emailAddress": {"address": "a@b.io"}},
                }
            ]
        },
    )
    events = await poll("outlook", "email_received", {"from_address": "a@b.io"})
    params = vendor.sent("GET", "/messages").url.params
    assert (
        params["$filter"]
        == "receivedDateTime gt 2026-09-25T08:00:00Z and from/emailAddress/address eq 'a@b.io'"
    )
    assert [(e.id, e.data["from_address"]) for e in events] == [("m1", "a@b.io")]


async def test_file_triggers_fire_per_version_and_skip_folders(vendor: Vendor) -> None:
    vendor.on(
        "GET",
        "/me/drive/root/children",
        {
            "value": [
                {
                    "id": "f1",
                    "name": "spec.md",
                    "file": {},
                    "eTag": "v2",
                    "lastModifiedDateTime": NEW,
                    "createdDateTime": OLD,
                },
                {"id": "f2", "name": "old.md", "file": {}, "lastModifiedDateTime": OLD},
                {"id": "d1", "name": "Folder", "folder": {}, "lastModifiedDateTime": NEW},
            ]
        },
    )
    events = await poll("onedrive", "file_changed")
    assert [(e.id, e.data["change"]) for e in events] == [("f1:v2", "updated")]

    vendor.on(
        "POST",
        "/files/list_folder",
        {
            "entries": [
                {".tag": "file", "id": "id:1", "rev": "r2", "name": "a.md", "server_modified": NEW},
                {".tag": "file", "id": "id:2", "rev": "r1", "name": "b.md", "server_modified": OLD},
                {".tag": "folder", "id": "id:3", "name": "sub"},
            ]
        },
    )
    events = await poll("dropbox", "file_changed", {"path": "/Projects"})
    assert vendor.json("POST", "/files/list_folder")["path"] == "/Projects"
    assert [e.id for e in events] == ["id:1:r2"]


async def test_teams_message_posted_ignores_system_messages(vendor: Vendor) -> None:
    vendor.on(
        "GET",
        "/teams/t/channels/c/messages",
        {
            "value": [
                {
                    "id": "1",
                    "messageType": "message",
                    "createdDateTime": NEW,
                    "body": {"content": "<p>Ship <b>it</b></p>"},
                },
                {"id": "2", "messageType": "systemEventMessage", "createdDateTime": NEW},
                {"id": "3", "messageType": "message", "createdDateTime": OLD},
            ]
        },
    )
    events = await poll("microsoft_teams", "message_posted", {"team_id": "t", "channel_id": "c"})
    assert [(e.id, e.data["text"]) for e in events] == [("1", "Ship it")]


async def test_task_triggers_fire_for_new_tasks_not_edited_ones(vendor: Vendor) -> None:
    vendor.on(
        "GET",
        "/tasks",
        lambda r: (
            {
                "data": [
                    {"gid": "9", "name": "New", "created_at": NEW},
                    {"gid": "8", "name": "Edited", "created_at": OLD},
                ]
            }
            if "app.asana.com" in str(r.url)
            else [
                {"id": "t1", "content": "New", "created_at": NEW},
                {"id": "t0", "content": "Old", "created_at": OLD},
            ]
        ),
    )
    asana = await poll("asana", "task_created", {"project_gid": "p1"})
    params = vendor.sent("GET", "/tasks").url.params
    assert params["project"] == "p1" and params["modified_since"].startswith("2026-09-25T08:00:00")
    assert [e.id for e in asana] == ["9"]
    todoist = await poll("todoist", "task_created")
    assert [e.id for e in todoist] == ["t1"]


async def test_zoom_meeting_ended_uses_the_scheduled_end(vendor: Vendor) -> None:
    now = datetime.now(UTC)
    ended = now - timedelta(minutes=5)
    vendor.on(
        "GET",
        "/users/me/meetings",
        {
            "meetings": [
                # Over: started 35 minutes ago, 30 minutes long.
                {
                    "id": 1,
                    "topic": "Client sync",
                    "start_time": (ended - timedelta(minutes=30)).isoformat(),
                    "duration": 30,
                },
                # Still going: its scheduled end is in the future.
                {
                    "id": 2,
                    "topic": "Long",
                    "start_time": (now - timedelta(minutes=10)).isoformat(),
                    "duration": 60,
                },
            ]
        },
    )
    provider = get_provider("zoom")
    assert isinstance(provider, RestOAuthProvider)
    trigger = next(t for t in provider.build_triggers() if t.name == "meeting_ended")
    events = await trigger.poll(ctx_for(), trigger.params_model(), now - timedelta(hours=1))
    assert vendor.sent("GET", "/users/me/meetings").url.params["type"] == "previous_meetings"
    assert [e.data["topic"] for e in events] == ["Client sync"]
