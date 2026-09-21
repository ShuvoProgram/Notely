"""Tasks: internal for now; a task may later be synchronised to an external provider."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFound
from app.db.base import utcnow
from app.models.note import Note
from app.models.task import Task, TaskStatus
from app.models.user import User
from app.schemas.tasks import TaskCreate, TaskUpdate


class TaskService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_tasks(
        self, user: User, *, status: TaskStatus | None = None, note_id: uuid.UUID | None = None
    ) -> list[Task]:
        stmt = select(Task).where(Task.user_id == user.id)
        if status is not None:
            stmt = stmt.where(Task.status == status)
        if note_id is not None:
            stmt = stmt.where(Task.note_id == note_id)
        stmt = stmt.order_by(Task.status, Task.due_date.nulls_last(), Task.created_at.desc())
        return list(await self.db.scalars(stmt))

    async def get(self, user: User, task_id: uuid.UUID) -> Task:
        task = await self.db.scalar(select(Task).where(Task.id == task_id, Task.user_id == user.id))
        if task is None:
            raise NotFound("Task not found.")
        return task

    async def create(self, user: User, payload: TaskCreate, *, commit: bool = True) -> Task:
        if payload.note_id is not None:
            owned = await self.db.scalar(
                select(Note.id).where(Note.id == payload.note_id, Note.user_id == user.id)
            )
            if owned is None:
                raise NotFound("Note not found.")
        task = Task(
            tenant_id=user.tenant_id,
            user_id=user.id,
            title=payload.title,
            description=payload.description,
            due_date=payload.due_date,
            due_time=payload.due_time,
            timezone=payload.timezone,
            priority=payload.priority,
            note_id=payload.note_id,
            source=payload.source,
        )
        self.db.add(task)
        await self.db.flush()
        if commit:
            await self.db.commit()
        return task

    async def create_many(self, user: User, items: list[TaskCreate]) -> list[Task]:
        tasks = [await self.create(user, item, commit=False) for item in items]
        await self.db.commit()
        return tasks

    async def update(self, user: User, task_id: uuid.UUID, payload: TaskUpdate) -> Task:
        task = await self.get(user, task_id)
        changes = payload.model_dump(exclude_unset=True)
        if changes.pop("clear_due_date", False):
            task.due_date = None
            task.due_time = None
            changes.pop("due_date", None)
            changes.pop("due_time", None)
        if changes.pop("clear_due_time", False):
            task.due_time = None
            changes.pop("due_time", None)
        for key, value in changes.items():
            if value is None and key != "description":
                continue
            setattr(task, key, value)
        if "status" in changes and changes["status"] is not None:
            task.completed_at = utcnow() if changes["status"] == TaskStatus.done else None
        await self.db.commit()
        return task

    async def delete(self, user: User, task_id: uuid.UUID) -> None:
        task = await self.get(user, task_id)
        await self.db.delete(task)
        await self.db.commit()
