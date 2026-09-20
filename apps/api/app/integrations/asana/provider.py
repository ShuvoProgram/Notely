"""Asana: OAuth2 with PKCE and refresh tokens, REST API 1.0."""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, Field

from app.ai.tools.base import Verification
from app.core.oauth import OAuthEndpoints
from app.integrations.base.capabilities import Capability
from app.integrations.base.provider import (
    AuthType,
    ConnectionIdentity,
    OAuthSetupGuide,
    PermissionSpec,
    ProviderContext,
    ProviderManifest,
)
from app.integrations.base.rest import ProviderTool, RestOAuthProvider


class MyTasksArgs(BaseModel):
    """List tasks assigned to you in a workspace (defaults to your first workspace)."""

    workspace_gid: str | None = None
    limit: int = Field(default=25, ge=1, le=100)
    include_completed: bool = False


class SearchTasksArgs(BaseModel):
    """Search tasks by text in a workspace."""

    query: str = Field(min_length=1, max_length=200)
    workspace_gid: str | None = None
    limit: int = Field(default=10, ge=1, le=25)


class CreateTaskArgs(BaseModel):
    """Create a task assigned to you."""

    name: str = Field(min_length=1, max_length=500)
    notes: str | None = Field(default=None, max_length=5000)
    due_on: date | None = None
    workspace_gid: str | None = None
    project_gid: str | None = None


class CompleteTaskArgs(BaseModel):
    """Mark a task complete."""

    task_gid: str = Field(min_length=1, max_length=40)


class AsanaProvider(RestOAuthProvider):
    settings_prefix = "asana"
    api_base = "https://app.asana.com/api/1.0"
    endpoints = OAuthEndpoints(
        authorize_url="https://app.asana.com/-/oauth_authorize",
        token_url="https://app.asana.com/-/oauth_token",
    )
    manifest = ProviderManifest(
        id="asana",
        name="Asana",
        category="project_management",
        description="See and search your tasks; create and complete tasks with approval.",
        logo_url="https://cdn.simpleicons.org/asana",
        docs_url="https://developers.asana.com/docs/oauth",
        auth=AuthType.oauth2,
        oauth_setup=OAuthSetupGuide(
            console_url="https://app.asana.com/0/my-apps",
            console_label="Open Asana's developer apps",
            steps=[
                "Create new app → OAuth → add the redirect URI shown here.",
                "Copy the Client ID and Client secret from the app's OAuth page.",
            ],
        ),
        capabilities=[Capability.search, Capability.read, Capability.create, Capability.update],
        permissions=[
            PermissionSpec(
                scope="default",
                label="Access your Asana workspaces and tasks",
                capability=Capability.read,
            )
        ],
    )

    async def _workspace(self, ctx: ProviderContext, explicit: str | None) -> str:
        if explicit:
            return explicit
        cached = ctx.connection.metadata_.get("workspace_gid")
        if cached:
            return str(cached)
        async with self.http(ctx) as http:
            me = (await http.get("/users/me", params={"opt_fields": "workspaces.gid"})).json()[
                "data"
            ]
        workspaces = me.get("workspaces") or []
        if not workspaces:
            from app.integrations.base.errors import ProviderError, ProviderErrorKind

            raise ProviderError(ProviderErrorKind.not_found, "no workspaces", provider="asana")
        return str(workspaces[0]["gid"])

    async def identity(self, ctx: ProviderContext) -> ConnectionIdentity:
        async with self.http(ctx) as http:
            me = (
                await http.get(
                    "/users/me", params={"opt_fields": "name,email,workspaces.gid,workspaces.name"}
                )
            ).json()["data"]
        workspaces = me.get("workspaces") or []
        first = workspaces[0] if workspaces else {}
        return ConnectionIdentity(
            external_account_id=str(me.get("gid")),
            external_account_name=(
                f"{me.get('name') or me.get('email')} @ {first.get('name', 'Asana')}"
            ),
            metadata={
                "workspace_gid": first.get("gid"),
                "workspaces": [{"gid": w.get("gid"), "name": w.get("name")} for w in workspaces],
            },
        )

    async def probe(self, ctx: ProviderContext) -> str:
        async with self.http(ctx) as http:
            data = (await http.get("/workspaces", params={"limit": 5})).json()["data"]
        return f"{len(data)} workspace(s)"

    async def search(self, ctx: ProviderContext, query: str, limit: int) -> list[dict[str, Any]]:
        ws = await self._workspace(ctx, None)
        async with self.http(ctx) as http:
            data = (
                await http.get(
                    f"/workspaces/{ws}/typeahead",
                    params={
                        "resource_type": "task",
                        "query": query,
                        "count": limit,
                        "opt_fields": "name,permalink_url,completed,modified_at",
                    },
                )
            ).json()["data"]
        return [
            {
                "id": t["gid"],
                "kind": "task",
                "title": t.get("name", ""),
                "snippet": "completed" if t.get("completed") else "",
                "url": t.get("permalink_url"),
                "updated_at": t.get("modified_at"),
            }
            for t in data
        ]

    def build_tools(self):  # type: ignore[no-untyped-def]
        fields = "name,notes,due_on,completed,permalink_url,projects.name"

        async def my_tasks(ctx: ProviderContext, a: MyTasksArgs) -> dict[str, Any]:
            ws = await self._workspace(ctx, a.workspace_gid)
            params: dict[str, Any] = {
                "assignee": "me",
                "workspace": ws,
                "limit": a.limit,
                "opt_fields": fields,
            }
            if not a.include_completed:
                params["completed_since"] = "now"
            async with self.http(ctx) as http:
                data = (await http.get("/tasks", params=params)).json()["data"]
            return {
                "tasks": [
                    {
                        "gid": t["gid"],
                        "name": self.wrap(t.get("name", ""), ref=t["gid"]),
                        "due_on": t.get("due_on"),
                        "completed": t.get("completed"),
                        "url": t.get("permalink_url"),
                    }
                    for t in data
                ]
            }

        async def search_tasks(ctx: ProviderContext, a: SearchTasksArgs) -> dict[str, Any]:
            hits = await self.search(ctx, a.query, a.limit)
            return {
                "results": hits,
                "sources": [
                    self.source(object_id=h["id"], title=h["title"], url=h["url"]) for h in hits
                ],
            }

        async def create_task(ctx: ProviderContext, a: CreateTaskArgs) -> dict[str, Any]:
            ws = await self._workspace(ctx, a.workspace_gid)
            data: dict[str, Any] = {"name": a.name, "assignee": "me", "workspace": ws}
            if a.notes:
                data["notes"] = a.notes
            if a.due_on:
                data["due_on"] = a.due_on.isoformat()
            if a.project_gid:
                data["projects"] = [a.project_gid]
            async with self.http(ctx) as http:
                task = (await http.post("/tasks", json={"data": data})).json()["data"]
            return {"task_gid": task.get("gid"), "url": task.get("permalink_url"), "name": a.name}

        async def complete_task(ctx: ProviderContext, a: CompleteTaskArgs) -> dict[str, Any]:
            async with self.http(ctx) as http:
                task = (
                    await http.request(
                        "PUT", f"/tasks/{a.task_gid}", json={"data": {"completed": True}}
                    )
                ).json()["data"]
            return {"task_gid": a.task_gid, "completed": bool(task.get("completed", True))}

        async def verify_create_task(
            ctx: ProviderContext, a: CreateTaskArgs, result: dict[str, Any]
        ) -> Verification:
            async with self.http(ctx) as http:
                task = (await http.get(f"/tasks/{result['task_gid']}")).json()["data"]
            if task.get("name") not in (None, a.name):
                return Verification.failed("Task exists but its name differs")
            return Verification.verified("Task is in Asana")

        async def verify_complete_task(
            ctx: ProviderContext, a: CompleteTaskArgs, result: dict[str, Any]
        ) -> Verification:
            async with self.http(ctx) as http:
                task = (await http.get(f"/tasks/{a.task_gid}")).json()["data"]
            if not task.get("completed"):
                return Verification.failed("Task is still open in Asana")
            return Verification.verified("Task is completed in Asana")

        return [
            ProviderTool(
                "my_tasks",
                "List tasks assigned to you.",
                MyTasksArgs,
                Capability.read,
                my_tasks,
                lambda a: "List my Asana tasks",
            ),
            ProviderTool(
                "search_tasks",
                "Search Asana tasks.",
                SearchTasksArgs,
                Capability.search,
                search_tasks,
                lambda a: f"Search Asana for “{a.query}”",
            ),
            ProviderTool(
                "create_task",
                "Create an Asana task assigned to you.",
                CreateTaskArgs,
                Capability.create,
                create_task,
                lambda a: f"Create Asana task “{a.name}”",
                verify=verify_create_task,
            ),
            ProviderTool(
                "complete_task",
                "Complete an Asana task.",
                CompleteTaskArgs,
                Capability.update,
                complete_task,
                lambda a: f"Complete Asana task {a.task_gid}",
                verify=verify_complete_task,
            ),
        ]
