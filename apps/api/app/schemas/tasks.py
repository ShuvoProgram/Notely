from __future__ import annotations

import uuid
from datetime import date, datetime, time

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.task import TaskPriority, TaskSource, TaskStatus


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=5000)
    due_date: date | None = None
    due_time: time | None = None
    # IANA zone the due time is expressed in (sent by the client, e.g. "Asia/Dhaka").
    timezone: str | None = Field(default=None, max_length=60)
    priority: TaskPriority = TaskPriority.none
    note_id: uuid.UUID | None = None
    source: TaskSource = TaskSource.manual

    @field_validator("title")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = " ".join(v.strip().split())
        if not v:
            raise ValueError("Title is required")
        return v


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=5000)
    due_date: date | None = None
    due_time: time | None = None
    timezone: str | None = Field(default=None, max_length=60)
    clear_due_date: bool = False
    clear_due_time: bool = False
    priority: TaskPriority | None = None
    status: TaskStatus | None = None


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    note_id: uuid.UUID | None
    title: str
    description: str | None
    due_date: date | None
    due_time: time | None
    timezone: str | None
    priority: TaskPriority
    status: TaskStatus
    source: TaskSource
    external_provider: str | None
    external_task_id: str | None
    calendar_id: str | None
    calendar_event_id: str | None
    calendar_event_url: str | None
    calendar_synced_at: datetime | None
    calendar_error: str | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class TaskBulkCreate(BaseModel):
    tasks: list[TaskCreate] = Field(min_length=1, max_length=50)
