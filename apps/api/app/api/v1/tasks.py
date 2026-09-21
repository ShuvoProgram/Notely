from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Query, status
from pydantic import BaseModel, Field

from app.api.deps import CurrentAuth, DbDep, SettingsDep
from app.core.responses import Envelope, ok
from app.models.notification import NotificationKind
from app.models.task import TaskStatus
from app.schemas.tasks import TaskBulkCreate, TaskCreate, TaskOut, TaskUpdate
from app.services.calendar_sync_service import CalendarSyncService
from app.services.notification_service import NotificationService
from app.services.task_service import TaskService

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("", response_model=Envelope[list[TaskOut]])
async def list_tasks(
    ctx: CurrentAuth,
    db: DbDep,
    status_filter: Annotated[TaskStatus | None, Query(alias="status")] = None,
    note_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    tasks = await TaskService(db).list_tasks(ctx.user, status=status_filter, note_id=note_id)
    return ok([TaskOut.model_validate(t) for t in tasks])


@router.post("", status_code=status.HTTP_201_CREATED, response_model=Envelope[TaskOut])
async def create_task(payload: TaskCreate, ctx: CurrentAuth, db: DbDep) -> dict[str, Any]:
    return ok(TaskOut.model_validate(await TaskService(db).create(ctx.user, payload)))


@router.post("/bulk", status_code=status.HTTP_201_CREATED, response_model=Envelope[list[TaskOut]])
async def create_tasks(payload: TaskBulkCreate, ctx: CurrentAuth, db: DbDep) -> dict[str, Any]:
    tasks = await TaskService(db).create_many(ctx.user, payload.tasks)
    return ok([TaskOut.model_validate(t) for t in tasks])


class CalendarStatusOut(BaseModel):
    connected: bool
    healthy: bool
    can_write: bool
    account: str | None
    status: str | None


@router.get("/calendar/status", response_model=Envelope[CalendarStatusOut])
async def calendar_status(ctx: CurrentAuth, db: DbDep, settings: SettingsDep) -> dict[str, Any]:
    return ok(CalendarStatusOut(**await CalendarSyncService(db, settings).status(ctx.user)))


@router.patch("/{task_id}", response_model=Envelope[TaskOut])
async def update_task(
    task_id: uuid.UUID, payload: TaskUpdate, ctx: CurrentAuth, db: DbDep, settings: SettingsDep
) -> dict[str, Any]:
    task = await TaskService(db).update(ctx.user, task_id, payload)
    if payload.status == TaskStatus.done:
        await NotificationService(db).notify(
            ctx.user,
            NotificationKind.task_completed,
            f"Completed: {task.title}",
            href="/app/tasks?view=done",
            dedupe_key=f"task:{task.id}:done:{task.completed_at}",
        )
    # A linked calendar event follows the task (title, time, done state); never blocks the edit.
    await CalendarSyncService(db, settings).resync_if_linked(ctx.user, task)
    return ok(TaskOut.model_validate(task))


@router.delete("/{task_id}", response_model=Envelope[dict[str, bool]])
async def delete_task(
    task_id: uuid.UUID, ctx: CurrentAuth, db: DbDep, settings: SettingsDep
) -> dict[str, Any]:
    service = TaskService(db)
    task = await service.get(ctx.user, task_id)
    if task.calendar_event_id:
        await CalendarSyncService(db, settings).unlink(ctx.user, task)
    await service.delete(ctx.user, task_id)
    return ok({"deleted": True})


# --- Google Calendar ------------------------------------------------------------------------------


class CalendarLinkIn(BaseModel):
    calendar_id: str | None = Field(default=None, max_length=255)


@router.post("/{task_id}/calendar", response_model=Envelope[TaskOut])
async def add_to_calendar(
    task_id: uuid.UUID, payload: CalendarLinkIn, ctx: CurrentAuth, db: DbDep, settings: SettingsDep
) -> dict[str, Any]:
    """Create (or refresh) the Google Calendar event for a task."""
    task = await TaskService(db).get(ctx.user, task_id)
    task = await CalendarSyncService(db, settings).sync(
        ctx.user, task, calendar_id=payload.calendar_id
    )
    return ok(TaskOut.model_validate(task))


@router.delete("/{task_id}/calendar", response_model=Envelope[TaskOut])
async def remove_from_calendar(
    task_id: uuid.UUID, ctx: CurrentAuth, db: DbDep, settings: SettingsDep
) -> dict[str, Any]:
    task = await TaskService(db).get(ctx.user, task_id)
    task = await CalendarSyncService(db, settings).unlink(ctx.user, task)
    return ok(TaskOut.model_validate(task))
