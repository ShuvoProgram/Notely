"""Minimal, request-capturing stand-ins for each vendor API + token endpoint."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field
from typing import Any

import httpx


@dataclass
class Captured:
    requests: list[httpx.Request] = field(default_factory=list)

    def find(self, method: str, path_part: str) -> httpx.Request | None:
        return next(
            (r for r in self.requests if r.method == method and path_part in str(r.url)), None
        )

    def body_json(self, method: str, path_part: str) -> Any:
        req = self.find(method, path_part)
        assert req is not None, f"no {method} {path_part} in {[str(r.url) for r in self.requests]}"
        return json.loads(req.content.decode() or "null")


def _json(status: int, body: Any) -> httpx.Response:
    return httpx.Response(status, json=body)


class VendorMock:
    """One handler serves both the token endpoint and the API for a provider id."""

    def __init__(self, provider: str) -> None:
        self.provider = provider
        self.captured = Captured()
        self.fail_auth = False

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.captured.requests.append(request)
        path = request.url.path
        host = request.url.host or ""
        if self.fail_auth and "token" not in path and "oauth" not in path:
            return _json(401, {"error": "invalid_token"})
        handler = getattr(self, f"_{self.provider}")
        response: httpx.Response | None = handler(request, host, path)
        return response if response is not None else _json(404, {"error": f"unmocked {path}"})

    # --- token endpoints ------------------------------------------------------------------------

    @staticmethod
    def _form(request: httpx.Request) -> dict[str, str]:
        return dict(httpx.QueryParams(request.content.decode()))

    # --- Slack ----------------------------------------------------------------------------------

    def _slack(self, r: httpx.Request, host: str, path: str) -> httpx.Response | None:
        if path == "/api/oauth.v2.access":
            form = self._form(r)
            assert form.get("client_id") == "test-id"
            return _json(
                200,
                {
                    "ok": True,
                    "authed_user": {
                        "id": "U1",
                        "access_token": "xoxp-user",
                        "scope": "search:read,channels:read,channels:history,users:read",
                    },
                    "team": {"id": "T1", "name": "Acme"},
                },
            )
        auth = r.headers.get("authorization")
        if auth != "Bearer xoxp-user":
            return _json(200, {"ok": False, "error": "invalid_auth"})
        if path == "/api/auth.test":
            return _json(
                200, {"ok": True, "user": "ada", "user_id": "U1", "team": "Acme", "team_id": "T1"}
            )
        if path == "/api/conversations.list":
            return _json(200, {"ok": True, "channels": [{"id": "C1", "name": "general"}]})
        if path == "/api/search.messages":
            q = self._form(r).get("query")
            return _json(
                200,
                {
                    "ok": True,
                    "messages": {
                        "matches": [
                            {
                                "iid": "m1",
                                "text": f"about {q}: pricing is final",
                                "channel": {"name": "launch"},
                                "permalink": "https://acme.slack.com/p1",
                            }
                        ]
                    },
                },
            )
        if path == "/api/conversations.history":
            return _json(
                200, {"ok": True, "messages": [{"ts": "1.0", "user": "U2", "text": "hello"}]}
            )
        if path == "/api/chat.postMessage":
            return _json(200, {"ok": True, "ts": "2.0", "channel": self._form(r).get("channel")})
        return None

    # --- Notion ---------------------------------------------------------------------------------

    def _notion(self, r: httpx.Request, host: str, path: str) -> httpx.Response | None:
        if path == "/v1/oauth/token":
            expected = "Basic " + base64.b64encode(b"test-id:test-secret").decode()
            assert r.headers.get("authorization") == expected, "Notion needs HTTP Basic client auth"
            body = json.loads(r.content)
            assert body.get("grant_type") == "authorization_code" and r.headers[
                "content-type"
            ].startswith("application/json")
            return _json(
                200,
                {
                    "access_token": "ntn-token",
                    "workspace_name": "Acme Wiki",
                    "bot_id": "b1",
                    "owner": {"user": {"name": "Ada"}},
                },
            )
        if r.headers.get("authorization") != "Bearer ntn-token":
            return _json(401, {"code": "unauthorized"})
        assert r.headers.get("notion-version") == "2022-06-28"
        if path == "/v1/users/me":
            return _json(
                200,
                {
                    "id": "bot-1",
                    "name": "Notely",
                    "bot": {"owner": {"user": {"name": "Ada"}}, "workspace_name": "Acme Wiki"},
                },
            )
        if path == "/v1/search":
            return _json(
                200,
                {
                    "results": [
                        {
                            "id": "p1",
                            "url": "https://notion.so/p1",
                            "last_edited_time": "2026-09-01T00:00:00Z",
                            "properties": {
                                "title": {"type": "title", "title": [{"plain_text": "Launch plan"}]}
                            },
                        }
                    ]
                },
            )
        if path == "/v1/pages/p1":
            return _json(
                200,
                {
                    "id": "p1",
                    "url": "https://notion.so/p1",
                    "properties": {
                        "Name": {"type": "title", "title": [{"plain_text": "Launch plan"}]}
                    },
                },
            )
        if path == "/v1/blocks/p1/children":
            return _json(
                200,
                {
                    "results": [
                        {
                            "type": "paragraph",
                            "paragraph": {"rich_text": [{"plain_text": "Ship Friday."}]},
                        }
                    ]
                },
            )
        if path == "/v1/pages" and r.method == "POST":
            return _json(200, {"id": "p2", "url": "https://notion.so/p2"})
        return None

    # --- Todoist --------------------------------------------------------------------------------

    def _todoist(self, r: httpx.Request, host: str, path: str) -> httpx.Response | None:
        if path == "/oauth/access_token":
            form = self._form(r)
            assert form.get("client_secret") == "test-secret"
            return _json(200, {"access_token": "td-token", "token_type": "Bearer"})
        if r.headers.get("authorization") != "Bearer td-token":
            return _json(401, {})
        if path == "/rest/v2/projects":
            return _json(200, [{"id": "pr1", "name": "Inbox", "is_inbox_project": True}])
        if path == "/rest/v2/tasks" and r.method == "GET":
            return _json(
                200,
                [
                    {
                        "id": "t1",
                        "content": "Finalize pricing",
                        "description": "",
                        "priority": 4,
                        "url": "https://todoist.com/t1",
                        "project_id": "pr1",
                        "created_at": "2026-09-01T00:00:00Z",
                    }
                ],
            )
        if path == "/rest/v2/tasks" and r.method == "POST":
            return _json(200, {"id": "t2", "url": "https://todoist.com/t2"})
        if path == "/rest/v2/tasks/t1/close":
            return httpx.Response(204)
        return None

    # --- Asana ----------------------------------------------------------------------------------

    def _asana(self, r: httpx.Request, host: str, path: str) -> httpx.Response | None:
        if path == "/-/oauth_token":
            form = self._form(r)
            assert form.get("code_verifier"), "Asana flow uses PKCE"
            return _json(
                200, {"access_token": "as-token", "refresh_token": "as-refresh", "expires_in": 3600}
            )
        if r.headers.get("authorization") != "Bearer as-token":
            return _json(401, {})
        if path == "/api/1.0/users/me":
            return _json(
                200,
                {
                    "data": {
                        "gid": "u1",
                        "name": "Ada",
                        "email": "ada@acme.io",
                        "workspaces": [{"gid": "w1", "name": "Acme"}],
                    }
                },
            )
        if path == "/api/1.0/workspaces":
            return _json(200, {"data": [{"gid": "w1", "name": "Acme"}]})
        if path == "/api/1.0/workspaces/w1/typeahead":
            return _json(
                200,
                {
                    "data": [
                        {
                            "gid": "t1",
                            "name": "Launch pricing page",
                            "permalink_url": "https://app.asana.com/t1",
                            "completed": False,
                        }
                    ]
                },
            )
        if path == "/api/1.0/tasks" and r.method == "GET":
            return _json(
                200,
                {
                    "data": [
                        {
                            "gid": "t1",
                            "name": "Launch pricing page",
                            "due_on": "2026-10-01",
                            "completed": False,
                            "permalink_url": "https://app.asana.com/t1",
                        }
                    ]
                },
            )
        if path == "/api/1.0/tasks" and r.method == "POST":
            return _json(201, {"data": {"gid": "t2", "permalink_url": "https://app.asana.com/t2"}})
        if path == "/api/1.0/tasks/t1" and r.method == "PUT":
            return _json(200, {"data": {"gid": "t1", "completed": True}})
        return None

    # --- Jira -----------------------------------------------------------------------------------

    def _jira(self, r: httpx.Request, host: str, path: str) -> httpx.Response | None:
        if host == "auth.atlassian.com" and path == "/oauth/token":
            body = json.loads(r.content)
            assert body.get("client_secret") == "test-secret" and body.get("grant_type") in (
                "authorization_code",
                "refresh_token",
            )
            return _json(
                200,
                {
                    "access_token": "jira-token",
                    "refresh_token": "jira-refresh",
                    "expires_in": 3600,
                    "scope": "read:jira-work read:jira-user offline_access",
                },
            )
        if r.headers.get("authorization") != "Bearer jira-token":
            return _json(401, {})
        if path == "/oauth/token/accessible-resources":
            return _json(
                200,
                [
                    {
                        "id": "cloud-1",
                        "name": "Acme",
                        "url": "https://acme.atlassian.net",
                        "scopes": ["read:jira-work"],
                    }
                ],
            )
        base = "/ex/jira/cloud-1/rest/api/3"
        if path == f"{base}/myself":
            return _json(200, {"accountId": "acc-1", "displayName": "Ada"})
        if path == f"{base}/project/search":
            return _json(200, {"total": 2, "values": [{"key": "PROJ"}, {"key": "OPS"}]})
        if path == f"{base}/search/jql":
            return _json(
                200,
                {
                    "issues": [
                        {
                            "key": "PROJ-482",
                            "fields": {
                                "summary": "Pricing page",
                                "status": {"name": "In Progress"},
                                "updated": "2026-09-01T00:00:00Z",
                            },
                        }
                    ]
                },
            )
        if path == f"{base}/issue/PROJ-482" and r.method == "GET":
            return _json(
                200,
                {
                    "key": "PROJ-482",
                    "fields": {
                        "summary": "Pricing page",
                        "status": {"name": "In Progress"},
                        "description": {
                            "type": "doc",
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [
                                        {"type": "text", "text": "Finalize the pricing page."}
                                    ],
                                }
                            ],
                        },
                        "comment": {"comments": []},
                    },
                },
            )
        if path == f"{base}/issue" and r.method == "POST":
            return _json(201, {"id": "10001", "key": "PROJ-500"})
        if path == f"{base}/issue/PROJ-482/comment" and r.method == "POST":
            return _json(201, {"id": "c1"})
        return None

    # --- Microsoft (Teams + Outlook) ------------------------------------------------------------

    def _microsoft(self, r: httpx.Request, host: str, path: str) -> httpx.Response | None:
        if host == "login.microsoftonline.com" and path.endswith("/oauth2/v2.0/token"):
            form = self._form(r)
            assert form.get("code_verifier"), "Microsoft flow uses PKCE"
            return _json(
                200,
                {
                    "access_token": "ms-token",
                    "refresh_token": "ms-refresh",
                    "expires_in": 3600,
                    "scope": form.get("scope", ""),
                },
            )
        if r.headers.get("authorization") != "Bearer ms-token":
            return _json(401, {"error": {"code": "InvalidAuthenticationToken"}})
        if path == "/v1.0/me":
            return _json(200, {"id": "ms-1", "displayName": "Ada Lovelace", "mail": "ada@acme.io"})
        if path == "/v1.0/me/joinedTeams":
            return _json(200, {"value": [{"id": "team-1", "displayName": "Product"}]})
        if path == "/v1.0/teams/team-1/channels":
            return _json(200, {"value": [{"id": "chan-1", "displayName": "General"}]})
        if path == "/v1.0/teams/team-1/channels/chan-1/messages" and r.method == "GET":
            return _json(
                200,
                {
                    "value": [
                        {
                            "id": "msg-1",
                            "createdDateTime": "2026-09-01T00:00:00Z",
                            "from": {"user": {"displayName": "Bob"}},
                            "body": {
                                "contentType": "html",
                                "content": "<p>Launch is <b>Friday</b></p>",
                            },
                        }
                    ]
                },
            )
        if path == "/v1.0/teams/team-1/channels/chan-1/messages" and r.method == "POST":
            return _json(201, {"id": "msg-2", "webUrl": "https://teams.microsoft.com/m2"})
        if path == "/v1.0/me/messages" and r.method == "GET":
            return _json(
                200,
                {
                    "value": [
                        {
                            "id": "mail-1",
                            "subject": "Q4 Launch Pricing",
                            "from": {"emailAddress": {"name": "Bob", "address": "bob@acme.io"}},
                            "receivedDateTime": "2026-09-01T00:00:00Z",
                            "bodyPreview": "Let's finalize pricing",
                            "webLink": "https://outlook.office.com/mail-1",
                        }
                    ]
                },
            )
        if path == "/v1.0/me/messages/mail-1":
            return _json(
                200,
                {
                    "id": "mail-1",
                    "subject": "Q4 Launch Pricing",
                    "from": {"emailAddress": {"address": "bob@acme.io"}},
                    "receivedDateTime": "2026-09-01T00:00:00Z",
                    "body": {
                        "contentType": "html",
                        "content": "<p>Let's <i>finalize</i> pricing</p>",
                    },
                    "webLink": "https://outlook.office.com/mail-1",
                },
            )
        if path == "/v1.0/me/messages" and r.method == "POST":
            return _json(201, {"id": "draft-1", "webLink": "https://outlook.office.com/draft-1"})
        if path == "/v1.0/me/sendMail":
            return httpx.Response(202)
        if path == "/v1.0/me/calendarView":
            return _json(
                200,
                {
                    "value": [
                        {
                            "id": "ev-1",
                            "subject": "Launch sync",
                            "start": {"dateTime": "2026-09-20T10:00:00"},
                            "end": {"dateTime": "2026-09-20T10:30:00"},
                            "attendees": [],
                            "webLink": "https://outlook.office.com/ev-1",
                        }
                    ]
                },
            )
        if path == "/v1.0/me/events" and r.method == "POST":
            return _json(201, {"id": "ev-2", "webLink": "https://outlook.office.com/ev-2"})
        return None

    _microsoft_teams = _microsoft
    _outlook = _microsoft

    # --- Dropbox --------------------------------------------------------------------------------

    def _dropbox(self, r: httpx.Request, host: str, path: str) -> httpx.Response | None:
        if path == "/oauth2/token":
            form = self._form(r)
            assert form.get("code_verifier"), "Dropbox flow uses PKCE"
            return _json(
                200,
                {
                    "access_token": "db-token",
                    "refresh_token": "db-refresh",
                    "expires_in": 14400,
                    "scope": "account_info.read files.metadata.read files.content.read",
                },
            )
        if r.headers.get("authorization") != "Bearer db-token":
            return _json(401, {"error_summary": "invalid_access_token"})
        if path == "/2/users/get_current_account":
            return _json(
                200,
                {"account_id": "dbid:1", "name": {"display_name": "Ada"}, "email": "ada@acme.io"},
            )
        if path == "/2/files/list_folder":
            return _json(
                200,
                {
                    "entries": [
                        {
                            ".tag": "file",
                            "name": "plan.md",
                            "path_display": "/plan.md",
                            "server_modified": "2026-09-01T00:00:00Z",
                        }
                    ]
                },
            )
        if path == "/2/files/search_v2":
            return _json(
                200,
                {
                    "matches": [
                        {
                            "metadata": {
                                "metadata": {
                                    ".tag": "file",
                                    "id": "id:1",
                                    "name": "plan.md",
                                    "path_lower": "/plan.md",
                                    "path_display": "/plan.md",
                                    "server_modified": "2026-09-01T00:00:00Z",
                                }
                            }
                        }
                    ]
                },
            )
        if host == "content.dropboxapi.com" and path == "/2/files/download":
            arg = json.loads(r.headers["dropbox-api-arg"])
            return httpx.Response(200, content=f"# Plan\nfor {arg['path']}".encode())
        if host == "content.dropboxapi.com" and path == "/2/files/upload":
            arg = json.loads(r.headers["dropbox-api-arg"])
            return _json(200, {"id": "id:2", "path_display": arg["path"], "size": len(r.content)})
        return None


def combined_transport(mocks: dict[str, VendorMock]) -> httpx.MockTransport:
    """Route token-endpoint traffic (which has no provider id) to the right vendor by host."""
    hosts = {
        "slack.com": "slack",
        "api.notion.com": "notion",
        "todoist.com": "todoist",
        "api.todoist.com": "todoist",
        "app.asana.com": "asana",
        "auth.atlassian.com": "jira",
        "api.atlassian.com": "jira",
        "login.microsoftonline.com": "microsoft",
        "graph.microsoft.com": "microsoft",
        "api.dropboxapi.com": "dropbox",
        "content.dropboxapi.com": "dropbox",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        vendor = hosts.get(request.url.host or "")
        if vendor == "microsoft":
            mock = mocks.get("microsoft_teams") or mocks.get("outlook")
        else:
            mock = mocks.get(vendor or "")
        if mock is None:
            return _json(404, {"error": f"no mock for {request.url.host}"})
        return mock.handle(request)

    return httpx.MockTransport(handler)
