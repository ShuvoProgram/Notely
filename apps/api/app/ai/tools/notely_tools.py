"""Internal Notely tools: notes, tasks, planning and cross-app search.

Read tools return untrusted-wrapped content. Write tools declare a `verify` read-back so the
framework can confirm the change actually landed before the assistant reports it."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.ai.tools.base import ToolContext, ToolRegistry, ToolSpec, Verification, untrusted
from app.models.ai import RiskLevel
from app.models.task import TaskPriority, TaskSource, TaskStatus
from app.schemas.notes import NoteCreate, NoteListQuery
from app.schemas.tasks import TaskCreate
from app.services.note_service import NoteService
from app.services.rich_text import excerpt
from app.services.task_service import TaskService

MAX_NOTE_CHARS = 12_000


# --- argument schemas ---------------------------------------------------------------------------


class SearchNotesArgs(BaseModel):
    """Search the user's notes by keywords. Use before answering questions about their notes."""

    query: str = Field(min_length=1, max_length=200, description="Keywords to search for")
    limit: int = Field(default=8, ge=1, le=20)


class ReadNoteArgs(BaseModel):
    """Read the full text of one note by id (ids come from search results)."""

    note_id: uuid.UUID


class ListRecentNotesArgs(BaseModel):
    """List the most recently edited notes."""

    limit: int = Field(default=10, ge=1, le=25)


class CreateNoteArgs(BaseModel):
    """Create a new note in the user's workspace."""

    title: str = Field(min_length=1, max_length=300)
    body: str = Field(
        default="",
        max_length=20_000,
        description="Plain text body; paragraphs separated by blank lines",
    )


class ListTasksArgs(BaseModel):
    """List the user's tasks."""

    status: TaskStatus | None = Field(default=None, description="Filter by open/done")


class CreateTaskArgs(BaseModel):
    """Create a task for the user."""

    title: str = Field(min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=5000)
    due_date: date | None = Field(default=None, description="ISO date, e.g. 2026-10-01")
    priority: TaskPriority = TaskPriority.none
    note_id: uuid.UUID | None = Field(default=None, description="Note this task came from, if any")


class CompleteTaskArgs(BaseModel):
    """Mark a task as done."""

    task_id: uuid.UUID


class SearchEverythingArgs(BaseModel):
    """Search the user's notes AND every connected app (Slack, Notion, Jira, ...) in one call.
    Use this first for requests that may involve several sources."""

    query: str = Field(min_length=1, max_length=200, description="Keywords to search for")
    limit: int = Field(default=8, ge=1, le=20, description="Max results per source")


class PlanStep(BaseModel):
    title: str = Field(min_length=1, max_length=120, description="What this step achieves")
    kind: Literal["read", "propose", "verify", "answer"] = Field(
        description="read = look things up; propose = suggest changes for approval; "
        "verify = confirm changes landed; answer = summarise for the user"
    )
    tools: list[str] = Field(
        default_factory=list, max_length=6, description="Tool names this step will use"
    )


class PlanStepsArgs(BaseModel):
    """Declare a short plan before a multi-step or cross-app request. The user sees the plan as
    a progress checklist. Call this once, before reading anything."""

    goal: str = Field(min_length=1, max_length=200)
    steps: list[PlanStep] = Field(min_length=1, max_length=8)


# --- handlers -----------------------------------------------------------------------------------


def _body_to_doc(body: str) -> dict[str, Any]:
    paragraphs = [p.strip() for p in body.split("\n\n") if p.strip()] or [""]
    return {
        "type": "doc",
        "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": p}] if p else []}
            for p in paragraphs
        ],
    }


async def search_notes(ctx: ToolContext, args: SearchNotesArgs) -> dict[str, Any]:
    rows = await NoteService(ctx.db).search(ctx.user, args.query, args.limit)
    return {
        "results": [
            {
                "note_id": str(r.note.id),
                "title": r.note.title or "Untitled",
                "snippet": untrusted(excerpt(r.note.plain_text, 240), source=f"note:{r.note.id}"),
                "updated_at": r.note.updated_at.isoformat(),
            }
            for r in rows
        ],
        "sources": [
            {
                "provider": "notely",
                "object_id": str(r.note.id),
                "title": r.note.title or "Untitled",
                "url": f"/app/notes/{r.note.id}",
            }
            for r in rows
        ],
    }


async def read_note(ctx: ToolContext, args: ReadNoteArgs) -> dict[str, Any]:
    note = await NoteService(ctx.db).get_note(ctx.user, args.note_id)
    text = note.plain_text[:MAX_NOTE_CHARS]
    return {
        "note_id": str(note.id),
        "title": note.title or "Untitled",
        "content": untrusted(text, source=f"note:{note.id}"),
        "truncated": len(note.plain_text) > MAX_NOTE_CHARS,
        "sources": [
            {
                "provider": "notely",
                "object_id": str(note.id),
                "title": note.title or "Untitled",
                "url": f"/app/notes/{note.id}",
            }
        ],
    }


async def list_recent_notes(ctx: ToolContext, args: ListRecentNotesArgs) -> dict[str, Any]:
    notes, _ = await NoteService(ctx.db).list_notes(ctx.user, NoteListQuery(limit=args.limit))
    return {
        "notes": [
            {
                "note_id": str(n.id),
                "title": n.title or "Untitled",
                "updated_at": n.updated_at.isoformat(),
            }
            for n in notes
        ]
    }


async def create_note(ctx: ToolContext, args: CreateNoteArgs) -> dict[str, Any]:
    note = await NoteService(ctx.db).create_note(
        ctx.user, NoteCreate(title=args.title, content_json=_body_to_doc(args.body))
    )
    return {"note_id": str(note.id), "title": note.title, "url": f"/app/notes/{note.id}"}


async def list_tasks(ctx: ToolContext, args: ListTasksArgs) -> dict[str, Any]:
    tasks = await TaskService(ctx.db).list_tasks(ctx.user, status=args.status)
    return {
        "tasks": [
            {
                "task_id": str(t.id),
                "title": t.title,
                "status": t.status.value,
                "priority": t.priority.value,
                "due_date": t.due_date.isoformat() if t.due_date else None,
            }
            for t in tasks
        ]
    }


async def create_task(ctx: ToolContext, args: CreateTaskArgs) -> dict[str, Any]:
    task = await TaskService(ctx.db).create(
        ctx.user,
        TaskCreate(
            title=args.title,
            description=args.description,
            due_date=args.due_date,
            priority=args.priority,
            note_id=args.note_id,
            source=TaskSource.ai,
        ),
    )
    return {"task_id": str(task.id), "title": task.title, "url": "/app/tasks"}


async def complete_task(ctx: ToolContext, args: CompleteTaskArgs) -> dict[str, Any]:
    from app.schemas.tasks import TaskUpdate

    task = await TaskService(ctx.db).update(
        ctx.user, args.task_id, TaskUpdate(status=TaskStatus.done)
    )
    return {"task_id": str(task.id), "status": task.status.value}


async def search_everything(ctx: ToolContext, args: SearchEverythingArgs) -> dict[str, Any]:
    from app.core.config import get_settings
    from app.services.search_service import UnifiedSearchService

    result = await UnifiedSearchService(ctx.db, get_settings()).search(
        ctx.user, args.query, args.limit
    )
    return {
        "results": [
            {
                "source": h.source,
                "kind": h.kind,
                "id": h.id,
                "title": untrusted(h.title, source=f"{h.source}:{h.id}"),
                "snippet": untrusted(h.snippet, source=f"{h.source}:{h.id}"),
                "url": h.url,
            }
            for h in result.hits
        ],
        "sources_searched": [
            {"source": s.source, "ok": s.ok, "count": s.count, "error": s.error}
            for s in result.sources
        ],
        "sources": [
            {"provider": h.source, "object_id": h.id, "title": h.title, "url": h.url}
            for h in result.hits
        ],
    }


async def plan_steps(ctx: ToolContext, args: PlanStepsArgs) -> dict[str, Any]:
    # The framework records and streams the plan; the model just gets an acknowledgement.
    return {
        "plan": {
            "goal": args.goal,
            "steps": [
                {"title": s.title, "kind": s.kind, "tools": s.tools, "status": "pending"}
                for s in args.steps
            ],
        },
        "message": "Plan recorded. Proceed with the steps.",
    }


# --- verifiers (read-back after a write) -------------------------------------------------------


async def verify_note_created(
    ctx: ToolContext, args: CreateNoteArgs, result: dict[str, Any]
) -> Verification:
    note = await NoteService(ctx.db).get_note(ctx.user, uuid.UUID(str(result["note_id"])))
    if note.title != args.title:
        return Verification.failed("Note exists but its title differs from what was requested")
    return Verification.verified(f"Note “{note.title}” exists in your workspace")


async def verify_task_created(
    ctx: ToolContext, args: CreateTaskArgs, result: dict[str, Any]
) -> Verification:
    task = await TaskService(ctx.db).get(ctx.user, uuid.UUID(str(result["task_id"])))
    if task.title != args.title or task.status != TaskStatus.open:
        return Verification.failed("Task exists but does not match what was requested")
    return Verification.verified(f"Task “{task.title}” is in your task list")


async def verify_task_completed(
    ctx: ToolContext, args: CompleteTaskArgs, result: dict[str, Any]
) -> Verification:
    task = await TaskService(ctx.db).get(ctx.user, args.task_id)
    if task.status != TaskStatus.done:
        return Verification.failed("Task is still open")
    return Verification.verified(f"Task “{task.title}” is marked done")


# --- registry -----------------------------------------------------------------------------------


def register_notely_tools(registry: ToolRegistry) -> None:
    registry.register(
        ToolSpec(
            name="search_notes",
            description="Search the user's notes by keywords; returns ids, titles and snippets.",
            args_schema=SearchNotesArgs,
            risk=RiskLevel.read,
            capability="search",
            handler=search_notes,
            summarize=lambda a: f"Search notes for “{a.query}”",
        )
    )
    registry.register(
        ToolSpec(
            name="read_note",
            description="Read the full content of a note by id.",
            args_schema=ReadNoteArgs,
            risk=RiskLevel.read,
            capability="read",
            handler=read_note,
            summarize=lambda a: "Read a note",
        )
    )
    registry.register(
        ToolSpec(
            name="list_recent_notes",
            description="List the user's most recently edited notes.",
            args_schema=ListRecentNotesArgs,
            risk=RiskLevel.read,
            capability="read",
            handler=list_recent_notes,
            summarize=lambda a: "List recent notes",
        )
    )
    registry.register(
        ToolSpec(
            name="create_note",
            description="Create a new note in the workspace (the user reviews it before it runs).",
            args_schema=CreateNoteArgs,
            risk=RiskLevel.write,
            capability="create",
            handler=create_note,
            summarize=lambda a: f"Create note “{a.title}”",
            verify=verify_note_created,
        )
    )
    registry.register(
        ToolSpec(
            name="list_tasks",
            description="List the user's tasks, optionally filtered by status.",
            args_schema=ListTasksArgs,
            risk=RiskLevel.read,
            capability="read",
            handler=list_tasks,
            summarize=lambda a: "List tasks",
        )
    )
    registry.register(
        ToolSpec(
            name="create_task",
            description="Create a task for the user (title, optional due date and priority).",
            args_schema=CreateTaskArgs,
            risk=RiskLevel.write,
            capability="create",
            handler=create_task,
            summarize=lambda a: (
                f"Create task “{a.title}”" + (f" due {a.due_date}" if a.due_date else "")
            ),
            verify=verify_task_created,
        )
    )
    registry.register(
        ToolSpec(
            name="complete_task",
            description="Mark one of the user's tasks as done.",
            args_schema=CompleteTaskArgs,
            risk=RiskLevel.write,
            capability="update",
            handler=complete_task,
            summarize=lambda a: "Mark a task as done",
            verify=verify_task_completed,
        )
    )
    registry.register(
        ToolSpec(
            name="search_everything",
            description=(
                "Search notes and every connected app at once. Results say which app they came "
                "from; use the matching app's read tool for details."
            ),
            args_schema=SearchEverythingArgs,
            risk=RiskLevel.read,
            capability="search",
            handler=search_everything,
            summarize=lambda a: f"Search everything for “{a.query}”",
        )
    )
    registry.register(
        ToolSpec(
            name="plan_steps",
            description=(
                "Declare a short plan (goal + 2-8 steps) before a multi-step or cross-app "
                "request. Call once, first. Not needed for simple questions."
            ),
            args_schema=PlanStepsArgs,
            risk=RiskLevel.read,
            capability="plan",
            handler=plan_steps,
            summarize=lambda a: f"Plan: {a.goal}",
            tags=("plan",),
        )
    )
