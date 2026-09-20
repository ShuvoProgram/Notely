"""Jira Cloud: Atlassian 3LO OAuth (JSON token endpoint, rotating refresh tokens), REST API v3
via the api.atlassian.com gateway. The connection stores the selected `cloud_id`."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.ai.tools.base import Verification
from app.core.oauth import OAuthEndpoints
from app.integrations.base.capabilities import Capability
from app.integrations.base.errors import ProviderError, ProviderErrorKind
from app.integrations.base.provider import (
    AuthType,
    ConnectionIdentity,
    PermissionSpec,
    ProviderContext,
    ProviderManifest,
)
from app.integrations.base.rest import ProviderTool, RestOAuthProvider

GATEWAY = "https://api.atlassian.com"


def _adf(text: str) -> dict[str, Any]:
    """Plain text → Atlassian Document Format (paragraphs)."""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()] or [""]
    return {
        "type": "doc",
        "version": 1,
        "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": p}] if p else []}
            for p in paragraphs
        ],
    }


def _adf_text(node: Any) -> str:
    if isinstance(node, dict):
        if node.get("type") == "text":
            return str(node.get("text", ""))
        inner = " ".join(_adf_text(c) for c in node.get("content", []) or [])
        return inner + ("\n" if node.get("type") == "paragraph" else "")
    if isinstance(node, list):
        return " ".join(_adf_text(c) for c in node)
    return str(node or "")


class SearchIssuesArgs(BaseModel):
    """Search issues with JQL (e.g. 'project = PROJ AND status != Done')."""

    jql: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=10, ge=1, le=50)


class ReadIssueArgs(BaseModel):
    """Read an issue by key (e.g. PROJ-482)."""

    issue_key: str = Field(min_length=3, max_length=40)


class CreateIssueArgs(BaseModel):
    """Create an issue in a project."""

    project_key: str = Field(min_length=1, max_length=20)
    summary: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=10_000)
    issue_type: str = Field(default="Task", max_length=40)


class AddCommentArgs(BaseModel):
    """Add a comment to an issue (visible to everyone on the issue)."""

    issue_key: str = Field(min_length=3, max_length=40)
    body: str = Field(min_length=1, max_length=10_000)


class JiraProvider(RestOAuthProvider):
    settings_prefix = "jira"
    use_pkce = False
    endpoints = OAuthEndpoints(
        authorize_url="https://auth.atlassian.com/authorize",
        token_url="https://auth.atlassian.com/oauth/token",
        token_format="json",
        extra_authorize_params={"audience": "api.atlassian.com", "prompt": "consent"},
    )
    manifest = ProviderManifest(
        id="jira",
        name="Jira",
        category="project_management",
        description="Search and read issues; create issues and comments with approval.",
        logo_url="https://cdn.simpleicons.org/jira",
        docs_url="https://developer.atlassian.com/cloud/jira/platform/oauth-2-3lo-apps/",
        mcp_server_url="https://mcp.atlassian.com/v1/mcp",
        auth=AuthType.oauth2,
        capabilities=[Capability.search, Capability.read, Capability.create, Capability.comment],
        permissions=[
            PermissionSpec(
                scope="read:jira-work", label="Read issues and projects", capability=Capability.read
            ),
            PermissionSpec(
                scope="read:jira-user", label="Read your user profile", capability=Capability.read
            ),
            PermissionSpec(scope="offline_access", label="Stay connected (refresh tokens)"),
            PermissionSpec(
                scope="write:jira-work",
                label="Create issues and comments",
                required=False,
                capability=Capability.create,
            ),
        ],
    )

    def _base(self, ctx: ProviderContext) -> str:
        cloud_id = ctx.connection.metadata_.get("cloud_id")
        if not cloud_id:
            raise ProviderError(
                ProviderErrorKind.misconfigured, "no Jira site selected", provider="jira"
            )
        return f"{GATEWAY}/ex/jira/{cloud_id}/rest/api/3"

    async def identity(self, ctx: ProviderContext) -> ConnectionIdentity:
        async with self.http(ctx, GATEWAY) as http:
            sites = (await http.get("/oauth/token/accessible-resources")).json()
        jira_sites = [s for s in sites if "jira" in " ".join(s.get("scopes", [])) or s.get("url")]
        if not jira_sites:
            raise ProviderError(
                ProviderErrorKind.permission_denied, "no accessible Jira sites", provider="jira"
            )
        site = jira_sites[0]
        ctx.connection.metadata_ = {
            **ctx.connection.metadata_,
            "cloud_id": site["id"],
            "site_url": site.get("url"),
        }
        async with self.http(ctx, f"{GATEWAY}/ex/jira/{site['id']}/rest/api/3") as http:
            me = (await http.get("/myself")).json()
        return ConnectionIdentity(
            external_account_id=str(me.get("accountId")),
            external_account_name=(
                f"{me.get('displayName') or me.get('emailAddress')} @ "
                f"{site.get('name') or site.get('url')}"
            ),
            metadata={
                "cloud_id": site["id"],
                "site_url": site.get("url"),
                "site_name": site.get("name"),
            },
        )

    async def probe(self, ctx: ProviderContext) -> str:
        async with self.http(ctx, self._base(ctx)) as http:
            projects = (await http.get("/project/search", params={"maxResults": 5})).json()
        return f"{projects.get('total', len(projects.get('values', [])))} project(s)"

    async def search(self, ctx: ProviderContext, query: str, limit: int) -> list[dict[str, Any]]:
        safe = query.replace('"', "")
        return await self._jql(ctx, f'text ~ "{safe}" ORDER BY updated DESC', limit)

    async def _jql(self, ctx: ProviderContext, jql: str, limit: int) -> list[dict[str, Any]]:
        site = ctx.connection.metadata_.get("site_url", "")
        async with self.http(ctx, self._base(ctx)) as http:
            body = (
                await http.post(
                    "/search/jql",
                    json={
                        "jql": jql,
                        "maxResults": limit,
                        "fields": ["summary", "status", "updated", "assignee"],
                    },
                )
            ).json()
        return [
            {
                "id": i["key"],
                "kind": "issue",
                "title": f"{i['key']}: {i['fields'].get('summary', '')}",
                "snippet": ((i["fields"].get("status") or {}).get("name") or ""),
                "url": f"{site}/browse/{i['key']}" if site else None,
                "updated_at": i["fields"].get("updated"),
            }
            for i in body.get("issues", [])
        ]

    def build_tools(self):  # type: ignore[no-untyped-def]
        async def search_issues(ctx: ProviderContext, a: SearchIssuesArgs) -> dict[str, Any]:
            hits = await self._jql(ctx, a.jql, a.limit)
            return {
                "results": hits,
                "sources": [
                    self.source(object_id=h["id"], title=h["title"], url=h["url"]) for h in hits
                ],
            }

        async def read_issue(ctx: ProviderContext, a: ReadIssueArgs) -> dict[str, Any]:
            async with self.http(ctx, self._base(ctx)) as http:
                issue = (
                    await http.get(
                        f"/issue/{a.issue_key}",
                        params={"fields": "summary,description,status,assignee,comment"},
                    )
                ).json()
            f = issue.get("fields", {})
            site = ctx.connection.metadata_.get("site_url", "")
            comments = [
                (_adf_text(c.get("body")) or "").strip()
                for c in (f.get("comment") or {}).get("comments", [])[-5:]
            ]
            return {
                "key": issue.get("key"),
                "summary": f.get("summary"),
                "status": (f.get("status") or {}).get("name"),
                "assignee": (f.get("assignee") or {}).get("displayName"),
                "description": self.wrap(
                    _adf_text(f.get("description")).strip()[:12_000], ref=a.issue_key
                ),
                "recent_comments": [self.wrap(c, ref=a.issue_key) for c in comments if c],
                "sources": [
                    self.source(
                        object_id=a.issue_key,
                        title=f"{a.issue_key}: {f.get('summary', '')}",
                        url=f"{site}/browse/{a.issue_key}" if site else None,
                    )
                ],
            }

        async def create_issue(ctx: ProviderContext, a: CreateIssueArgs) -> dict[str, Any]:
            fields: dict[str, Any] = {
                "project": {"key": a.project_key},
                "summary": a.summary,
                "issuetype": {"name": a.issue_type},
            }
            if a.description:
                fields["description"] = _adf(a.description)
            async with self.http(ctx, self._base(ctx)) as http:
                created = (await http.post("/issue", json={"fields": fields})).json()
            site = ctx.connection.metadata_.get("site_url", "")
            return {
                "key": created.get("key"),
                "url": f"{site}/browse/{created.get('key')}" if site else None,
            }

        async def add_comment(ctx: ProviderContext, a: AddCommentArgs) -> dict[str, Any]:
            async with self.http(ctx, self._base(ctx)) as http:
                comment = (
                    await http.post(f"/issue/{a.issue_key}/comment", json={"body": _adf(a.body)})
                ).json()
            return {"comment_id": comment.get("id"), "issue_key": a.issue_key}

        async def verify_create_issue(
            ctx: ProviderContext, a: CreateIssueArgs, result: dict[str, Any]
        ) -> Verification:
            async with self.http(ctx, self._base(ctx)) as http:
                issue = (
                    await http.get(f"/issue/{result['key']}", params={"fields": "summary"})
                ).json()
            summary = (issue.get("fields") or {}).get("summary")
            if summary not in (None, a.summary):
                return Verification.failed("Issue exists but its summary differs")
            return Verification.verified(f"Issue {issue.get('key', result['key'])} exists in Jira")

        async def verify_add_comment(
            ctx: ProviderContext, a: AddCommentArgs, result: dict[str, Any]
        ) -> Verification:
            async with self.http(ctx, self._base(ctx)) as http:
                comment = (
                    await http.get(f"/issue/{a.issue_key}/comment/{result['comment_id']}")
                ).json()
            if str(comment.get("id")) != str(result["comment_id"]):
                return Verification.failed("Comment was not found on the issue")
            return Verification.verified(f"Comment is on {a.issue_key}")

        return [
            ProviderTool(
                "search_issues",
                "Search Jira issues with JQL.",
                SearchIssuesArgs,
                Capability.search,
                search_issues,
                lambda a: f"Search Jira: {a.jql[:60]}",
            ),
            ProviderTool(
                "read_issue",
                "Read a Jira issue.",
                ReadIssueArgs,
                Capability.read,
                read_issue,
                lambda a: f"Read Jira issue {a.issue_key}",
            ),
            ProviderTool(
                "create_issue",
                "Create a Jira issue.",
                CreateIssueArgs,
                Capability.create,
                create_issue,
                lambda a: f"Create Jira issue in {a.project_key}: “{a.summary}”",
                verify=verify_create_issue,
            ),
            ProviderTool(
                "add_comment",
                "Comment on a Jira issue (visible to others).",
                AddCommentArgs,
                Capability.comment,
                add_comment,
                lambda a: f"Comment on Jira issue {a.issue_key}",
                verify=verify_add_comment,
            ),
        ]
