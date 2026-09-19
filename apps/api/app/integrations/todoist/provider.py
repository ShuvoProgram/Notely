"""Todoist: OAuth2 (non-expiring tokens), REST API v2."""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, Field

from app.core.oauth import OAuthEndpoints
from app.integrations.base.capabilities import Capability
from app.integrations.base.provider import (
    AuthType,
    ConnectionIdentity,
    PermissionSpec,
    ProviderContext,
    ProviderManifest,
)
from app.integrations.base.rest import RestOAuthProvider


class ListTasksArgs(BaseModel):
    """List open tasks, optionally filtered with a Todoist filter string."""

    filter: str | None = Field(
        default=None, max_length=200, description="e.g. 'today', 'overdue', 'p1'"
    )
    limit: int = Field(default=25, ge=1, le=100)


class ListProjectsArgs(BaseModel):
    """List projects."""


class CreateTaskArgs(BaseModel):
    """Create a task."""

    content: str = Field(min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=5000)
    due_date: date | None = None
    priority: int = Field(default=1, ge=1, le=4, description="1 normal … 4 urgent")
    project_id: str | None = None


class CompleteTaskArgs(BaseModel):
    """Close (complete) a task."""

    task_id: str = Field(min_length=1, max_length=40)


class TodoistProvider(RestOAuthProvider):
    settings_prefix = "todoist"
    use_pkce = False
    api_base = "https://api.todoist.com/rest/v2"
    endpoints = OAuthEndpoints(
        authorize_url="https://todoist.com/oauth/authorize",
        token_url="https://todoist.com/oauth/access_token",
        scope_separator=",",
    )
    manifest = ProviderManifest(
        id="todoist",
        name="Todoist",
        category="tasks",
        description="Read your tasks and projects; create and complete tasks with approval.",
        logo_url="https://cdn.simpleicons.org/todoist",
        docs_url="https://developer.todoist.com/guides/#authorization",
        auth=AuthType.oauth2,
        capabilities=[Capability.read, Capability.create, Capability.update],
        permissions=[
            PermissionSpec(
                scope="data:read", label="Read tasks and projects", capability=Capability.read
            ),
            PermissionSpec(scope="task:add", label="Create tasks", capability=Capability.create),
            PermissionSpec(
                scope="data:read_write",
                label="Complete and update tasks",
                required=False,
                capability=Capability.update,
            ),
        ],
    )

    async def identity(self, ctx: ProviderContext) -> ConnectionIdentity:
        async with self.http(ctx) as http:
            projects = (await http.get("/projects")).json()
        inbox = next((p for p in projects if p.get("is_inbox_project")), None)
        return ConnectionIdentity(
            external_account_id=str(inbox.get("id")) if inbox else "todoist",
            external_account_name="Todoist account",
            metadata={"project_count": len(projects)},
        )

    async def probe(self, ctx: ProviderContext) -> str:
        async with self.http(ctx) as http:
            projects = (await http.get("/projects")).json()
        return f"{len(projects)} project(s)"

    async def search(self, ctx: ProviderContext, query: str, limit: int) -> list[dict[str, Any]]:
        async with self.http(ctx) as http:
            tasks = (await http.get("/tasks", params={"filter": f"search: {query}"})).json()
        return [
            {
                "id": t["id"],
                "kind": "task",
                "title": t.get("content", ""),
                "snippet": (t.get("description") or "")[:240],
                "url": t.get("url"),
                "updated_at": t.get("created_at"),
            }
            for t in tasks[:limit]
        ]

    def build_tools(self):  # type: ignore[no-untyped-def]
        async def list_tasks(ctx: ProviderContext, a: ListTasksArgs) -> dict[str, Any]:
            params = {"filter": a.filter} if a.filter else {}
            async with self.http(ctx) as http:
                tasks = (await http.get("/tasks", params=params)).json()
            return {
                "tasks": [
                    {
                        "id": t["id"],
                        "content": self.wrap(t.get("content", ""), ref=t["id"]),
                        "due": (t.get("due") or {}).get("date"),
                        "priority": t.get("priority"),
                        "project_id": t.get("project_id"),
                        "url": t.get("url"),
                    }
                    for t in tasks[: a.limit]
                ]
            }

        async def list_projects(ctx: ProviderContext, a: ListProjectsArgs) -> dict[str, Any]:
            async with self.http(ctx) as http:
                projects = (await http.get("/projects")).json()
            return {
                "projects": [
                    {"id": p["id"], "name": self.wrap(str(p.get("name", "")), ref=p["id"])}
                    for p in projects
                ]
            }

        async def create_task(ctx: ProviderContext, a: CreateTaskArgs) -> dict[str, Any]:
            payload: dict[str, Any] = {"content": a.content, "priority": a.priority}
            if a.description:
                payload["description"] = a.description
            if a.due_date:
                payload["due_date"] = a.due_date.isoformat()
            if a.project_id:
                payload["project_id"] = a.project_id
            async with self.http(ctx) as http:
                task = (await http.post("/tasks", json=payload)).json()
            return {"task_id": task.get("id"), "url": task.get("url"), "content": a.content}

        async def complete_task(ctx: ProviderContext, a: CompleteTaskArgs) -> dict[str, Any]:
            async with self.http(ctx) as http:
                await http.post(f"/tasks/{a.task_id}/close")
            return {"task_id": a.task_id, "completed": True}

        return [
            (
                "list_tasks",
                "List open Todoist tasks.",
                ListTasksArgs,
                Capability.read,
                list_tasks,
                lambda a: "List Todoist tasks",
            ),
            (
                "list_projects",
                "List Todoist projects.",
                ListProjectsArgs,
                Capability.read,
                list_projects,
                lambda a: "List Todoist projects",
            ),
            (
                "create_task",
                "Create a Todoist task.",
                CreateTaskArgs,
                Capability.create,
                create_task,
                lambda a: f"Create Todoist task “{a.content}”",
            ),
            (
                "complete_task",
                "Complete a Todoist task.",
                CompleteTaskArgs,
                Capability.update,
                complete_task,
                lambda a: f"Complete Todoist task {a.task_id}",
            ),
        ]
