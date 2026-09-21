"""Authentication: signup, login, sessions, password changes.

Sessions are opaque random tokens delivered in an HttpOnly cookie. The database stores a keyed
hash of the token. Sessions slide: `last_seen_at`/`expires_at` are refreshed on use.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import Conflict, NotFound, Unauthorized, ValidationFailed
from app.core.security import hash_password, hash_token, new_session_token, verify_password
from app.db.base import utcnow
from app.models.user import SignInProvider, User, UserSession
from app.repositories.user_repository import UserRepository

# Refresh the sliding expiry at most this often to avoid a write on every request.
SESSION_TOUCH_INTERVAL = timedelta(minutes=5)


@dataclass(frozen=True)
class IssuedSession:
    token: str  # only ever placed in the cookie
    record: UserSession


@dataclass(frozen=True)
class AuthContext:
    user: User
    session: UserSession


class AuthService:
    def __init__(self, db: AsyncSession, settings: Settings) -> None:
        self.db = db
        self.settings = settings
        self.repo = UserRepository(db)

    # --- account creation / credentials ------------------------------------------------------

    async def signup(self, *, email: str, password: str, display_name: str) -> User:
        email = email.lower().strip()
        if await self.repo.get_by_email(email) is not None:
            raise Conflict("An account with this email already exists.", code="EMAIL_TAKEN")
        user = await self.repo.create_user_with_personal_tenant(
            email=email,
            display_name=display_name,
            password_hash=hash_password(password),
            email_verified=False,
        )
        await self._bind_pending_shares(user)
        await self.db.commit()
        return user

    async def _bind_pending_shares(self, user: User) -> None:
        """Notes shared with this address before the account existed become reachable now."""
        from app.models.note import (
            Note,
            NoteCollaborator,  # local: keep auth free of note imports
        )
        from app.models.notification import NotificationKind
        from app.services.notification_service import NotificationService

        rows = list(
            await self.db.scalars(
                select(NoteCollaborator).where(
                    NoteCollaborator.email == user.email, NoteCollaborator.user_id.is_(None)
                )
            )
        )
        for row in rows:
            # Signing up with the invited address is acceptance: the emailed link is no longer
            # needed (and could not be reused).
            row.user_id = user.id
            row.accepted_at = utcnow()
            row.invite_token = None
            note = await self.db.get(Note, row.note_id)
            if note is not None:
                await NotificationService(self.db).notify(
                    user,
                    NotificationKind.note_shared,
                    "A note was shared with you",
                    body=note.title or "Untitled",
                    href=f"/app/notes/{note.id}",
                    dedupe_key=f"note:{note.id}:shared:{user.id}",
                    commit=False,
                )

    async def authenticate(self, *, email: str, password: str) -> User:
        user = await self.repo.get_by_email(email.lower().strip())
        # Constant-ish time: always run the verifier, even when the user is unknown.
        stored = user.password_hash if user and user.password_hash else _DUMMY_HASH
        valid = verify_password(password, stored)
        if user is None or user.password_hash is None or not valid:
            raise Unauthorized("Incorrect email or password.", code="INVALID_CREDENTIALS")
        if not user.is_active:
            raise Unauthorized("This account is disabled.", code="ACCOUNT_DISABLED")
        return user

    async def change_password(
        self, user: User, *, current_password: str, new_password: str, keep_session: UserSession
    ) -> None:
        if user.password_hash is None or not verify_password(current_password, user.password_hash):
            raise ValidationFailed(
                "Your current password is incorrect.",
                code="INVALID_CREDENTIALS",
                details={"fields": {"current_password": ["Incorrect password"]}},
            )
        if current_password == new_password:
            raise ValidationFailed(
                "Choose a password you haven't used before.",
                details={"fields": {"new_password": ["Must differ from current password"]}},
            )
        user.password_hash = hash_password(new_password)
        # Changing a password ends every other session.
        await self.repo.revoke_all_sessions(user.id, except_id=keep_session.id)
        await self.db.commit()

    # --- federated sign-in ---------------------------------------------------------------------

    async def sign_in_with_identity(
        self,
        *,
        provider: SignInProvider,
        subject: str,
        email: str | None,
        email_verified: bool,
        display_name: str | None,
        avatar_url: str | None,
    ) -> User:
        identity = await self.repo.get_identity(provider, subject)
        if identity is not None:
            user = await self.repo.get_by_id(identity.user_id)
            if user is None or not user.is_active:
                raise Unauthorized("This account is disabled.", code="ACCOUNT_DISABLED")
            return user

        if not email:
            raise Unauthorized(
                "Your provider did not share an email address.", code="EMAIL_REQUIRED"
            )
        email = email.lower().strip()
        user = await self.repo.get_by_email(email)
        if user is not None:
            # Link only when the provider vouches for the email; otherwise an attacker who
            # controls an unverified provider account could take over a local account.
            if not email_verified:
                raise Unauthorized(
                    "Sign in with your password, then connect this provider from settings.",
                    code="EMAIL_UNVERIFIED",
                )
        else:
            user = await self.repo.create_user_with_personal_tenant(
                email=email,
                display_name=display_name or email.split("@")[0],
                password_hash=None,
                email_verified=email_verified,
            )
            await self._bind_pending_shares(user)
            user.avatar_url = avatar_url
        await self.repo.add_identity(user, provider, subject, email)
        await self.db.commit()
        return user

    # --- sessions -------------------------------------------------------------------------------

    async def issue_session(
        self, user: User, *, user_agent: str | None, ip_address: str | None
    ) -> IssuedSession:
        token = new_session_token()
        record = await self.repo.create_session(
            user,
            token_hash=hash_token(token, self.settings.session_secret),
            expires_at=utcnow() + timedelta(seconds=self.settings.session_ttl_seconds),
            user_agent=user_agent,
            ip_address=ip_address,
        )
        await self.repo.touch_last_login(user)
        await self.db.commit()
        return IssuedSession(token=token, record=record)

    async def resolve_session(self, token: str | None) -> AuthContext | None:
        if not token:
            return None
        record = await self.repo.get_session_by_token_hash(
            hash_token(token, self.settings.session_secret)
        )
        if record is None or not record.is_active:
            return None
        user = await self.repo.get_by_id(record.user_id)
        if user is None or not user.is_active:
            return None
        now = utcnow()
        if now - record.last_seen_at > SESSION_TOUCH_INTERVAL:
            record.last_seen_at = now
            record.expires_at = now + timedelta(seconds=self.settings.session_ttl_seconds)
            await self.db.commit()
        return AuthContext(user=user, session=record)

    async def revoke_session(self, session: UserSession) -> None:
        session.revoked_at = utcnow()
        await self.db.commit()

    async def revoke_session_by_id(self, user: User, session_id: uuid.UUID) -> None:
        record = await self.repo.get_session_for_user(session_id, user.id)
        if record is None:
            raise NotFound("Session not found.")
        record.revoked_at = utcnow()
        await self.db.commit()

    async def revoke_other_sessions(self, user: User, current: UserSession) -> int:
        count = await self.repo.revoke_all_sessions(user.id, except_id=current.id)
        await self.db.commit()
        return count

    async def list_sessions(self, user: User) -> list[UserSession]:
        return await self.repo.list_active_sessions(user.id)


# A valid argon2 hash of an unguessable value, used to equalize timing for unknown emails.
_DUMMY_HASH = hash_password(new_session_token())
