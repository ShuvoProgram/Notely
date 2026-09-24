from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

from app.models.ai import ApprovalStatus, MessageRole, RiskLevel, RunStatus, ToolCallStatus


class ChatRequest(BaseModel):
    # Omitted only when retrying: the last user message of `thread_id` is answered again.
    message: str | None = Field(default=None, min_length=1, max_length=8000)
    thread_id: uuid.UUID | None = None
    note_id: uuid.UUID | None = None
    retry: bool = False

    @model_validator(mode="after")
    def _message_or_retry(self) -> ChatRequest:
        if self.retry and self.thread_id is None:
            raise ValueError("retry needs a thread_id")
        if not self.retry and not (self.message and self.message.strip()):
            raise ValueError("message is required")
        return self


class ThreadCreate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    note_id: uuid.UUID | None = None


class ThreadUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    archived: bool | None = None


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
    last_activity_at: datetime
    archived_at: datetime | None = None
    # List-only extras (see AIThreadService.list_threads).
    last_message: str | None = None
    last_message_role: MessageRole | None = None
    active_run_id: uuid.UUID | None = None
    active_run_status: RunStatus | None = None


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

    @computed_field  # type: ignore[prop-decorator]
    @property
    def error_message(self) -> str | None:
        """Why the run failed or stopped, readable by the user (`error` may be a short code)."""
        return describe_run_error(self.error)


def describe_run_error(error: str | None) -> str | None:
    if not error:
        return None
    known = {
        "interrupted": "The assistant was interrupted before it finished. Please try again.",
        "superseded": "Replaced by a newer message.",
        "internal": "The assistant ran into a problem. Please try again.",
    }
    if error in known:
        return known[error]
    if " " in error:
        return error  # already a readable reason (see runner.failure_message)
    # Older runs stored only the exception class name.
    if "ratelimit" in error.lower() or "resourceexhausted" in error.lower():
        return "The AI provider was rate-limiting requests. Wait a minute and retry."
    return "The assistant ran into a problem. Please try again."


class ThreadDetailOut(BaseModel):
    thread: ThreadOut
    messages: list[MessageOut]
    active_run: RunOut | None
    # The most recent run, finished or not: lets a reloaded client show that the last request
    # failed or was stopped (and offer a retry) when no answer follows it.
    last_run: RunOut | None = None


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
    supports_tools: bool | None = None


class UserModelIn(BaseModel):
    provider: str = Field(max_length=40)
    model: str = Field(min_length=1, max_length=120)
    base_url: str | None = Field(default=None, max_length=500)
    # Write-only. Omit (or send empty) to keep the stored key.
    api_key: str | None = Field(default=None, max_length=500)
    enabled: bool = True
    # Test the draft before storing it (default). Only the workspace test-suite turns this off.
    verify: bool = True


class ModelDraftIn(BaseModel):
    """A configuration to try without saving. Empty api_key = the stored key for the provider."""

    provider: str = Field(max_length=40)
    model: str = Field(min_length=1, max_length=120)
    base_url: str | None = Field(default=None, max_length=500)
    api_key: str | None = Field(default=None, max_length=500)


class ModelListIn(BaseModel):
    provider: str = Field(max_length=40)
    # Write-only; empty means "use the key stored for this provider".
    api_key: str | None = Field(default=None, max_length=500)
    base_url: str | None = Field(default=None, max_length=500)


class ModelInfo(BaseModel):
    id: str
    name: str
    tier: str = "balanced"
    context: int | None = None
    price: str = "unknown"
    status: str = "current"
    tools: bool = True
    note: str = ""


class ModelListOut(BaseModel):
    models: list[ModelInfo]


class ModelTestOut(BaseModel):
    ok: bool
    detail: str
    latency_ms: int | None
    supports_tools: bool | None = None


class AISettingsOut(BaseModel):
    provider: str
    models: list[dict[str, str]]
    preferences: AIPreferences
    tools: list[dict[str, Any]]
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
