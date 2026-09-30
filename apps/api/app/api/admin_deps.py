"""Authorization for the admin API. Every admin route depends on `require(...)`.

Checks, in order, all server-side:
1. a valid session with any required second factor completed (CurrentAuth);
2. a staff role, read from the database row loaded with the session — never from the client;
3. a session no older than ADMIN_SESSION_MAX_AGE_HOURS (admin access re-authenticates twice a
   day even though ordinary sessions slide for a week);
4. two-factor authentication when ADMIN_REQUIRE_2FA is set;
5. the specific permission the route needs.
A signed-in non-staff caller is refused with 403 and the attempt lands in the admin audit log.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Annotated

from fastapi import Depends, Request

from app.api.deps import CurrentAuth, DbDep, SettingsDep
from app.core.exceptions import Forbidden, Unauthorized
from app.core.kv import kv
from app.core.permissions import Permission, permissions_for
from app.core.rate_limit import rate_limit
from app.db.base import utcnow
from app.models.user import STAFF_ROLES, User, UserSession
from app.services.admin_audit import AdminAuditService


@dataclass(frozen=True)
class AdminContext:
    user: User
    session: UserSession
    permissions: frozenset[Permission]

    @property
    def role(self) -> str:
        return self.user.role

    def can(self, permission: Permission) -> bool:
        return permission in self.permissions


DENIED_AUDIT_WINDOW_SECONDS = 600

admin_read_limit = rate_limit("admin", lambda s: s.rate_limit_admin_per_minute)
admin_write_limit = rate_limit("admin_write", lambda s: s.rate_limit_admin_write_per_minute)


def require(permission: Permission) -> Callable[..., Awaitable[AdminContext]]:
    async def _dependency(
        request: Request, ctx: CurrentAuth, db: DbDep, settings: SettingsDep
    ) -> AdminContext:
        user = ctx.user
        if user.role not in STAFF_ROLES:
            # One audit row per person per window: enough to see who probed the admin API
            # without letting a script fill the audit table.
            throttle = f"admin-denied:{user.id}"
            if await kv.get(throttle) is None:
                await kv.set(throttle, "1", DENIED_AUDIT_WINDOW_SECONDS)
                AdminAuditService(db).add(
                    actor=user,
                    action="admin.access_denied",
                    request=request,
                    result="denied",
                    metadata={"path": request.url.path, "method": request.method},
                )
                await db.commit()
            raise Forbidden("This area is for Notely administrators.", code="ADMIN_ONLY")
        max_age = timedelta(hours=settings.admin_session_max_age_hours)
        if utcnow() - ctx.session.created_at > max_age:
            raise Unauthorized(
                "For your security, sign in again to use the admin area.",
                code="ADMIN_REAUTH_REQUIRED",
            )
        if settings.admin_require_2fa and not user.totp_secret_encrypted:
            raise Forbidden(
                "Turn on two-factor authentication to use the admin area.",
                code="ADMIN_2FA_REQUIRED",
            )
        granted = permissions_for(user.role)
        if permission not in granted:
            AdminAuditService(db).add(
                actor=user,
                action="admin.permission_denied",
                request=request,
                result="denied",
                metadata={"path": request.url.path, "needs": permission.value},
            )
            await db.commit()
            raise Forbidden("Your admin role doesn't allow this action.", code="ADMIN_PERMISSION")
        return AdminContext(user=user, session=ctx.session, permissions=granted)

    return _dependency


AdminRead = Annotated[AdminContext, Depends(require(Permission.read))]
AdminManageUsers = Annotated[AdminContext, Depends(require(Permission.manage_users))]
AdminManageRoles = Annotated[AdminContext, Depends(require(Permission.manage_roles))]
AdminManagePlatform = Annotated[AdminContext, Depends(require(Permission.manage_platform))]
