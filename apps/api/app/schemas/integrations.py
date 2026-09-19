from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.integrations.base.provider import ConfigField, PermissionSpec
from app.models.integration import ConnectionStatus


class ConnectionOut(BaseModel):
    """Public view of a connection. Never includes credentials."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    provider: str
    auth_type: str
    status: ConnectionStatus
    external_account_id: str | None
    external_account_name: str | None
    scopes: list[str]
    config: dict[str, Any]
    metadata: dict[str, Any] = Field(default_factory=dict, validation_alias="metadata_")
    token_expires_at: datetime | None
    last_sync_at: datetime | None
    last_checked_at: datetime | None
    last_error: str | None
    last_error_code: str | None
    created_at: datetime
    updated_at: datetime


class ProviderOut(BaseModel):
    id: str
    name: str
    category: str
    description: str
    logo_url: str | None
    docs_url: str | None
    auth: str
    capabilities: list[str]
    permissions: list[PermissionSpec]
    config_fields: list[ConfigField]
    supports_webhooks: bool
    supports_sync: bool
    configured: bool
    connection: ConnectionOut | None


class ProviderDetailOut(ProviderOut):
    local_item_count: int = 0
    tools: list[dict[str, Any]] = Field(default_factory=list)


class ConnectRequest(BaseModel):
    config: dict[str, Any] = Field(default_factory=dict)
    token: str | None = Field(default=None, max_length=4096)


class ConnectionUpdate(BaseModel):
    config: dict[str, Any] | None = None


class TestStepOut(BaseModel):
    name: str
    ok: bool
    detail: str = ""


class ConnectionTestOut(BaseModel):
    healthy: bool
    steps: list[TestStepOut]
    connection: ConnectionOut


class OAuthStartOut(BaseModel):
    authorize_url: str
