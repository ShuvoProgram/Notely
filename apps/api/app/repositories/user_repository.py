"""Persistence for tenants, users, identities and sessions.

Every method that reads user-owned data takes the owning user/tenant id explicitly so
authorization is enforced at the query, not in the caller.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utcnow
from app.models.tenant import Tenant, TenantKind
from app.models.user import AuthIdentity, SignInProvider, User, UserSession


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # --- tenants / users -------------------------------------------------------------------

    async def create_user_with_personal_tenant(
        self, *, email: str, display_name: str, password_hash: str | None, email_verified: bool
    ) -> User:
        tenant = Tenant(name=display_name, kind=TenantKind.personal)
        self.session.add(tenant)
        await self.session.flush()
        user = User(
            tenant_id=tenant.id,
            email=email,
            display_name=display_name,
            password_hash=password_hash,
            email_verified=email_verified,
        )
        self.session.add(user)
        await self.session.flush()
        return user

    async def get_by_email(self, email: str) -> User | None:
        return await self.session.scalar(select(User).where(User.email == email))

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        return await self.session.get(User, user_id)

    async def touch_last_login(self, user: User) -> None:
        user.last_login_at = utcnow()

    # --- federated identities --------------------------------------------------------------

    async def get_identity(self, provider: SignInProvider, subject: str) -> AuthIdentity | None:
        return await self.session.scalar(
            select(AuthIdentity).where(
                AuthIdentity.provider == provider, AuthIdentity.provider_subject == subject
            )
        )

    async def add_identity(
        self, user: User, provider: SignInProvider, subject: str, email: str | None
    ) -> AuthIdentity:
        identity = AuthIdentity(
            tenant_id=user.tenant_id,
            user_id=user.id,
            provider=provider,
            provider_subject=subject,
            email=email,
        )
        self.session.add(identity)
        await self.session.flush()
        return identity

    # --- sessions ----------------------------------------------------------------------------

    async def create_session(
        self,
        user: User,
        *,
        token_hash: str,
        expires_at: datetime,
        user_agent: str | None,
        ip_address: str | None,
    ) -> UserSession:
        now = utcnow()
        record = UserSession(
            tenant_id=user.tenant_id,
            user_id=user.id,
            token_hash=token_hash,
            user_agent=user_agent[:512] if user_agent else None,
            ip_address=ip_address[:64] if ip_address else None,
            created_at=now,
            last_seen_at=now,
            expires_at=expires_at,
        )
        self.session.add(record)
        await self.session.flush()
        return record

    async def get_session_by_token_hash(self, token_hash: str) -> UserSession | None:
        return await self.session.scalar(
            select(UserSession).where(UserSession.token_hash == token_hash)
        )

    async def list_active_sessions(self, user_id: uuid.UUID) -> list[UserSession]:
        result = await self.session.scalars(
            select(UserSession)
            .where(
                UserSession.user_id == user_id,
                UserSession.revoked_at.is_(None),
                UserSession.expires_at > utcnow(),
            )
            .order_by(UserSession.last_seen_at.desc())
        )
        return list(result)

    async def get_session_for_user(
        self, session_id: uuid.UUID, user_id: uuid.UUID
    ) -> UserSession | None:
        return await self.session.scalar(
            select(UserSession).where(UserSession.id == session_id, UserSession.user_id == user_id)
        )

    async def revoke_all_sessions(
        self, user_id: uuid.UUID, *, except_id: uuid.UUID | None = None
    ) -> int:
        stmt = (
            update(UserSession)
            .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
            .values(revoked_at=utcnow())
        )
        if except_id is not None:
            stmt = stmt.where(UserSession.id != except_id)
        result = await self.session.execute(stmt)
        return int(getattr(result, "rowcount", 0) or 0)
