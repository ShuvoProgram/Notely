from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.automation.model import Workflow

ScheduleKind = Literal["once", "daily", "weekly", "monthly", "custom", "interval", "manual"]


class AutomationIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=500)
    workflow: dict[str, Any]
    schedule_kind: ScheduleKind = "daily"
    schedule_config: dict[str, Any] = Field(default_factory=dict)
    timezone: str = Field(default="UTC", min_length=1, max_length=60)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    enabled: bool = False

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("Give the automation a name.")
        return value

    @field_validator("workflow")
    @classmethod
    def _workflow(cls, value: dict[str, Any]) -> dict[str, Any]:
        return Workflow.model_validate(value).model_dump()

    @model_validator(mode="after")
    def _dates(self) -> AutomationIn:
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            raise ValueError("The end date must be after the start date.")
        return self


class IssueOut(BaseModel):
    message: str
    step_id: str | None = None
    field: str | None = None
    kind: str = "fix"
    app: str | None = None
    fix_path: str | None = None


class LastRunOut(BaseModel):
    id: uuid.UUID
    status: str
    run_mode: str
    summary: str | None = None
    error: str | None = None
    started_at: datetime
    finished_at: datetime | None = None


class AutomationOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    workflow: dict[str, Any]
    schedule_kind: str
    schedule_config: dict[str, Any]
    timezone: str
    starts_at: datetime | None
    ends_at: datetime | None
    next_run_at: datetime | None
    enabled: bool
    status: str
    consecutive_failures: int
    created_at: datetime
    updated_at: datetime
    apps: list[str] = Field(default_factory=list)
    last_run: LastRunOut | None = None
    running: bool = False
    pending_approvals: int = 0
    issues: list[IssueOut] = Field(default_factory=list)


class ExecutionStepOut(BaseModel):
    step_id: str
    position: int
    kind: str
    name: str | None
    status: str
    summary: str | None
    error: str | None
    input: dict[str, Any]
    output: Any
    details: dict[str, Any]
    attempts: int
    started_at: datetime | None
    finished_at: datetime | None


class ApprovalOut(BaseModel):
    id: uuid.UUID
    execution_id: uuid.UUID
    step_id: str
    status: str
    proposal: dict[str, Any]
    decided_at: datetime | None


class ExecutionOut(BaseModel):
    id: uuid.UUID
    status: str
    run_mode: str
    summary: str | None = None
    error: str | None = None
    occurrence_at: datetime
    started_at: datetime
    finished_at: datetime | None = None
    trigger: dict[str, Any] = Field(default_factory=dict)


class ExecutionDetailOut(ExecutionOut):
    steps: list[ExecutionStepOut] = Field(default_factory=list)
    approvals: list[ApprovalOut] = Field(default_factory=list)


class RunRequest(BaseModel):
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=100)


class TestRequest(BaseModel):
    step_id: str | None = Field(default=None, max_length=64)


class EnabledRequest(BaseModel):
    enabled: bool


class ApprovalDecision(BaseModel):
    approved: bool


class ValidateRequest(BaseModel):
    workflow: dict[str, Any]


class ValidateOut(BaseModel):
    valid: bool
    issues: list[IssueOut]
    error: str | None = None


class TemplateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=500)


class TemplateOut(BaseModel):
    id: str
    name: str
    description: str | None
    builtin: bool
    apps: list[str]
    workflow: dict[str, Any]
    schedule_kind: str
    schedule_config: dict[str, Any]
    available: bool
    missing_apps: list[str] = Field(default_factory=list)
    prompt: str | None = None


class DraftCurrent(BaseModel):
    name: str | None = Field(default=None, max_length=160)
    workflow: dict[str, Any]
    schedule_kind: ScheduleKind | None = None
    schedule_config: dict[str, Any] = Field(default_factory=dict)
    timezone: str | None = Field(default=None, max_length=60)


class DraftRequest(BaseModel):
    prompt: str = Field(min_length=3, max_length=4_000)
    timezone: str | None = Field(default=None, max_length=60)
    # When set, the AI changes this automation instead of creating a new one.
    current: DraftCurrent | None = None


class MissingApp(BaseModel):
    app: str
    name: str
    connect_path: str


class Unsupported(BaseModel):
    request: str
    reason: str
    suggestion: str | None = None


class DraftOut(BaseModel):
    name: str | None = None
    description: str | None = None
    workflow: dict[str, Any] | None = None
    schedule_kind: ScheduleKind | None = None
    schedule_config: dict[str, Any] = Field(default_factory=dict)
    timezone: str | None = None
    starts_at: datetime | None = None
    questions: list[str] = Field(default_factory=list)
    missing_apps: list[MissingApp] = Field(default_factory=list)
    unsupported: list[Unsupported] = Field(default_factory=list)
    changes: list[str] = Field(default_factory=list)
    issues: list[IssueOut] = Field(default_factory=list)
