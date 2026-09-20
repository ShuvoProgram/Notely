from __future__ import annotations

import hashlib
import json
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import RedirectResponse

from app.api.deps import CurrentAuth, DbDep, SettingsDep
from app.core import metrics
from app.core.config import get_settings
from app.core.exceptions import APIError, NotFound
from app.core.rate_limit import rate_limit
from app.core.responses import Envelope, ok
from app.db.base import utcnow
from app.integrations.base.provider import IntegrationProvider
from app.integrations.registry import get_provider
from app.models.integration import UserConnection, WebhookEvent
from app.schemas.integrations import (
    ConnectionOut,
    ConnectionTestOut,
    ConnectionUpdate,
    ConnectRequest,
    OAuthStartOut,
    ProviderDetailOut,
    ProviderOut,
    TestStepOut,
)
from app.services.connection_service import ConnectionService, MarketplaceEntry
from app.workers.queue import enqueue

router = APIRouter(prefix="/integrations", tags=["integrations"])
oauth_router = APIRouter(prefix="/oauth", tags=["integrations"])
webhook_router = APIRouter(prefix="/webhooks", tags=["webhooks"])

connect_limit = rate_limit("integrations", 30)
oauth_limit = rate_limit("oauth", lambda s: s.rate_limit_oauth_per_minute, key="ip")
webhook_limit = rate_limit("webhook", lambda s: s.rate_limit_webhook_per_minute, key="provider")


def get_connection_service(db: DbDep, settings: SettingsDep) -> ConnectionService:
    return ConnectionService(db, settings)


ServiceDep = Annotated[ConnectionService, Depends(get_connection_service)]


def connection_out(conn: UserConnection | None) -> ConnectionOut | None:
    return ConnectionOut.model_validate(conn) if conn else None


def provider_out(entry: MarketplaceEntry) -> ProviderOut:
    m = entry.provider.manifest
    return ProviderOut(
        id=m.id,
        name=m.name,
        category=m.category,
        description=m.description,
        logo_url=m.logo_url,
        docs_url=m.docs_url,
        auth=m.auth.value,
        capabilities=[c.value for c in m.capabilities],
        permissions=m.permissions,
        config_fields=m.config_fields,
        token_auth=m.token_auth,
        connect_methods=entry.provider.connect_methods(get_settings()),
        supports_webhooks=m.supports_webhooks,
        supports_sync=m.supports_sync,
        configured=entry.configured,
        connection=connection_out(entry.connection),
    )


# --- marketplace --------------------------------------------------------------------------------


@router.get("/providers", response_model=Envelope[list[ProviderOut]])
async def list_providers(ctx: CurrentAuth, service: ServiceDep) -> dict[str, Any]:
    return ok([provider_out(e) for e in await service.marketplace(ctx.user)])


@router.get("/providers/{provider_id}", response_model=Envelope[ProviderDetailOut])
async def provider_detail(
    provider_id: str, ctx: CurrentAuth, service: ServiceDep
) -> dict[str, Any]:
    entry = next(
        (e for e in await service.marketplace(ctx.user) if e.provider.manifest.id == provider_id),
        None,
    )
    if entry is None:
        raise NotFound("Unknown integration.")
    base = provider_out(entry).model_dump()
    count = await service.local_item_count(entry.connection) if entry.connection else 0
    tools = entry.connection.metadata_.get("tools", []) if entry.connection else []
    return ok(
        ProviderDetailOut(
            **base, local_item_count=count, tools=tools if isinstance(tools, list) else []
        )
    )


@router.post(
    "/providers/{provider_id}/connect",
    status_code=status.HTTP_201_CREATED,
    response_model=Envelope[ConnectionOut],
    dependencies=[Depends(connect_limit)],
)
async def connect_provider(
    provider_id: str, payload: ConnectRequest, ctx: CurrentAuth, service: ServiceDep
) -> dict[str, Any]:
    """Connect a token/config-based provider (OAuth providers use /oauth/{provider}/start)."""
    conn = await service.connect_with_config(
        ctx.user, provider_id, config=payload.config, token=payload.token
    )
    return ok(connection_out(conn))


# --- connections --------------------------------------------------------------------------------


@router.get("/connections", response_model=Envelope[list[ConnectionOut]])
async def list_connections(ctx: CurrentAuth, service: ServiceDep) -> dict[str, Any]:
    entries = await service.marketplace(ctx.user)
    return ok([connection_out(e.connection) for e in entries if e.connection is not None])


@router.get("/connections/{connection_id}", response_model=Envelope[ConnectionOut])
async def get_connection(
    connection_id: uuid.UUID, ctx: CurrentAuth, service: ServiceDep
) -> dict[str, Any]:
    return ok(connection_out(await service.get_connection(ctx.user, connection_id)))


@router.patch("/connections/{connection_id}", response_model=Envelope[ConnectionOut])
async def update_connection(
    connection_id: uuid.UUID, payload: ConnectionUpdate, ctx: CurrentAuth, service: ServiceDep
) -> dict[str, Any]:
    conn = await service.get_connection(ctx.user, connection_id)
    return ok(connection_out(await service.update_config(ctx.user, conn, config=payload.config)))


@router.post(
    "/connections/{connection_id}/test",
    response_model=Envelope[ConnectionTestOut],
    dependencies=[Depends(connect_limit)],
)
async def test_connection(
    connection_id: uuid.UUID, ctx: CurrentAuth, service: ServiceDep
) -> dict[str, Any]:
    conn = await service.get_connection(ctx.user, connection_id)
    result = await service.test(ctx.user, conn)
    return ok(
        ConnectionTestOut(
            healthy=result.healthy,
            steps=[TestStepOut(name=s.name, ok=s.ok, detail=s.detail) for s in result.steps],
            connection=ConnectionOut.model_validate(conn),
        )
    )


@router.delete("/connections/{connection_id}", response_model=Envelope[ConnectionOut])
async def disconnect(
    connection_id: uuid.UUID,
    ctx: CurrentAuth,
    service: ServiceDep,
    purge: Annotated[bool, Query(description="Also delete locally indexed provider data")] = False,
) -> dict[str, Any]:
    conn = await service.get_connection(ctx.user, connection_id)
    await service.disconnect(ctx.user, conn, purge_data=purge)
    return ok(connection_out(conn))


# --- provider OAuth -----------------------------------------------------------------------------


@oauth_router.get(
    "/{provider_id}/start", dependencies=[Depends(connect_limit), Depends(oauth_limit)]
)
async def oauth_start(
    provider_id: str,
    ctx: CurrentAuth,
    service: ServiceDep,
    scopes: Annotated[str | None, Query(description="Comma-separated optional scopes")] = None,
) -> RedirectResponse:
    selected = [s for s in (scopes or "").replace(" ", ",").split(",") if s]
    url = await service.start_oauth(ctx.user, provider_id, selected_scopes=selected)
    return RedirectResponse(url, status_code=status.HTTP_302_FOUND)


@oauth_router.get("/{provider_id}/start-url", response_model=Envelope[OAuthStartOut])
async def oauth_start_url(
    provider_id: str,
    ctx: CurrentAuth,
    service: ServiceDep,
    scopes: Annotated[str | None, Query()] = None,
) -> dict[str, Any]:
    """Same as /start but returns the URL (for clients that want to navigate themselves)."""
    selected = [s for s in (scopes or "").replace(" ", ",").split(",") if s]
    return ok(
        OAuthStartOut(
            authorize_url=await service.start_oauth(ctx.user, provider_id, selected_scopes=selected)
        )
    )


@oauth_router.get(
    "/{provider_id}/callback", dependencies=[Depends(connect_limit), Depends(oauth_limit)]
)
async def oauth_callback(
    provider_id: str,
    ctx: CurrentAuth,
    service: ServiceDep,
    settings: SettingsDep,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    target = f"{settings.frontend_origin}/app/settings/connections/{provider_id}"
    try:
        await service.complete_oauth(ctx.user, provider_id, code=code, state=state, error=error)
    except APIError as exc:
        return RedirectResponse(f"{target}?error={exc.code}", status_code=status.HTTP_302_FOUND)
    return RedirectResponse(f"{target}?connected=1", status_code=status.HTTP_302_FOUND)


# --- webhooks -----------------------------------------------------------------------------------


@webhook_router.post(
    "/{provider_id}", status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(webhook_limit)]
)
async def receive_webhook(
    provider_id: str, request: Request, db: DbDep, settings: SettingsDep
) -> dict[str, Any]:
    """Verify signature, store each event once (idempotent), hand off to the worker."""
    provider: IntegrationProvider | None = get_provider(provider_id)
    if provider is None or not provider.manifest.supports_webhooks:
        metrics.webhooks.labels(provider_id, "unknown").inc()
        raise NotFound("Unknown webhook endpoint.")
    body = await request.body()
    verification = provider.verify_webhook(headers=request.headers, body=body, settings=settings)
    if not verification.ok:
        metrics.webhooks.labels(provider_id, "rejected").inc()
        raise APIError("Webhook signature rejected.", code="WEBHOOK_REJECTED", status_code=401)
    metrics.webhooks.labels(provider_id, "accepted").inc()
    digest = hashlib.sha256(body).hexdigest()
    accepted = 0
    duplicates = 0
    for event in verification.events:
        event_id = str(event.get("id") or "")
        if not event_id:
            continue
        from sqlalchemy import select

        exists = await db.scalar(
            select(WebhookEvent.id).where(
                WebhookEvent.provider == provider_id, WebhookEvent.event_id == event_id
            )
        )
        if exists is not None:
            duplicates += 1
            continue
        row = WebhookEvent(
            provider=provider_id,
            event_id=event_id,
            event_type=str(event.get("type") or "") or None,
            payload_hash=digest,
            payload=json.loads(json.dumps(event, default=str)),
            received_at=utcnow(),
        )
        db.add(row)
        await db.flush()
        await enqueue("process_webhook", str(row.id))
        accepted += 1
    await db.commit()
    return {"accepted": accepted, "duplicates": duplicates}
