"""Account actions staff can take. Each one enforces its own guard rails server-side and writes
an admin audit event in the same transaction as the change, so a change without its audit row
(or vice versa) can't be committed.

Guard rails:
- nobody acts on their own account here (use the normal settings instead);
- a staff member only acts on accounts of a lower role, except admins, who may act on anyone;
- the last active admin can't be suspended or demoted (the deployment would be locked out).
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import Conflict, Forbidden, NotFound, ValidationFailed
from app.core.permissions import ROLE_RANK
from app.db.base import utcnow
from app.models.user import PlatformRole, User
from app.repositories.user_repository import UserRepository
from app.services.admin_audit import AdminAuditService
from app.services.platform_events import add_event


class AdminUserService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.audit = AdminAuditService(db)
        self.repo = UserRepository(db)

    async def get(self, user_id: Any) -> User:
        user = await self.db.get(User, user_id)
        if user is None:
            raise NotFound("No account with that id.")
        return user

    def _guard(self, actor: User, target: User, verb: str) -> None:
        if actor.id == target.id:
            raise Forbidden(
                f"You can't {verb} your own account from the admin area.", code="SELF_ACTION"
            )
        if actor.role != PlatformRole.admin and ROLE_RANK.get(target.role, 0) >= ROLE_RANK.get(
            actor.role, 0
        ):
            raise Forbidden(
                f"Only an admin can {verb} a {target.role} account.", code="ADMIN_PERMISSION"
            )

    async def _active_admins(self) -> int:
        return int(
            await self.db.scalar(
                select(func.count())
                .select_from(User)
                .where(User.role == PlatformRole.admin, User.is_active.is_(True))
            )
            or 0
        )

    async def suspend(
        self, actor: User, target: User, *, reason: str, revoke_sessions: bool, request: Request
    ) -> User:
        self._guard(actor, target, "suspend")
        if not target.is_active:
            raise Conflict("This account is already suspended.", code="ALREADY_SUSPENDED")
        if target.role == PlatformRole.admin and await self._active_admins() <= 1:
            raise Conflict("You can't suspend the last active admin.", code="LAST_ADMIN")
        target.is_active = False
        target.suspended_at = utcnow()
        target.suspension_reason = reason
        revoked = await self.repo.revoke_all_sessions(target.id) if revoke_sessions else 0
        self.audit.add(
            actor=actor,
            action="user.suspend",
            request=request,
            resource_type="user",
            resource_id=target.id,
            resource_label=target.email,
            metadata={"reason": reason, "sessions_revoked": revoked},
        )
        add_event(
            self.db,
            "security",
            "account.suspended",
            source="admin",
            message="Account suspended by an administrator",
            user_id=target.id,
        )
        await self.db.commit()
        return target

    async def reactivate(self, actor: User, target: User, *, request: Request) -> User:
        self._guard(actor, target, "reactivate")
        if target.is_active:
            raise Conflict("This account is already active.", code="ALREADY_ACTIVE")
        suspended_for = target.suspension_reason
        target.is_active = True
        target.suspended_at = None
        target.suspension_reason = None
        self.audit.add(
            actor=actor,
            action="user.reactivate",
            request=request,
            resource_type="user",
            resource_id=target.id,
            resource_label=target.email,
            metadata={"previous_reason": suspended_for},
        )
        add_event(
            self.db,
            "security",
            "account.reactivated",
            source="admin",
            message="Account reactivated by an administrator",
            user_id=target.id,
        )
        await self.db.commit()
        return target

    async def revoke_sessions(self, actor: User, target: User, *, request: Request) -> int:
        self._guard(actor, target, "sign out")
        count = await self.repo.revoke_all_sessions(target.id)
        self.audit.add(
            actor=actor,
            action="user.sessions_revoke",
            request=request,
            resource_type="user",
            resource_id=target.id,
            resource_label=target.email,
            metadata={"sessions_revoked": count},
        )
        add_event(
            self.db,
            "security",
            "sessions.revoked",
            source="admin",
            message=f"{count} session(s) signed out by an administrator",
            user_id=target.id,
        )
        await self.db.commit()
        return count

    async def change_role(self, actor: User, target: User, *, role: str, request: Request) -> User:
        try:
            new_role = PlatformRole(role)
        except ValueError:
            raise ValidationFailed("Unknown role.") from None
        if actor.id == target.id:
            raise Forbidden("You can't change your own role.", code="SELF_ACTION")
        if target.role == new_role:
            return target
        if (
            target.role == PlatformRole.admin
            and target.is_active
            and await self._active_admins() <= 1
        ):
            raise Conflict("You can't remove the last active admin.", code="LAST_ADMIN")
        previous = target.role
        target.role = new_role.value
        # A demotion takes effect immediately: the next admin request re-reads the role, but
        # ending the sessions also closes any admin page left open in a browser.
        revoked = 0
        if ROLE_RANK.get(new_role, 0) < ROLE_RANK.get(previous, 0):
            revoked = await self.repo.revoke_all_sessions(target.id)
        self.audit.add(
            actor=actor,
            action="user.role_change",
            request=request,
            resource_type="user",
            resource_id=target.id,
            resource_label=target.email,
            metadata={"from": previous, "to": new_role.value, "sessions_revoked": revoked},
        )
        add_event(
            self.db,
            "security",
            "role.changed",
            source="admin",
            message=f"Platform role changed from {previous} to {new_role.value}",
            user_id=target.id,
        )
        await self.db.commit()
        return target
