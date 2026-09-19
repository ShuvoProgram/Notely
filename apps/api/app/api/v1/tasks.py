from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentAuth, DbDep
from app.core.responses import Envelope, ok
from app.models.task import TaskStatus
from app.schemas.tasks import TaskBulkCreate, TaskCreate, TaskOut, TaskUpdate
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


@router.patch("/{task_id}", response_model=Envelope[TaskOut])
async def update_task(
    task_id: uuid.UUID, payload: TaskUpdate, ctx: CurrentAuth, db: DbDep
) -> dict[str, Any]:
    return ok(TaskOut.model_validate(await TaskService(db).update(ctx.user, task_id, payload)))


@router.delete("/{task_id}", response_model=Envelope[dict[str, bool]])
async def delete_task(task_id: uuid.UUID, ctx: CurrentAuth, db: DbDep) -> dict[str, Any]:
    await TaskService(db).delete(ctx.user, task_id)
    return ok({"deleted": True})
