"""Admin API (/api/v1/admin). Every route depends on a permission from app.api.admin_deps, so
authorization is enforced here on the server whatever the UI shows. Responses are marked
no-store; changes are rate limited separately and audited in the same transaction."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.admin_deps import (
    AdminManagePlatform,
    AdminManageRoles,
    AdminManageUsers,
    AdminRead,
    admin_read_limit,
    admin_write_limit,
)
from app.api.deps import DbDep, SettingsDep
from app.core.exceptions import NotFound
from app.core.permissions import ROLE_PERMISSIONS
from app.core.responses import Envelope, ok
from app.integrations.registry import get_providers
from app.models.integration import Integration
from app.models.user import PlatformRole
from app.services.admin_analytics import AdminAnalytics
from app.services.admin_audit import AdminAuditService
from app.services.admin_users import AdminUserService
from app.services.platform_settings import SPECS, PlatformSettings


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store, private"


router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(_no_store), Depends(admin_read_limit)],
)
write = [Depends(admin_write_limit)]

Days = Annotated[int, Query(ge=1, le=365)]
Page = Annotated[int, Query(ge=1, le=10_000)]
PageSize = Annotated[int, Query(ge=1, le=100)]
EnvelopeAny = Envelope[dict[str, Any]]


def _paged(result: dict[str, Any], page: int, page_size: int) -> dict[str, Any]:
    items, total = result.pop("items"), result.pop("total")
    return ok(items, {"total": total, "page": page, "page_size": page_size, **result})


def _day_start(d: date | None) -> datetime | None:
    return datetime.combine(d, time.min, UTC) if d else None


def _day_end(d: date | None) -> datetime | None:
    return datetime.combine(d, time.min, UTC) + timedelta(days=1) if d else None


# --- session ------------------------------------------------------------------------------------


@router.get("/me", response_model=EnvelopeAny)
async def me(admin: AdminRead, settings: SettingsDep) -> dict[str, Any]:
    expires = admin.session.created_at + timedelta(hours=settings.admin_session_max_age_hours)
    return ok(
        {
            "id": str(admin.user.id),
            "email": admin.user.email,
            "display_name": admin.user.display_name,
            "role": admin.role,
            "permissions": sorted(p.value for p in admin.permissions),
            "admin_session_expires_at": expires,
            "two_factor_enabled": admin.user.totp_secret_encrypted is not None,
        }
    )


# --- overview -----------------------------------------------------------------------------------


@router.get("/overview", response_model=EnvelopeAny)
async def overview(
    _: AdminRead, db: DbDep, settings: SettingsDep, days: Days = 30
) -> dict[str, Any]:
    return ok(await AdminAnalytics(db, settings).overview(days))


@router.get("/events", response_model=Envelope[list[dict[str, Any]]])
async def events(
    _: AdminRead,
    db: DbDep,
    settings: SettingsDep,
    category: Literal["error", "security", "usage"] | None = None,
    kind: Annotated[str | None, Query(max_length=60)] = None,
    user_id: uuid.UUID | None = None,
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
    page: Page = 1,
    page_size: PageSize = 50,
) -> dict[str, Any]:
    result = await AdminAnalytics(db, settings).events(
        category=category,
        kind=kind,
        user_id=user_id,
        since=_day_start(date_from),
        until=_day_end(date_to),
        page=page,
        page_size=page_size,
    )
    return _paged(result, page, page_size)


# --- users --------------------------------------------------------------------------------------


class SuspendRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)
    revoke_sessions: bool = True


class RoleRequest(BaseModel):
    role: PlatformRole


@router.get("/users", response_model=Envelope[list[dict[str, Any]]])
async def list_users(
    _: AdminRead,
    db: DbDep,
    settings: SettingsDep,
    q: Annotated[str | None, Query(max_length=200)] = None,
    status: Literal["active", "suspended"] | None = None,
    role: Literal["user", "viewer", "support", "admin", "staff"] | None = None,
    activity: Literal["active_7d", "active_30d", "dormant", "new_7d"] | None = None,
    sort: Literal["created_desc", "created_asc", "active_desc", "email"] = "created_desc",
    page: Page = 1,
    page_size: PageSize = 25,
) -> dict[str, Any]:
    result = await AdminAnalytics(db, settings).list_users(
        q=q,
        status=status,
        role=role,
        activity=activity,
        sort=sort,
        page=page,
        page_size=page_size,
    )
    return _paged(result, page, page_size)


@router.get("/users/{user_id}", response_model=EnvelopeAny)
async def user_detail(
    user_id: uuid.UUID, admin: AdminRead, db: DbDep, settings: SettingsDep
) -> dict[str, Any]:
    target = await AdminUserService(db).get(user_id)
    detail = await AdminAnalytics(db, settings).user_detail(target)
    return ok(detail)


@router.post("/users/{user_id}/suspend", response_model=EnvelopeAny, dependencies=write)
async def suspend_user(
    user_id: uuid.UUID,
    payload: SuspendRequest,
    request: Request,
    admin: AdminManageUsers,
    db: DbDep,
) -> dict[str, Any]:
    service = AdminUserService(db)
    target = await service.suspend(
        admin.user,
        await service.get(user_id),
        reason=payload.reason.strip(),
        revoke_sessions=payload.revoke_sessions,
        request=request,
    )
    return ok({"id": str(target.id), "is_active": target.is_active})


@router.post("/users/{user_id}/reactivate", response_model=EnvelopeAny, dependencies=write)
async def reactivate_user(
    user_id: uuid.UUID, request: Request, admin: AdminManageUsers, db: DbDep
) -> dict[str, Any]:
    service = AdminUserService(db)
    target = await service.reactivate(admin.user, await service.get(user_id), request=request)
    return ok({"id": str(target.id), "is_active": target.is_active})


@router.post("/users/{user_id}/sessions/revoke", response_model=EnvelopeAny, dependencies=write)
async def revoke_user_sessions(
    user_id: uuid.UUID, request: Request, admin: AdminManageUsers, db: DbDep
) -> dict[str, Any]:
    service = AdminUserService(db)
    count = await service.revoke_sessions(admin.user, await service.get(user_id), request=request)
    return ok({"revoked": count})


@router.patch("/users/{user_id}/role", response_model=EnvelopeAny, dependencies=write)
async def change_role(
    user_id: uuid.UUID,
    payload: RoleRequest,
    request: Request,
    admin: AdminManageRoles,
    db: DbDep,
) -> dict[str, Any]:
    service = AdminUserService(db)
    target = await service.change_role(
        admin.user, await service.get(user_id), role=payload.role.value, request=request
    )
    return ok({"id": str(target.id), "role": target.role})


# --- automations --------------------------------------------------------------------------------


@router.get("/automations/summary", response_model=EnvelopeAny)
async def automation_summary(
    _: AdminRead, db: DbDep, settings: SettingsDep, days: Days = 30
) -> dict[str, Any]:
    return ok(await AdminAnalytics(db, settings).automation_summary(days))


@router.get("/automations/executions", response_model=Envelope[list[dict[str, Any]]])
async def list_executions(
    _: AdminRead,
    db: DbDep,
    settings: SettingsDep,
    status: Literal[
        "succeeded",
        "completed",
        "stopped",
        "failed",
        "running",
        "queued",
        "waiting_for_approval",
        "skipped",
    ]
    | None = None,
    user_id: uuid.UUID | None = None,
    automation_id: uuid.UUID | None = None,
    connector: Annotated[str | None, Query(max_length=60, pattern=r"^[a-z0-9_]+$")] = None,
    error_type: Annotated[str | None, Query(max_length=40, pattern=r"^[a-z_]+$")] = None,
    run_mode: Literal["scheduled", "manual", "test", "event"] | None = None,
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
    page: Page = 1,
    page_size: PageSize = 25,
) -> dict[str, Any]:
    result = await AdminAnalytics(db, settings).list_executions(
        status=status,
        user_id=user_id,
        automation_id=automation_id,
        connector=connector,
        error_type=error_type,
        run_mode=run_mode,
        since=_day_start(date_from),
        until=_day_end(date_to),
        page=page,
        page_size=page_size,
    )
    return _paged(result, page, page_size)


@router.get("/automations/executions/{execution_id}", response_model=EnvelopeAny)
async def execution_detail(
    execution_id: uuid.UUID, _: AdminRead, db: DbDep, settings: SettingsDep
) -> dict[str, Any]:
    detail = await AdminAnalytics(db, settings).execution_detail(execution_id)
    if detail is None:
        raise NotFound("No execution with that id.")
    return ok(detail)


# --- connectors ---------------------------------------------------------------------------------


class ConnectorUpdate(BaseModel):
    enabled: bool


@router.get("/connectors", response_model=Envelope[list[dict[str, Any]]])
async def connectors(
    _: AdminRead, db: DbDep, settings: SettingsDep, days: Days = 30
) -> dict[str, Any]:
    result = await AdminAnalytics(db, settings).connectors(days)
    return ok(result["items"], {"window": result["window"]})


@router.get("/connectors/{provider_id}", response_model=EnvelopeAny)
async def connector_detail(
    provider_id: str, _: AdminRead, db: DbDep, settings: SettingsDep, days: Days = 30
) -> dict[str, Any]:
    if len(provider_id) > 60:
        raise NotFound("Unknown connector.")
    return ok(await AdminAnalytics(db, settings).connector_detail(provider_id, days))


@router.patch("/connectors/{provider_id}", response_model=EnvelopeAny, dependencies=write)
async def update_connector(
    provider_id: str,
    payload: ConnectorUpdate,
    request: Request,
    admin: AdminManagePlatform,
    db: DbDep,
    settings: SettingsDep,
) -> dict[str, Any]:
    if provider_id not in get_providers():
        raise NotFound("Unknown connector.")
    row = await db.scalar(select(Integration).where(Integration.provider == provider_id))
    if row is None:  # the catalog is seeded at startup; seed it now if that was skipped
        from app.services.connection_service import ConnectionService

        await ConnectionService(db, settings).ensure_catalog()
        row = await db.scalar(select(Integration).where(Integration.provider == provider_id))
    if row is None:
        raise NotFound("Unknown connector.")
    if row.enabled != payload.enabled:
        row.enabled = payload.enabled
        AdminAuditService(db).add(
            actor=admin.user,
            action="connector.enable" if payload.enabled else "connector.disable",
            request=request,
            resource_type="connector",
            resource_id=provider_id,
            resource_label=row.name,
            metadata={"enabled": payload.enabled},
        )
        await db.commit()
    return ok({"provider": provider_id, "enabled": row.enabled})


# --- AI -----------------------------------------------------------------------------------------


@router.get("/ai", response_model=EnvelopeAny)
async def ai_usage(
    _: AdminRead, db: DbDep, settings: SettingsDep, days: Days = 30
) -> dict[str, Any]:
    return ok(await AdminAnalytics(db, settings).ai(days))


# --- audit --------------------------------------------------------------------------------------


@router.get("/audit", response_model=Envelope[list[dict[str, Any]]])
async def audit_log(
    _: AdminRead,
    db: DbDep,
    settings: SettingsDep,
    action: Annotated[str | None, Query(max_length=80, pattern=r"^[a-z_.]+$")] = None,
    actor_id: uuid.UUID | None = None,
    resource_id: Annotated[str | None, Query(max_length=80)] = None,
    result: Literal["success", "denied", "failed"] | None = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
    page: Page = 1,
    page_size: PageSize = 50,
) -> dict[str, Any]:
    data = await AdminAnalytics(db, settings).audit(
        action=action,
        actor_id=actor_id,
        resource_id=resource_id,
        result=result,
        q=q,
        since=_day_start(date_from),
        until=_day_end(date_to),
        page=page,
        page_size=page_size,
    )
    return _paged(data, page, page_size)


# --- settings -----------------------------------------------------------------------------------


class SettingsUpdate(BaseModel):
    changes: dict[str, Any] = Field(min_length=1, max_length=len(SPECS))


def _settings_payload(values: dict[str, Any], rows: list[Any], settings: Any) -> dict[str, Any]:
    meta = {r.key: r for r in rows}
    from app.services.sign_in_providers import enabled_sign_in_providers

    providers = get_providers()
    return {
        "settings": [
            {
                "key": spec.key,
                "label": spec.label,
                "description": spec.description,
                "kind": spec.kind,
                "group": spec.group,
                "value": values[spec.key],
                "default": spec.default,
                "minimum": spec.minimum,
                "maximum": spec.maximum,
                "max_length": spec.max_length,
                "nullable": spec.nullable,
                "updated_at": meta[spec.key].updated_at if spec.key in meta else None,
            }
            for spec in SPECS.values()
        ],
        # Read-only facts from the environment. Booleans and public names only: no keys,
        # secrets, connection strings or internal hostnames.
        "environment": {
            "environment": settings.environment,
            "ai": {
                "provider": settings.ai_provider,
                "default_model": settings.ai_model_default,
                "fast_model": settings.ai_model_fast,
                "gateway_key_configured": bool(settings.litellm_api_key),
                "max_tool_iterations": settings.ai_max_tool_iterations,
                "request_timeout_seconds": settings.ai_request_timeout_seconds,
            },
            "email": {
                "configured": bool(settings.smtp_host and settings.smtp_from),
                "from_address": settings.smtp_from or None,
            },
            "sign_in_providers": [p.id.value for p in enabled_sign_in_providers(settings)],
            "connectors_configured": sum(
                1 for p in providers.values() if p.is_configured(settings)
            ),
            "connectors_total": len(providers),
            "security": {
                "admin_session_max_age_hours": settings.admin_session_max_age_hours,
                "admin_require_2fa": settings.admin_require_2fa,
                "session_ttl_hours": settings.session_ttl_seconds // 3600,
                "rate_limit_auth_per_minute": settings.rate_limit_auth_per_minute,
                "rate_limit_ai_per_minute": settings.rate_limit_ai_per_minute,
                "encryption_configured": bool(settings.encryption_key),
            },
        },
        "roles": {role: sorted(p.value for p in perms) for role, perms in ROLE_PERMISSIONS.items()},
    }


@router.get("/settings", response_model=EnvelopeAny)
async def get_settings_view(_: AdminRead, db: DbDep, settings: SettingsDep) -> dict[str, Any]:
    service = PlatformSettings(db)
    return ok(_settings_payload(await service.values(fresh=True), await service.rows(), settings))


@router.patch("/settings", response_model=EnvelopeAny, dependencies=write)
async def update_settings(
    payload: SettingsUpdate,
    request: Request,
    admin: AdminManagePlatform,
    db: DbDep,
    settings: SettingsDep,
) -> dict[str, Any]:
    service = PlatformSettings(db)
    diff = await service.update(payload.changes, actor_id=admin.user.id)
    for key, (old, new) in diff.items():
        AdminAuditService(db).add(
            actor=admin.user,
            action="settings.update",
            request=request,
            resource_type="setting",
            resource_id=key,
            resource_label=SPECS[key].label,
            metadata={"from": old, "to": new},
        )
    await db.commit()
    return ok(_settings_payload(await service.values(fresh=True), await service.rows(), settings))
