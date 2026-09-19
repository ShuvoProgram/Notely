from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, Enum, ForeignKey, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import (
    Base,
    JSONType,
    TenantScopedMixin,
    TimestampMixin,
    TZDateTime,
    UUIDPrimaryKeyMixin,
)


class ConnectionStatus(enum.StrEnum):
    pending = "pending"
    connecting = "connecting"
    connected = "connected"
    syncing = "syncing"
    needs_attention = "needs_attention"
    expired = "expired"
    error = "error"
    disconnected = "disconnected"


class Integration(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Catalog row per provider. Metadata comes from the code manifest; `enabled` is operational."""

    __tablename__ = "integrations"

    provider: Mapped[str] = mapped_column(String(60), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    category: Mapped[str] = mapped_column(String(60), nullable=False)
    logo_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class UserConnection(UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin, Base):
    """A user's link to one provider. Credentials are stored encrypted, never in plaintext."""

    __tablename__ = "user_connections"
    __table_args__ = (
        UniqueConstraint("user_id", "provider", name="uq_user_connections_user_provider"),
    )

    integration_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("integrations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    auth_type: Mapped[str] = mapped_column(String(20), nullable=False)  # oauth2 | token | none
    external_account_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    external_account_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[ConnectionStatus] = mapped_column(
        Enum(ConnectionStatus, name="connection_status"),
        nullable=False,
        default=ConnectionStatus.pending,
        index=True,
    )
    access_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    refresh_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_expires_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)
    scopes: Mapped[list[str]] = mapped_column(JSONType, nullable=False, default=list)
    # Provider-specific, non-secret configuration (server URL, selected channels, ...).
    config: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONType, nullable=False, default=dict
    )
    last_sync_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(60), nullable=True)
    disconnected_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)

    @property
    def is_usable(self) -> bool:
        return self.status in (ConnectionStatus.connected, ConnectionStatus.syncing)


class ExternalItem(UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin, Base):
    """Notely's cached/indexed representation of a provider object (never the source of truth)."""

    __tablename__ = "external_items"
    __table_args__ = (
        UniqueConstraint(
            "connection_id", "external_id", name="uq_external_items_connection_external"
        ),
    )

    connection_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("user_connections.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(60), nullable=False)  # message, page, task, file, ...
    title: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    content_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONType, nullable=False, default=dict
    )
    source_updated_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)
    indexed_at: Mapped[datetime] = mapped_column(TZDateTime(), nullable=False)


class WebhookEvent(UUIDPrimaryKeyMixin, Base):
    """Inbound provider webhook, stored before processing so handling is idempotent."""

    __tablename__ = "webhook_events"
    __table_args__ = (
        UniqueConstraint("provider", "event_id", name="uq_webhook_events_provider_event"),
    )

    provider: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    event_id: Mapped[str] = mapped_column(String(255), nullable=False)
    event_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    connection_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="received", index=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    received_at: Mapped[datetime] = mapped_column(TZDateTime(), nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)
