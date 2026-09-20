"""Linear via its GraphQL API: search/read issues; create issues and comments with approval.

Connects with OAuth (Authorization: Bearer) or a personal API key (Authorization: <key>)."""

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
    TokenAuthSpec,
)
from app.integrations.base.rest import ProviderTool, RestOAuthProvider

API = "https://api.linear.app"

ISSUE_FIELDS = """
  id identifier title description url priority updatedAt
  state { name type } assignee { name } team { id key name }
"""


class SearchIssuesArgs(BaseModel):
    """Search issues by text in their title."""

    query: str = Field(min_length=1, max_length=200)
    limit: int = Field(default=10, ge=1, le=50)


class MyIssuesArgs(BaseModel):
    """List open issues assigned to you."""

    limit: int = Field(default=20, ge=1, le=50)


class ReadIssueArgs(BaseModel):
    """Read one issue by identifier (e.g. ENG-123) or id."""

    issue: str = Field(min_length=1, max_length=80)


class CreateIssueArgs(BaseModel):
    """Create an issue in a team."""

    team_key: str = Field(min_length=1, max_length=20, description="Team key, e.g. ENG")
    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=10_000)
    priority: int | None = Field(default=None, ge=0, le=4, description="0 none … 1 urgent … 4 low")


class AddCommentArgs(BaseModel):
    """Comment on an issue (visible to the whole team)."""

    issue: str = Field(min_length=1, max_length=80)
    body: str = Field(min_length=1, max_length=10_000)


class LinearProvider(RestOAuthProvider):
    settings_prefix = "linear"
    use_pkce = False
    api_base = API
    token_scheme = "raw"
    endpoints = OAuthEndpoints(
        authorize_url="https://linear.app/oauth/authorize",
        token_url="https://api.linear.app/oauth/token",
        scope_separator=",",
        extra_authorize_params={"prompt": "consent"},
    )
    manifest = ProviderManifest(
        id="linear",
        name="Linear",
        category="project_management",
        description="Search and read issues; create issues and comments with approval.",
        logo_url="https://cdn.simpleicons.org/linear",
        docs_url="https://developers.linear.app/docs/oauth/authentication",
        auth=AuthType.oauth2,
        capabilities=[Capability.search, Capability.read, Capability.create, Capability.comment],
        permissions=[
            PermissionSpec(
                scope="read", label="Read issues, teams and projects", capability=Capability.read
            ),
            PermissionSpec(
                scope="write",
                label="Create and update issues and comments",
                required=False,
                capability=Capability.create,
            ),
        ],
        mcp_server_url="https://mcp.linear.app/mcp",
        token_auth=TokenAuthSpec(
            label="Personal API key",
            help="Linear → Settings → Security & access → Personal API keys → Create key.",
            help_url="https://linear.app/settings/account/security",
            placeholder="lin_api_…",
        ),
    )

    async def _gql(
        self, ctx: ProviderContext, query: str, variables: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        async with self.http(ctx) as http:
            resp = await http.post("/graphql", json={"query": query, "variables": variables or {}})
        body = resp.json()
        errors = body.get("errors") or []
        if errors:
            message = str(errors[0].get("message", "GraphQL error"))
            code = str((errors[0].get("extensions") or {}).get("code", "")).lower()
            kind = ProviderErrorKind.invalid_request
            if "authentication" in code or "unauthorized" in message.lower():
                kind = ProviderErrorKind.expired
            elif "forbidden" in code or "permission" in message.lower():
                kind = ProviderErrorKind.permission_denied
            elif "not found" in message.lower():
                kind = ProviderErrorKind.not_found
            raise ProviderError(kind, message, provider="linear")
        data = body.get("data")
        return data if isinstance(data, dict) else {}

    async def identity(self, ctx: ProviderContext) -> ConnectionIdentity:
        data = await self._gql(ctx, "{ viewer { id name email organization { name } } }")
        viewer = data.get("viewer") or {}
        org = (viewer.get("organization") or {}).get("name")
        return ConnectionIdentity(
            external_account_id=str(viewer.get("id")),
            external_account_name=f"{viewer.get('name') or viewer.get('email')} @ {org}",
            metadata={"organization": org},
        )

    async def probe(self, ctx: ProviderContext) -> str:
        data = await self._gql(ctx, "{ teams { nodes { id key name } } }")
        teams = (data.get("teams") or {}).get("nodes") or []
        return f"{len(teams)} team(s)"

    async def _issue_lookup(self, ctx: ProviderContext, ref: str) -> dict[str, Any]:
        data = await self._gql(
            ctx, f"query($id: String!) {{ issue(id: $id) {{ {ISSUE_FIELDS} }} }}", {"id": ref}
        )
        issue = data.get("issue")
        if not issue:
            raise ProviderError(ProviderErrorKind.not_found, ref, provider="linear")
        return dict(issue)

    def _hit(self, i: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": i["id"],
            "kind": "issue",
            "title": f"{i.get('identifier')}: {i.get('title')}",
            "snippet": (
                f"{(i.get('state') or {}).get('name', '')} · "
                f"{(i.get('team') or {}).get('name', '')}"
            ),
            "url": i.get("url"),
            "updated_at": i.get("updatedAt"),
        }

    async def search(self, ctx: ProviderContext, query: str, limit: int) -> list[dict[str, Any]]:
        data = await self._gql(
            ctx,
            f"""query($q: String!, $n: Int!) {{
              issues(filter: {{ title: {{ containsIgnoreCase: $q }} }}, first: $n,
                     orderBy: updatedAt) {{ nodes {{ {ISSUE_FIELDS} }} }}
            }}""",
            {"q": query, "n": limit},
        )
        return [self._hit(i) for i in (data.get("issues") or {}).get("nodes") or []]

    def _issue_out(self, i: dict[str, Any]) -> dict[str, Any]:
        return {
            "issue_id": i["id"],
            "identifier": i.get("identifier"),
            "title": self.wrap(str(i.get("title", "")), ref=i["id"]),
            "state": (i.get("state") or {}).get("name"),
            "assignee": (i.get("assignee") or {}).get("name"),
            "team": (i.get("team") or {}).get("key"),
            "url": i.get("url"),
        }

    def build_tools(self) -> list[ProviderTool]:
        async def search_issues(ctx: ProviderContext, a: SearchIssuesArgs) -> dict[str, Any]:
            hits = await self.search(ctx, a.query, a.limit)
            return {
                "results": [
                    {
                        "issue_id": h["id"],
                        "title": self.wrap(h["title"], ref=h["id"]),
                        "url": h["url"],
                    }
                    for h in hits
                ],
                "sources": [
                    self.source(object_id=h["id"], title=h["title"], url=h["url"]) for h in hits
                ],
            }

        async def my_issues(ctx: ProviderContext, a: MyIssuesArgs) -> dict[str, Any]:
            data = await self._gql(
                ctx,
                f"""query($n: Int!) {{ viewer {{ assignedIssues(first: $n,
                     filter: {{ state: {{ type: {{ nin: ["completed", "canceled"] }} }} }}) {{
                     nodes {{ {ISSUE_FIELDS} }} }} }} }}""",
                {"n": a.limit},
            )
            issues = ((data.get("viewer") or {}).get("assignedIssues") or {}).get("nodes") or []
            return {
                "issues": [self._issue_out(i) for i in issues],
                "sources": [
                    self.source(object_id=i["id"], title=str(i.get("title")), url=i.get("url"))
                    for i in issues
                ],
            }

        async def read_issue(ctx: ProviderContext, a: ReadIssueArgs) -> dict[str, Any]:
            i = await self._issue_lookup(ctx, a.issue)
            return {
                **self._issue_out(i),
                "description": self.wrap(str(i.get("description") or ""), ref=i["id"]),
                "sources": [
                    self.source(object_id=i["id"], title=str(i.get("title")), url=i.get("url"))
                ],
            }

        async def create_issue(ctx: ProviderContext, a: CreateIssueArgs) -> dict[str, Any]:
            teams = await self._gql(
                ctx,
                "query($k: String!) { teams(filter: { key: { eq: $k } }) { nodes { id key } } }",
                {"k": a.team_key},
            )
            nodes = (teams.get("teams") or {}).get("nodes") or []
            if not nodes:
                raise ProviderError(
                    ProviderErrorKind.not_found, f"team {a.team_key}", provider="linear"
                )
            payload: dict[str, Any] = {"teamId": nodes[0]["id"], "title": a.title}
            if a.description:
                payload["description"] = a.description
            if a.priority is not None:
                payload["priority"] = a.priority
            data = await self._gql(
                ctx,
                "mutation($input: IssueCreateInput!) { issueCreate(input: $input) "
                f"{{ success issue {{ {ISSUE_FIELDS} }} }} }}",
                {"input": payload},
            )
            created = (data.get("issueCreate") or {}).get("issue") or {}
            return {
                "issue_id": created.get("id"),
                "identifier": created.get("identifier"),
                "url": created.get("url"),
                "title": a.title,
            }

        async def verify_issue(
            ctx: ProviderContext, a: CreateIssueArgs, result: dict[str, Any]
        ) -> Verification:
            i = await self._issue_lookup(ctx, str(result["issue_id"]))
            if i.get("title") != a.title:
                return Verification.failed("Issue exists but its title differs")
            return Verification.verified(f"Issue {i.get('identifier')} exists in Linear")

        async def add_comment(ctx: ProviderContext, a: AddCommentArgs) -> dict[str, Any]:
            issue = await self._issue_lookup(ctx, a.issue)
            data = await self._gql(
                ctx,
                "mutation($input: CommentCreateInput!) { commentCreate(input: $input) "
                "{ success comment { id url } } }",
                {"input": {"issueId": issue["id"], "body": a.body}},
            )
            comment = (data.get("commentCreate") or {}).get("comment") or {}
            return {
                "comment_id": comment.get("id"),
                "issue": issue.get("identifier"),
                "url": comment.get("url"),
            }

        async def verify_comment(
            ctx: ProviderContext, a: AddCommentArgs, result: dict[str, Any]
        ) -> Verification:
            data = await self._gql(
                ctx,
                "query($id: String!) { comment(id: $id) { id } }",
                {"id": str(result["comment_id"])},
            )
            if not data.get("comment"):
                return Verification.failed("Comment was not found")
            return Verification.verified(f"Comment is on {result.get('issue')}")

        return [
            ProviderTool(
                "search_issues",
                "Search Linear issues by title.",
                SearchIssuesArgs,
                Capability.search,
                search_issues,
                lambda a: f"Search Linear for “{a.query}”",
            ),
            ProviderTool(
                "my_issues",
                "List open issues assigned to you.",
                MyIssuesArgs,
                Capability.read,
                my_issues,
                lambda a: "List my Linear issues",
            ),
            ProviderTool(
                "read_issue",
                "Read one issue.",
                ReadIssueArgs,
                Capability.read,
                read_issue,
                lambda a: f"Read Linear issue {a.issue}",
            ),
            ProviderTool(
                "create_issue",
                "Create a Linear issue.",
                CreateIssueArgs,
                Capability.create,
                create_issue,
                lambda a: f"Create Linear issue “{a.title}” in {a.team_key}",
                verify=verify_issue,
            ),
            ProviderTool(
                "add_comment",
                "Comment on a Linear issue.",
                AddCommentArgs,
                Capability.comment,
                add_comment,
                lambda a: f"Comment on Linear issue {a.issue}",
                verify=verify_comment,
            ),
        ]
