from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import RedirectResponse

from app.api.deps import (
    AuthServiceDep,
    CurrentAuth,
    SettingsDep,
    clear_session_cookie,
    set_session_cookie,
)
from app.core import metrics
from app.core.config import Settings
from app.core.exceptions import APIError, OAuthExchangeFailed
from app.core.oauth import callback_uri
from app.core.rate_limit import client_ip, rate_limit
from app.core.responses import Envelope, ok
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    SessionOut,
    SignInProviderOut,
    SignupRequest,
    UserOut,
)
from app.services.auth_service import AuthService
from app.services.sign_in_providers import (
    SIGN_IN_FLOW,
    build_client,
    claims_to_profile,
    enabled_sign_in_providers,
    get_sign_in_provider,
)

router = APIRouter(prefix="/auth", tags=["auth"])

auth_limit = rate_limit("auth", lambda s: s.rate_limit_auth_per_minute)


def user_out(user: Any) -> UserOut:
    return UserOut(
        id=user.id,
        tenant_id=user.tenant_id,
        email=user.email,
        email_verified=user.email_verified,
        display_name=user.display_name,
        avatar_url=user.avatar_url,
        has_password=user.password_hash is not None,
        created_at=user.created_at,
        notifications=(
            dict((user.preferences or {}).get("notifications") or {})
            if isinstance(user.preferences, dict)
            else {}
        ),
    )


@router.post(
    "/signup",
    status_code=status.HTTP_201_CREATED,
    response_model=Envelope[UserOut],
    dependencies=[Depends(auth_limit)],
)
async def signup(
    payload: SignupRequest,
    request: Request,
    response: Response,
    auth: AuthServiceDep,
    settings: SettingsDep,
) -> dict[str, Any]:
    user = await auth.signup(
        email=payload.email, password=payload.password, display_name=payload.display_name
    )
    issued = await auth.issue_session(
        user, user_agent=request.headers.get("user-agent"), ip_address=client_ip(request)
    )
    set_session_cookie(response, issued.token, settings)
    return ok(user_out(user))


@router.post("/login", response_model=Envelope[UserOut], dependencies=[Depends(auth_limit)])
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    auth: AuthServiceDep,
    settings: SettingsDep,
) -> dict[str, Any]:
    user = await auth.authenticate(email=payload.email, password=payload.password)
    issued = await auth.issue_session(
        user, user_agent=request.headers.get("user-agent"), ip_address=client_ip(request)
    )
    set_session_cookie(response, issued.token, settings)
    return ok(user_out(user))


@router.post("/logout", response_model=Envelope[dict[str, bool]])
async def logout(
    response: Response, ctx: CurrentAuth, auth: AuthServiceDep, settings: SettingsDep
) -> dict[str, Any]:
    await auth.revoke_session(ctx.session)
    clear_session_cookie(response, settings)
    return ok({"logged_out": True})


@router.post("/logout-all", response_model=Envelope[dict[str, int]])
async def logout_all(ctx: CurrentAuth, auth: AuthServiceDep) -> dict[str, Any]:
    count = await auth.revoke_other_sessions(ctx.user, ctx.session)
    return ok({"revoked": count})


@router.post(
    "/change-password",
    response_model=Envelope[dict[str, bool]],
    dependencies=[Depends(auth_limit)],
)
async def change_password(
    payload: ChangePasswordRequest, ctx: CurrentAuth, auth: AuthServiceDep
) -> dict[str, Any]:
    await auth.change_password(
        ctx.user,
        current_password=payload.current_password,
        new_password=payload.new_password,
        keep_session=ctx.session,
    )
    return ok({"changed": True})


@router.get("/sessions", response_model=Envelope[list[SessionOut]])
async def list_sessions(ctx: CurrentAuth, auth: AuthServiceDep) -> dict[str, Any]:
    sessions = await auth.list_sessions(ctx.user)
    return ok(
        [
            SessionOut.model_validate(s).model_copy(update={"current": s.id == ctx.session.id})
            for s in sessions
        ]
    )


@router.delete("/sessions/{session_id}", response_model=Envelope[dict[str, bool]])
async def revoke_session(
    session_id: uuid.UUID, ctx: CurrentAuth, auth: AuthServiceDep
) -> dict[str, Any]:
    await auth.revoke_session_by_id(ctx.user, session_id)
    return ok({"revoked": True})


# --- federated sign-in ---------------------------------------------------------------------------


@router.get("/providers", response_model=Envelope[list[SignInProviderOut]])
async def list_providers(settings: SettingsDep) -> dict[str, Any]:
    base = callback_uri(settings, "/auth/oauth")
    return ok(
        [
            SignInProviderOut(
                id=spec.id.value,
                display_name=spec.display_name,
                start_url=f"{base}/{spec.id.value}/start",
            )
            for spec in enabled_sign_in_providers(settings)
        ]
    )


@router.get("/oauth/{provider_id}/start", dependencies=[Depends(auth_limit)])
async def oauth_start(provider_id: str, settings: SettingsDep) -> RedirectResponse:
    spec = get_sign_in_provider(settings, provider_id)
    url = await build_client(settings, spec).begin(context={"flow": SIGN_IN_FLOW})
    return RedirectResponse(url, status_code=status.HTTP_302_FOUND)


async def complete_sign_in(
    provider_id: str,
    record: dict[str, Any],
    *,
    request: Request,
    auth: AuthService,
    settings: Settings,
    code: str | None,
    error: str | None,
) -> RedirectResponse:
    """Finish "Continue with {vendor}" once the shared `/oauth/{vendor}/callback` has validated
    the state: exchange the code, verify the id_token, create-or-find the account, start a
    session and land the user in the app. Every failure becomes a readable login-page message."""
    try:
        spec = get_sign_in_provider(settings, provider_id)
    except APIError:
        return _login_redirect(settings, "oauth_failed")
    client = build_client(settings, spec)
    if error or not code:
        return _login_redirect(settings, "oauth_denied")
    try:
        tokens = await client.exchange_code(code, record.get("verifier"))
        if not tokens.id_token:
            raise OAuthExchangeFailed()
        claims = client.verify_id_token(tokens.id_token, record.get("nonce"))
        userinfo = await client.fetch_userinfo(tokens.access_token)
        profile = claims_to_profile(claims, userinfo)
        user = await auth.sign_in_with_identity(
            provider=spec.id,
            subject=profile.subject,
            email=profile.email,
            email_verified=profile.email_verified,
            display_name=profile.display_name,
            avatar_url=profile.avatar_url,
        )
    except OAuthExchangeFailed:
        metrics.oauth_failures.labels(f"signin:{spec.id}", "exchange").inc()
        return _login_redirect(settings, "oauth_failed")
    issued = await auth.issue_session(
        user, user_agent=request.headers.get("user-agent"), ip_address=client_ip(request)
    )
    response = RedirectResponse(
        f"{settings.frontend_origin}/app", status_code=status.HTTP_302_FOUND
    )
    set_session_cookie(response, issued.token, settings)
    return response


def login_redirect(settings: Settings, reason: str) -> RedirectResponse:
    return _login_redirect(settings, reason)


def _login_redirect(settings: Any, reason: str) -> RedirectResponse:
    return RedirectResponse(
        f"{settings.frontend_origin}/login?error={reason}", status_code=status.HTTP_302_FOUND
    )
