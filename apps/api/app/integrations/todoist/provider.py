"""Todoist: OAuth2 (non-expiring tokens), REST API v2."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field

from app.ai.tools.base import OutputField as F
from app.ai.tools.base import Verification
from app.core.oauth import OAuthEndpoints
from app.integrations.base.capabilities import Capability
from app.integrations.base.errors import ProviderError, ProviderErrorKind
from app.integrations.base.outputs import listing
from app.integrations.base.provider import (
    AuthType,
    ConnectionIdentity,
    PermissionSpec,
    ProviderContext,
    ProviderManifest,
)
from app.integrations.base.rest import ProviderTool, RestOAuthProvider
from app.integrations.base.triggers import ProviderTrigger, TriggerEvent, parse_time

WRITE_SCOPE = "data:read_write"
# REST v2 cannot change a task's project; the Sync API's `item_move` command can.
SYNC_URL = "https://api.todoist.com/sync/v9/sync"


class ListTasksArgs(BaseModel):
    """List open tasks, optionally filtered with a Todoist filter string or searched by text."""

    filter: str | None = Field(
        default=None, max_length=200, description="e.g. 'today', 'overdue', 'p1', '#Work'"
    )
    search: str | None = Field(default=None, max_length=200, description="Words in the task")
    limit: int = Field(default=25, ge=1, le=100)


class ListProjectsArgs(BaseModel):
    """List projects."""


class CreateTaskArgs(BaseModel):
    """Create a task."""

    content: str = Field(min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=5000)
    due_date: date | None = None
    due_string: str | None = Field(
        default=None, max_length=120, description="Natural language, e.g. 'tomorrow 3pm'"
    )
    priority: int = Field(default=1, ge=1, le=4, description="1 normal … 4 urgent")
    project_id: str | None = None
    labels: list[str] = Field(default_factory=list, max_length=20)


class UpdateTaskArgs(BaseModel):
    """Change a task's text, description, due date, priority or labels. Omitted fields stay."""

    task_id: str = Field(min_length=1, max_length=40)
    content: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=5000)
    due_date: date | None = None
    due_string: str | None = Field(default=None, max_length=120)
    priority: int | None = Field(default=None, ge=1, le=4)
    labels: list[str] | None = Field(default=None, max_length=20)


class MoveTaskArgs(BaseModel):
    """Move a task into another project."""

    task_id: str = Field(min_length=1, max_length=40)
    project_id: str = Field(min_length=1, max_length=40)


class TaskCreatedParams(BaseModel):
    """New tasks anywhere, or only in one project."""

    project_id: str | None = Field(default=None, max_length=40)


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
                scope=WRITE_SCOPE,
                label="Complete, update and move tasks",
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

    def build_triggers(self) -> list[ProviderTrigger]:
        async def task_created(
            ctx: ProviderContext, p: TaskCreatedParams, since: datetime
        ) -> list[TriggerEvent]:
            params = {"project_id": p.project_id} if p.project_id else {}
            async with self.http(ctx) as http:
                tasks = (await http.get("/tasks", params=params)).json()
            events = []
            for t in tasks:
                created = parse_time(t.get("created_at"))
                if created is None or created <= since:
                    continue
                events.append(
                    TriggerEvent(
                        id=str(t["id"]),
                        occurred_at=created,
                        data={
                            "task_id": t["id"],
                            "content": t.get("content", ""),
                            "description": t.get("description") or "",
                            "due": (t.get("due") or {}).get("date"),
                            "priority": t.get("priority"),
                            "project_id": t.get("project_id"),
                            "created_at": t.get("created_at"),
                            "url": t.get("url"),
                        },
                    )
                )
            return events

        return [
            ProviderTrigger(
                "task_created",
                "New task",
                "Starts when a task is added in Todoist (anywhere, or in one project).",
                task_created,
                TaskCreatedParams,
                outputs=(
                    F("content", "Task"),
                    F("description", "Description", "long_text"),
                    F("due", "Due", "date"),
                    F("priority", "Priority", "number"),
                    F("task_id", "Task ID"),
                    F("url", "Link", "url"),
                ),
                scope="data:read",
            )
        ]

    def build_tools(self):  # type: ignore[no-untyped-def]
        async def list_tasks(ctx: ProviderContext, a: ListTasksArgs) -> dict[str, Any]:
            terms = [a.filter] if a.filter else []
            if a.search:
                terms.append(f"search: {a.search}")
            params = {"filter": " & ".join(f"({t})" for t in terms)} if terms else {}
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
            elif a.due_string:
                payload["due_string"] = a.due_string
            if a.project_id:
                payload["project_id"] = a.project_id
            if a.labels:
                payload["labels"] = a.labels
            async with self.http(ctx) as http:
                task = (await http.post("/tasks", json=payload)).json()
            return {"task_id": task.get("id"), "url": task.get("url"), "content": a.content}

        async def update_task(ctx: ProviderContext, a: UpdateTaskArgs) -> dict[str, Any]:
            payload: dict[str, Any] = {
                key: getattr(a, key)
                for key in ("content", "description", "priority", "labels")
                if getattr(a, key) is not None
            }
            if a.due_date:
                payload["due_date"] = a.due_date.isoformat()
            elif a.due_string:
                payload["due_string"] = a.due_string
            if not payload:
                raise ProviderError(ProviderErrorKind.invalid_request, "Nothing to change.")
            async with self.http(ctx) as http:
                task = (await http.post(f"/tasks/{a.task_id}", json=payload)).json()
            return {
                "task_id": a.task_id,
                "content": task.get("content"),
                "due": (task.get("due") or {}).get("date"),
                "priority": task.get("priority"),
                "url": task.get("url"),
            }

        async def move_task(ctx: ProviderContext, a: MoveTaskArgs) -> dict[str, Any]:
            command = {
                "type": "item_move",
                "uuid": str(uuid.uuid4()),
                "args": {"id": a.task_id, "project_id": a.project_id},
            }
            async with self.http(ctx) as http:
                result = (await http.post(SYNC_URL, json={"commands": [command]})).json()
            if (result.get("sync_status") or {}).get(command["uuid"]) != "ok":
                raise ProviderError(ProviderErrorKind.invalid_request, "Todoist refused the move.")
            return {"task_id": a.task_id, "project_id": a.project_id}

        async def complete_task(ctx: ProviderContext, a: CompleteTaskArgs) -> dict[str, Any]:
            async with self.http(ctx) as http:
                await http.post(f"/tasks/{a.task_id}/close")
            return {"task_id": a.task_id, "completed": True}

        async def verify_create_task(
            ctx: ProviderContext, a: CreateTaskArgs, result: dict[str, Any]
        ) -> Verification:
            async with self.http(ctx) as http:
                task = (await http.get(f"/tasks/{result['task_id']}")).json()
            if task.get("content") != a.content:
                return Verification.failed("Task exists but its content differs")
            return Verification.verified("Task is in Todoist")

        async def verify_update_task(
            ctx: ProviderContext, a: UpdateTaskArgs, result: dict[str, Any]
        ) -> Verification:
            async with self.http(ctx) as http:
                task = (await http.get(f"/tasks/{a.task_id}")).json()
            if a.content is not None and task.get("content") != a.content:
                return Verification.failed("The task's text did not change")
            if a.priority is not None and task.get("priority") != a.priority:
                return Verification.failed("The task's priority did not change")
            if a.due_date and (task.get("due") or {}).get("date") != a.due_date.isoformat():
                return Verification.failed("The task's due date did not change")
            return Verification.verified("Task updated in Todoist")

        async def verify_move_task(
            ctx: ProviderContext, a: MoveTaskArgs, result: dict[str, Any]
        ) -> Verification:
            async with self.http(ctx) as http:
                task = (await http.get(f"/tasks/{a.task_id}")).json()
            if str(task.get("project_id")) != a.project_id:
                return Verification.failed("The task is still in its old project")
            return Verification.verified("Task moved in Todoist")

        async def verify_complete_task(
            ctx: ProviderContext, a: CompleteTaskArgs, result: dict[str, Any]
        ) -> Verification:
            # Todoist drops completed tasks from the active-task endpoint (404) or flags them.
            try:
                async with self.http(ctx) as http:
                    task = (await http.get(f"/tasks/{a.task_id}")).json()
            except ProviderError as exc:
                if exc.kind == ProviderErrorKind.not_found:
                    return Verification.verified("Task is no longer active in Todoist")
                raise
            if task.get("is_completed"):
                return Verification.verified("Task is completed in Todoist")
            return Verification.failed("Task is still open in Todoist")

        return [
            ProviderTool(
                "list_tasks",
                "List open Todoist tasks.",
                ListTasksArgs,
                Capability.read,
                list_tasks,
                lambda a: "List Todoist tasks",
                outputs=(
                    listing(
                        "tasks",
                        "Tasks",
                        F("content", "Task"),
                        F("due", "Due", "date"),
                        F("priority", "Priority", "number"),
                        F("url", "Link", "url"),
                    ),
                ),
            ),
            ProviderTool(
                "list_projects",
                "List Todoist projects.",
                ListProjectsArgs,
                Capability.read,
                list_projects,
                lambda a: "List Todoist projects",
            ),
            ProviderTool(
                "create_task",
                "Create a Todoist task.",
                CreateTaskArgs,
                Capability.create,
                create_task,
                lambda a: f"Create Todoist task “{a.content}”",
                verify=verify_create_task,
                outputs=(F("task_id", "Task ID"), F("url", "Link", "url"), F("content", "Task")),
            ),
            ProviderTool(
                "update_task",
                "Change a Todoist task's text, due date, priority or labels.",
                UpdateTaskArgs,
                Capability.update,
                update_task,
                lambda a: f"Update Todoist task {a.task_id}",
                verify=verify_update_task,
                scope=WRITE_SCOPE,
                outputs=(F("task_id", "Task ID"), F("due", "Due", "date"), F("url", "Link", "url")),
            ),
            ProviderTool(
                "move_task",
                "Move a Todoist task to another project.",
                MoveTaskArgs,
                Capability.update,
                move_task,
                lambda a: f"Move Todoist task {a.task_id} to another project",
                verify=verify_move_task,
                scope=WRITE_SCOPE,
            ),
            ProviderTool(
                "complete_task",
                "Complete a Todoist task.",
                CompleteTaskArgs,
                Capability.update,
                complete_task,
                lambda a: f"Complete Todoist task {a.task_id}",
                verify=verify_complete_task,
                scope=WRITE_SCOPE,
            ),
        ]
