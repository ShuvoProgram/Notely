"""FastAPI dependencies: settings, database session, authenticated user."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.exceptions import Unauthorized
from app.db.session import get_db_session
from app.services.auth_service import AuthContext, AuthService

SettingsDep = Annotated[Settings, Depends(get_settings)]
DbDep = Annotated[AsyncSession, Depends(get_db_session)]


def get_auth_service(db: DbDep, settings: SettingsDep) -> AuthService:
    return AuthService(db, settings)


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]


async def get_optional_auth(
    request: Request, auth: AuthServiceDep, settings: SettingsDep
) -> AuthContext | None:
    token = request.cookies.get(settings.session_cookie_name)
    ctx = await auth.resolve_session(token)
    if ctx is not None:
        # Identity for rate limiting and logging is derived from the session, never the client.
        request.state.user_id = str(ctx.user.id)
        request.state.tenant_id = str(ctx.user.tenant_id)
    return ctx


async def get_current_auth(
    ctx: Annotated[AuthContext | None, Depends(get_optional_auth)],
) -> AuthContext:
    if ctx is None:
        raise Unauthorized()
    return ctx


CurrentAuth = Annotated[AuthContext, Depends(get_current_auth)]


def set_session_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.session_ttl_seconds,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        domain=settings.session_cookie_domain,
        path="/",
    )


def clear_session_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        key=settings.session_cookie_name,
        domain=settings.session_cookie_domain,
        path="/",
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )
