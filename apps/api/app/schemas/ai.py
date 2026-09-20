from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.ai import ApprovalStatus, MessageRole, RiskLevel, RunStatus, ToolCallStatus


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    thread_id: uuid.UUID | None = None
    note_id: uuid.UUID | None = None


class ApproveRequest(BaseModel):
    run_id: uuid.UUID
    approval_id: uuid.UUID
    approved_call_ids: list[str] = Field(default_factory=list, max_length=50)
    reject_all: bool = False


class ThreadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    note_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: MessageRole
    content: str
    sources: list[dict[str, Any]] | None
    run_id: uuid.UUID | None
    created_at: datetime


class ToolCallOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    call_id: str
    tool_name: str
    provider: str
    risk_level: RiskLevel
    arguments: dict[str, Any]
    status: ToolCallStatus
    error: str | None
    verification: dict[str, Any] | None = None
    executed_at: datetime | None


class ApprovalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: ApprovalStatus
    tool_call_ids: list[str]
    created_at: datetime
    decided_at: datetime | None


class RunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    thread_id: uuid.UUID
    status: RunStatus
    model: str | None
    provider: str | None
    token_usage: dict[str, Any]
    steps: list[dict[str, Any]]
    plan: dict[str, Any] | None = None
    sources: list[dict[str, Any]] = Field(default_factory=list)
    error: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    tool_calls: list[ToolCallOut] = Field(default_factory=list)
    approvals: list[ApprovalOut] = Field(default_factory=list)


class ThreadDetailOut(BaseModel):
    thread: ThreadOut
    messages: list[MessageOut]
    active_run: RunOut | None


class AIPreferences(BaseModel):
    model: str | None = None
    summary_length: Literal["short", "medium", "long"] = "medium"
    confirm_reads: bool = False


class UserModelOut(BaseModel):
    """The user's own model configuration. The key itself is never included."""

    provider: str
    model: str
    base_url: str | None
    key_hint: str
    enabled: bool
    verified_at: datetime | None
    last_error: str | None


class UserModelIn(BaseModel):
    provider: str = Field(max_length=40)
    model: str = Field(min_length=1, max_length=120)
    base_url: str | None = Field(default=None, max_length=500)
    # Write-only. Omit (or send empty) to keep the stored key.
    api_key: str | None = Field(default=None, max_length=500)
    enabled: bool = True


class ModelTestOut(BaseModel):
    ok: bool
    detail: str
    latency_ms: int | None


class AISettingsOut(BaseModel):
    provider: str
    models: list[dict[str, str]]
    preferences: AIPreferences
    tools: list[dict[str, str]]
    # Bring your own key
    user_model: UserModelOut | None = None
    user_model_providers: list[dict[str, Any]] = Field(default_factory=list)
    encryption_available: bool = True


class AuditEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    provider: str
    action: str
    tool_name: str | None
    risk_level: RiskLevel
    status: str
    run_id: uuid.UUID | None
    request_metadata: dict[str, Any]
    created_at: datetime
