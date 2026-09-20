"""ClickUp: list/read tasks; create and update tasks with approval.

ClickUp sends both OAuth tokens and personal tokens as a bare `Authorization: <token>`."""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Any

from pydantic import BaseModel, Field

from app.ai.tools.base import Verification
from app.core.oauth import OAuthEndpoints
from app.integrations.base.capabilities import Capability
from app.integrations.base.errors import ProviderError, ProviderErrorKind
from app.integrations.base.http import ProviderHttpClient
from app.integrations.base.provider import (
    AuthType,
    ConnectionIdentity,
    PermissionSpec,
    ProviderContext,
    ProviderManifest,
    TokenAuthSpec,
)
from app.integrations.base.rest import ProviderTool, RestOAuthProvider

API = "https://api.clickup.com/api/v2"


class ListTasksArgs(BaseModel):
    """List open tasks in your workspace, optionally filtered by text."""

    query: str | None = Field(default=None, max_length=200)
    limit: int = Field(default=20, ge=1, le=50)


class ReadTaskArgs(BaseModel):
    """Read one task by id."""

    task_id: str = Field(min_length=1, max_length=40)


class CreateTaskArgs(BaseModel):
    """Create a task in a list (list ids come from list_lists)."""

    list_id: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=10_000)
    due_date: date | None = None
    priority: int | None = Field(default=None, ge=1, le=4, description="1 urgent … 4 low")


class ListListsArgs(BaseModel):
    """List spaces, folders and lists (needed to create tasks)."""


class UpdateTaskArgs(BaseModel):
    """Rename, describe or close a task."""

    task_id: str = Field(min_length=1, max_length=40)
    name: str | None = Field(default=None, max_length=300)
    description: str | None = Field(default=None, max_length=10_000)
    status: str | None = Field(default=None, max_length=60, description="e.g. 'complete'")


class ClickUpProvider(RestOAuthProvider):
    settings_prefix = "clickup"
    use_pkce = False
    api_base = API
    endpoints = OAuthEndpoints(
        authorize_url="https://app.clickup.com/api",
        token_url="https://api.clickup.com/api/v2/oauth/token",
    )
    manifest = ProviderManifest(
        id="clickup",
        name="ClickUp",
        category="project_management",
        description="Read your tasks and lists; create and update tasks with approval.",
        logo_url="https://cdn.simpleicons.org/clickup",
        docs_url="https://developer.clickup.com/docs/authentication",
        auth=AuthType.oauth2,
        capabilities=[Capability.read, Capability.create, Capability.update],
        permissions=[
            PermissionSpec(
                scope="all",
                label="Access tasks and lists in your workspaces",
                capability=Capability.read,
            ),
        ],
        token_auth=TokenAuthSpec(
            label="Personal API token",
            help="ClickUp → your avatar → Settings → Apps → API Token → Generate.",
            help_url="https://app.clickup.com/settings/apps",
            placeholder="pk_…",
        ),
    )

    def http(self, ctx: ProviderContext, base_url: str | None = None) -> ProviderHttpClient:
        token = ctx.credentials.access_token
        if not token:
            raise ProviderError(ProviderErrorKind.expired, "no access token", provider="clickup")
        # Both OAuth and personal tokens are sent bare.
        return ProviderHttpClient(
            provider="clickup", base_url=base_url or self.api_base, headers={"Authorization": token}
        )

    async def identity(self, ctx: ProviderContext) -> ConnectionIdentity:
        async with self.http(ctx) as http:
            user = (await http.get("/user")).json().get("user") or {}
            teams = (await http.get("/team")).json().get("teams") or []
        if not teams:
            raise ProviderError(
                ProviderErrorKind.permission_denied, "no workspaces", provider="clickup"
            )
        return ConnectionIdentity(
            external_account_id=str(user.get("id")),
            external_account_name=(
                f"{user.get('username') or user.get('email')} @ {teams[0].get('name')}"
            ),
            metadata={"team_id": str(teams[0]["id"]), "team_name": teams[0].get("name")},
        )

    def _team(self, ctx: ProviderContext) -> str:
        team = ctx.connection.metadata_.get("team_id")
        if not team:
            raise ProviderError(ProviderErrorKind.misconfigured, "no workspace", provider="clickup")
        return str(team)

    async def probe(self, ctx: ProviderContext) -> str:
        async with self.http(ctx) as http:
            spaces = (await http.get(f"/team/{self._team(ctx)}/space")).json().get("spaces") or []
        return f"{len(spaces)} space(s)"

    async def _tasks(
        self, ctx: ProviderContext, query: str | None, limit: int
    ) -> list[dict[str, Any]]:
        async with self.http(ctx) as http:
            body = (
                await http.get(
                    f"/team/{self._team(ctx)}/task",
                    params={
                        "page": 0,
                        "subtasks": "true",
                        "include_closed": "false",
                        "order_by": "updated",
                    },
                )
            ).json()
        tasks = body.get("tasks") or []
        if query:
            q = query.lower()
            tasks = [
                t
                for t in tasks
                if q in str(t.get("name", "")).lower()
                or q in str(t.get("description") or "").lower()
            ]
        return tasks[:limit]

    def _hit(self, t: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": t["id"],
            "kind": "task",
            "title": str(t.get("name", "")),
            "snippet": (
                f"{(t.get('status') or {}).get('status', '')} · "
                f"{(t.get('list') or {}).get('name', '')}"
            ),
            "url": t.get("url"),
            "updated_at": None,
        }

    async def search(self, ctx: ProviderContext, query: str, limit: int) -> list[dict[str, Any]]:
        return [self._hit(t) for t in await self._tasks(ctx, query, limit)]

    def _task_out(self, t: dict[str, Any]) -> dict[str, Any]:
        return {
            "task_id": t["id"],
            "name": self.wrap(str(t.get("name", "")), ref=t["id"]),
            "status": (t.get("status") or {}).get("status"),
            "list": (t.get("list") or {}).get("name"),
            "due_date": t.get("due_date"),
            "url": t.get("url"),
        }

    def build_tools(self) -> list[ProviderTool]:
        async def list_tasks(ctx: ProviderContext, a: ListTasksArgs) -> dict[str, Any]:
            tasks = await self._tasks(ctx, a.query, a.limit)
            return {
                "tasks": [self._task_out(t) for t in tasks],
                "sources": [
                    self.source(object_id=t["id"], title=str(t.get("name")), url=t.get("url"))
                    for t in tasks
                ],
            }

        async def list_lists(ctx: ProviderContext, a: ListListsArgs) -> dict[str, Any]:
            out = []
            async with self.http(ctx) as http:
                spaces = (await http.get(f"/team/{self._team(ctx)}/space")).json().get(
                    "spaces"
                ) or []
                for space in spaces[:10]:
                    lists = (await http.get(f"/space/{space['id']}/list")).json().get("lists") or []
                    folders = (await http.get(f"/space/{space['id']}/folder")).json().get(
                        "folders"
                    ) or []
                    for folder in folders:
                        lists.extend(folder.get("lists") or [])
                    out.append(
                        {
                            "space": self.wrap(str(space.get("name", "")), ref=space["id"]),
                            "lists": [
                                {
                                    "list_id": lst["id"],
                                    "name": self.wrap(str(lst.get("name", "")), ref=lst["id"]),
                                }
                                for lst in lists
                            ],
                        }
                    )
            return {"spaces": out}

        async def read_task(ctx: ProviderContext, a: ReadTaskArgs) -> dict[str, Any]:
            async with self.http(ctx) as http:
                t = (await http.get(f"/task/{a.task_id}")).json()
            return {
                **self._task_out(t),
                "description": self.wrap(str(t.get("description") or ""), ref=t["id"]),
                "sources": [
                    self.source(object_id=t["id"], title=str(t.get("name")), url=t.get("url"))
                ],
            }

        async def create_task(ctx: ProviderContext, a: CreateTaskArgs) -> dict[str, Any]:
            payload: dict[str, Any] = {"name": a.name}
            if a.description:
                payload["description"] = a.description
            if a.due_date:
                payload["due_date"] = int(datetime.combine(a.due_date, time(12)).timestamp() * 1000)
            if a.priority:
                payload["priority"] = a.priority
            async with self.http(ctx) as http:
                t = (await http.post(f"/list/{a.list_id}/task", json=payload)).json()
            return {"task_id": t.get("id"), "url": t.get("url"), "name": a.name}

        async def verify_create(
            ctx: ProviderContext, a: CreateTaskArgs, result: dict[str, Any]
        ) -> Verification:
            async with self.http(ctx) as http:
                t = (await http.get(f"/task/{result['task_id']}")).json()
            if t.get("name") != a.name:
                return Verification.failed("Task exists but its name differs")
            return Verification.verified("Task is in ClickUp")

        async def update_task(ctx: ProviderContext, a: UpdateTaskArgs) -> dict[str, Any]:
            payload = {
                k: v
                for k, v in {
                    "name": a.name,
                    "description": a.description,
                    "status": a.status,
                }.items()
                if v
            }
            async with self.http(ctx) as http:
                t = (await http.request("PUT", f"/task/{a.task_id}", json=payload)).json()
            return {
                "task_id": a.task_id,
                "status": (t.get("status") or {}).get("status"),
                "name": t.get("name"),
            }

        async def verify_update(
            ctx: ProviderContext, a: UpdateTaskArgs, result: dict[str, Any]
        ) -> Verification:
            async with self.http(ctx) as http:
                t = (await http.get(f"/task/{a.task_id}")).json()
            if (
                a.status
                and str((t.get("status") or {}).get("status", "")).lower() != a.status.lower()
            ):
                return Verification.failed("Task status did not change")
            if a.name and t.get("name") != a.name:
                return Verification.failed("Task name did not change")
            return Verification.verified("Task is updated in ClickUp")

        return [
            ProviderTool(
                "list_tasks",
                "List open ClickUp tasks (optionally filtered).",
                ListTasksArgs,
                Capability.read,
                list_tasks,
                lambda a: "List ClickUp tasks",
            ),
            ProviderTool(
                "list_lists",
                "List spaces and lists.",
                ListListsArgs,
                Capability.read,
                list_lists,
                lambda a: "List ClickUp lists",
            ),
            ProviderTool(
                "read_task",
                "Read one task.",
                ReadTaskArgs,
                Capability.read,
                read_task,
                lambda a: f"Read ClickUp task {a.task_id}",
            ),
            ProviderTool(
                "create_task",
                "Create a task in a list.",
                CreateTaskArgs,
                Capability.create,
                create_task,
                lambda a: f"Create ClickUp task “{a.name}”",
                verify=verify_create,
            ),
            ProviderTool(
                "update_task",
                "Rename, describe or close a task.",
                UpdateTaskArgs,
                Capability.update,
                update_task,
                lambda a: f"Update ClickUp task {a.task_id}",
                verify=verify_update,
            ),
        ]
