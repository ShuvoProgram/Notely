"""Integration background jobs: health checks, token refresh, sync, webhook processing.

Never run inside an HTTP request. Each job opens its own session and is safe to retry.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy import select

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.base import utcnow
from app.db.session import get_session_factory
from app.integrations.base.errors import ProviderError
from app.integrations.registry import get_provider
from app.models.integration import ConnectionStatus, UserConnection, WebhookEvent
from app.models.user import User
from app.services.connection_service import USABLE, ConnectionService

log = get_logger(__name__)

CHECK_INTERVAL = timedelta(hours=1)


async def check_connections(_: dict[str, Any]) -> int:
    """Test every usable connection not checked recently; flips status on failure."""
    settings = get_settings()
    checked = 0
    async with get_session_factory()() as db:
        service = ConnectionService(db, settings)
        cutoff = utcnow() - CHECK_INTERVAL
        rows = list(
            await db.scalars(
                select(UserConnection).where(
                    UserConnection.status.in_(list(USABLE)),
                    (UserConnection.last_checked_at.is_(None))
                    | (UserConnection.last_checked_at < cutoff),
                )
            )
        )
        for conn in rows:
            user = await db.get(User, conn.user_id)
            if user is None:
                continue
            try:
                await service.test(user, conn)
            except Exception:  # noqa: BLE001
                log.exception("check_connection_failed", extra={"connection_id": str(conn.id)})
            checked += 1
    log.info("check_connections", extra={"checked": checked})
    return checked


async def refresh_oauth_tokens(_: dict[str, Any]) -> int:
    """Proactively refresh OAuth tokens that expire within the leeway window."""
    settings = get_settings()
    refreshed = 0
    async with get_session_factory()() as db:
        service = ConnectionService(db, settings)
        soon = utcnow() + timedelta(minutes=10)
        rows = list(
            await db.scalars(
                select(UserConnection).where(
                    UserConnection.auth_type == "oauth2",
                    UserConnection.status.in_(list(USABLE)),
                    UserConnection.token_expires_at.is_not(None),
                    UserConnection.token_expires_at < soon,
                )
            )
        )
        for conn in rows:
            user = await db.get(User, conn.user_id)
            if user is None:
                continue
            try:
                await service.refresh_if_needed(user, conn)
                refreshed += 1
            except ProviderError:
                pass  # status already updated by the service
    log.info("refresh_oauth_tokens", extra={"refreshed": refreshed})
    return refreshed


async def sync_integration(_: dict[str, Any], connection_id: str) -> int:
    settings = get_settings()
    async with get_session_factory()() as db:
        conn = await db.get(UserConnection, uuid.UUID(connection_id))
        if conn is None or conn.status not in USABLE:
            return 0
        user = await db.get(User, conn.user_id)
        provider = get_provider(conn.provider)
        if user is None or provider is None or not provider.manifest.supports_sync:
            return 0
        service = ConnectionService(db, settings)
        conn.status = ConnectionStatus.syncing
        await db.commit()
        try:
            touched = await provider.sync(service.context(user, conn))
            conn.status = ConnectionStatus.connected
            conn.last_sync_at = utcnow()
            await db.commit()
            return touched
        except ProviderError as exc:
            await service.record_tool_failure(conn, exc)
            if conn.status == ConnectionStatus.syncing:
                conn.status = ConnectionStatus.error
                conn.last_error = exc.user_message()[1]
                await db.commit()
            return 0


async def process_webhook(_: dict[str, Any], event_row_id: str) -> bool:
    """Idempotent: a processed event is never handled twice."""
    settings = get_settings()
    async with get_session_factory()() as db:
        row = await db.get(WebhookEvent, uuid.UUID(event_row_id))
        if row is None or row.status == "processed":
            return False
        provider = get_provider(row.provider)
        if provider is None:
            row.status = "failed"
            row.error = "unknown provider"
            await db.commit()
            return False
        ctx = None
        if row.connection_id is not None:
            conn = await db.get(UserConnection, row.connection_id)
            user = await db.get(User, conn.user_id) if conn else None
            if conn is not None and user is not None:
                ctx = ConnectionService(db, settings).context(user, conn)
        try:
            await provider.handle_webhook(ctx, row.payload)
            row.status = "processed"
            row.processed_at = utcnow()
        except Exception as exc:  # noqa: BLE001
            row.status = "failed"
            row.error = type(exc).__name__
            log.exception("process_webhook_failed", extra={"event": event_row_id})
        await db.commit()
        return row.status == "processed"
