"""Asana: OAuth2 with PKCE and refresh tokens, REST API 1.0."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from pydantic import BaseModel, Field

from app.ai.tools.base import OutputField as F
from app.ai.tools.base import Verification
from app.core.oauth import OAuthEndpoints
from app.integrations.base.capabilities import Capability
from app.integrations.base.errors import ProviderError, ProviderErrorKind
from app.integrations.base.outputs import HIT_FIELDS, listing
from app.integrations.base.provider import (
    AuthType,
    ConnectionIdentity,
    PermissionSpec,
    ProviderContext,
    ProviderManifest,
)
from app.integrations.base.rest import ProviderTool, RestOAuthProvider
from app.integrations.base.triggers import ProviderTrigger, TriggerEvent, parse_time


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


class SearchProjectsArgs(BaseModel):
    """Find projects by name."""

    query: str = Field(default="", max_length=200, description="Leave empty to list projects")
    workspace_gid: str | None = None
    limit: int = Field(default=10, ge=1, le=50)


class FindPeopleArgs(BaseModel):
    """Find people in the workspace by name or email (to assign tasks to them)."""

    query: str = Field(min_length=1, max_length=200)
    workspace_gid: str | None = None
    limit: int = Field(default=5, ge=1, le=20)


class ReadTaskArgs(BaseModel):
    """Read one task: description, assignee, due date, projects and recent comments."""

    task_gid: str = Field(min_length=1, max_length=40)


ASSIGNEE_HELP = "'me', a person's email, or a user gid from find_people"


class CreateTaskArgs(BaseModel):
    """Create a task (assigned to you unless you name someone else)."""

    name: str = Field(min_length=1, max_length=500)
    notes: str | None = Field(default=None, max_length=5000)
    due_on: date | None = None
    assignee: str = Field(default="me", min_length=1, max_length=200, description=ASSIGNEE_HELP)
    workspace_gid: str | None = None
    project_gid: str | None = None


class UpdateTaskArgs(BaseModel):
    """Change a task's name, description, due date, assignee or completion. Omitted fields stay."""

    task_gid: str = Field(min_length=1, max_length=40)
    name: str | None = Field(default=None, min_length=1, max_length=500)
    notes: str | None = Field(default=None, max_length=5000)
    due_on: date | None = None
    clear_due_date: bool = False
    assignee: str | None = Field(default=None, max_length=200, description=ASSIGNEE_HELP)
    completed: bool | None = None


class AddCommentArgs(BaseModel):
    """Post a comment on a task (visible to everyone on the task)."""

    task_gid: str = Field(min_length=1, max_length=40)
    text: str = Field(min_length=1, max_length=5000)


class TaskCreatedParams(BaseModel):
    """New tasks in one project, or (when empty) new tasks assigned to you."""

    project_gid: str | None = Field(default=None, max_length=40)


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
        description=(
            "Search projects and tasks; create, assign, update, complete and comment on tasks "
            "with approval."
        ),
        logo_url="https://cdn.simpleicons.org/asana",
        docs_url="https://developers.asana.com/docs/oauth",
        auth=AuthType.oauth2,
        capabilities=[
            Capability.search,
            Capability.read,
            Capability.create,
            Capability.update,
            Capability.comment,
        ],
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

    async def _typeahead(
        self, ctx: ProviderContext, ws: str, kind: str, query: str, limit: int, fields: str
    ) -> list[dict[str, Any]]:
        async with self.http(ctx) as http:
            data: list[dict[str, Any]] = (
                await http.get(
                    f"/workspaces/{ws}/typeahead",
                    params={
                        "resource_type": kind,
                        "query": query,
                        "count": limit,
                        "opt_fields": fields,
                    },
                )
            ).json()["data"]
        return data

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

    def build_triggers(self) -> list[ProviderTrigger]:
        async def task_created(
            ctx: ProviderContext, p: TaskCreatedParams, since: datetime
        ) -> list[TriggerEvent]:
            params: dict[str, Any] = {
                "modified_since": since.astimezone(UTC).isoformat(),
                "limit": 100,
                "opt_fields": "name,notes,due_on,created_at,permalink_url,assignee.name,"
                "projects.name",
            }
            if p.project_gid:
                params["project"] = p.project_gid
            else:
                params["assignee"] = "me"
                params["workspace"] = await self._workspace(ctx, None)
            async with self.http(ctx) as http:
                tasks = (await http.get("/tasks", params=params)).json()["data"]
            events = []
            for t in tasks:
                created = parse_time(t.get("created_at"))
                if created is None or created <= since:
                    continue  # modified, not new
                events.append(
                    TriggerEvent(
                        id=str(t["gid"]),
                        occurred_at=created,
                        data={
                            "task_gid": t["gid"],
                            "name": t.get("name", ""),
                            "notes": t.get("notes") or "",
                            "due_on": t.get("due_on"),
                            "assignee": (t.get("assignee") or {}).get("name"),
                            "projects": ", ".join(
                                str(x.get("name")) for x in t.get("projects") or []
                            ),
                            "created_at": t.get("created_at"),
                            "url": t.get("permalink_url"),
                        },
                    )
                )
            return events

        return [
            ProviderTrigger(
                "task_created",
                "New task",
                "Starts when a task is added to a project, or assigned to you.",
                task_created,
                TaskCreatedParams,
                outputs=(
                    F("name", "Task"),
                    F("notes", "Description", "long_text"),
                    F("assignee", "Assignee"),
                    F("due_on", "Due", "date"),
                    F("projects", "Projects"),
                    F("task_gid", "Task ID"),
                    F("url", "Link", "url"),
                ),
            )
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
            data: dict[str, Any] = {"name": a.name, "assignee": a.assignee, "workspace": ws}
            if a.notes:
                data["notes"] = a.notes
            if a.due_on:
                data["due_on"] = a.due_on.isoformat()
            if a.project_gid:
                data["projects"] = [a.project_gid]
            async with self.http(ctx) as http:
                task = (await http.post("/tasks", json={"data": data})).json()["data"]
            return {"task_gid": task.get("gid"), "url": task.get("permalink_url"), "name": a.name}

        async def search_projects(ctx: ProviderContext, a: SearchProjectsArgs) -> dict[str, Any]:
            ws = await self._workspace(ctx, a.workspace_gid)
            projects = await self._typeahead(
                ctx, ws, "project", a.query, a.limit, "name,permalink_url,archived"
            )
            return {
                "projects": [
                    {
                        "gid": p["gid"],
                        "name": self.wrap(p.get("name", ""), ref=p["gid"]),
                        "url": p.get("permalink_url"),
                    }
                    for p in projects
                    if not p.get("archived")
                ]
            }

        async def find_people(ctx: ProviderContext, a: FindPeopleArgs) -> dict[str, Any]:
            ws = await self._workspace(ctx, a.workspace_gid)
            people = await self._typeahead(ctx, ws, "user", a.query, a.limit, "name,email")
            return {
                "people": [
                    {"gid": u["gid"], "name": u.get("name"), "email": u.get("email")}
                    for u in people
                ]
            }

        async def read_task(ctx: ProviderContext, a: ReadTaskArgs) -> dict[str, Any]:
            async with self.http(ctx) as http:
                task = (
                    await http.get(
                        f"/tasks/{a.task_gid}",
                        params={"opt_fields": f"{fields},assignee.name,modified_at"},
                    )
                ).json()["data"]
                stories = (
                    await http.get(
                        f"/tasks/{a.task_gid}/stories",
                        params={"opt_fields": "type,text,created_by.name,created_at", "limit": 50},
                    )
                ).json()["data"]
            comments = [s for s in stories if s.get("type") == "comment"][-10:]
            return {
                "gid": task.get("gid"),
                "name": self.wrap(task.get("name", ""), ref=a.task_gid),
                "notes": self.wrap(task.get("notes") or "", ref=a.task_gid),
                "due_on": task.get("due_on"),
                "completed": task.get("completed"),
                "assignee": (task.get("assignee") or {}).get("name"),
                "projects": [p.get("name") for p in task.get("projects") or []],
                "url": task.get("permalink_url"),
                "comments": [
                    {
                        "author": (c.get("created_by") or {}).get("name"),
                        "text": self.wrap(c.get("text") or "", ref=a.task_gid),
                        "at": c.get("created_at"),
                    }
                    for c in comments
                ],
                "sources": [
                    self.source(
                        object_id=a.task_gid,
                        title=str(task.get("name", "")),
                        url=task.get("permalink_url"),
                    )
                ],
            }

        async def update_task(ctx: ProviderContext, a: UpdateTaskArgs) -> dict[str, Any]:
            data: dict[str, Any] = {
                key: getattr(a, key)
                for key in ("name", "notes", "assignee", "completed")
                if getattr(a, key) is not None
            }
            if a.clear_due_date:
                data["due_on"] = None
            elif a.due_on:
                data["due_on"] = a.due_on.isoformat()
            if not data:
                raise ProviderError(ProviderErrorKind.invalid_request, "Nothing to change.")
            async with self.http(ctx) as http:
                task = (
                    await http.request("PUT", f"/tasks/{a.task_gid}", json={"data": data})
                ).json()["data"]
            return {
                "task_gid": a.task_gid,
                "name": task.get("name"),
                "due_on": task.get("due_on"),
                "completed": task.get("completed"),
                "url": task.get("permalink_url"),
            }

        async def add_comment(ctx: ProviderContext, a: AddCommentArgs) -> dict[str, Any]:
            async with self.http(ctx) as http:
                story = (
                    await http.post(f"/tasks/{a.task_gid}/stories", json={"data": {"text": a.text}})
                ).json()["data"]
            return {"task_gid": a.task_gid, "comment_gid": story.get("gid")}

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

        async def verify_update_task(
            ctx: ProviderContext, a: UpdateTaskArgs, result: dict[str, Any]
        ) -> Verification:
            async with self.http(ctx) as http:
                task = (
                    await http.get(
                        f"/tasks/{a.task_gid}",
                        params={"opt_fields": "name,due_on,completed,assignee.email"},
                    )
                ).json()["data"]
            if a.name is not None and task.get("name") != a.name:
                return Verification.failed("The task's name did not change")
            if a.due_on and task.get("due_on") != a.due_on.isoformat():
                return Verification.failed("The task's due date did not change")
            if a.completed is not None and bool(task.get("completed")) != a.completed:
                return Verification.failed("The task's completion did not change")
            return Verification.verified("Task updated in Asana")

        async def verify_add_comment(
            ctx: ProviderContext, a: AddCommentArgs, result: dict[str, Any]
        ) -> Verification:
            async with self.http(ctx) as http:
                stories = (
                    await http.get(
                        f"/tasks/{a.task_gid}/stories", params={"opt_fields": "type,text"}
                    )
                ).json()["data"]
            if any(s.get("gid") == result.get("comment_gid") for s in stories):
                return Verification.verified("Comment is on the task")
            return Verification.unverified("The comment was posted but could not be read back")

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
                outputs=(
                    listing(
                        "tasks",
                        "Tasks",
                        F("name", "Task"),
                        F("due_on", "Due", "date"),
                        F("completed", "Completed", "boolean"),
                        F("url", "Link", "url"),
                    ),
                ),
            ),
            ProviderTool(
                "search_tasks",
                "Search Asana tasks.",
                SearchTasksArgs,
                Capability.search,
                search_tasks,
                lambda a: f"Search Asana for “{a.query}”",
                outputs=(listing("results", "Tasks", *HIT_FIELDS),),
            ),
            ProviderTool(
                "search_projects",
                "Find Asana projects by name.",
                SearchProjectsArgs,
                Capability.search,
                search_projects,
                lambda a: f"Search Asana projects for “{a.query}”" if a.query else "List projects",
                outputs=(
                    listing("projects", "Projects", F("name", "Project"), F("url", "Link", "url")),
                ),
            ),
            ProviderTool(
                "find_people",
                "Find people in Asana by name or email (to assign them tasks).",
                FindPeopleArgs,
                Capability.search,
                find_people,
                lambda a: f"Find “{a.query}” in Asana",
                outputs=(listing("people", "People", F("name", "Name"), F("email", "Email")),),
            ),
            ProviderTool(
                "read_task",
                "Read an Asana task with its description, assignee and recent comments.",
                ReadTaskArgs,
                Capability.read,
                read_task,
                lambda a: f"Read Asana task {a.task_gid}",
                outputs=(
                    F("name", "Task"),
                    F("notes", "Description"),
                    F("assignee", "Assignee"),
                    F("due_on", "Due", "date"),
                    F("url", "Link", "url"),
                ),
            ),
            ProviderTool(
                "create_task",
                "Create an Asana task, assigned to you or to someone else.",
                CreateTaskArgs,
                Capability.create,
                create_task,
                lambda a: (
                    f"Create Asana task “{a.name}”"
                    + ("" if a.assignee == "me" else f" for {a.assignee}")
                ),
                verify=verify_create_task,
                outputs=(F("task_gid", "Task ID"), F("url", "Link", "url"), F("name", "Task")),
            ),
            ProviderTool(
                "update_task",
                "Change an Asana task's name, description, due date, assignee or completion.",
                UpdateTaskArgs,
                Capability.update,
                update_task,
                lambda a: f"Update Asana task {a.task_gid}",
                verify=verify_update_task,
                outputs=(
                    F("task_gid", "Task ID"),
                    F("due_on", "Due", "date"),
                    F("url", "Link", "url"),
                ),
            ),
            ProviderTool(
                "add_comment",
                "Comment on an Asana task.",
                AddCommentArgs,
                Capability.comment,
                add_comment,
                lambda a: f"Comment on Asana task {a.task_gid}",
                verify=verify_add_comment,
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
