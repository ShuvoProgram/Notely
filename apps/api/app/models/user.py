from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, Enum, ForeignKey, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, JSONType, TimestampMixin, TZDateTime, UUIDPrimaryKeyMixin, utcnow

if TYPE_CHECKING:
    from app.models.tenant import Tenant


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    email_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)
    # User-level preference memory (AI model, summary length, ...). Never derived from note content.
    preferences: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    # TOTP material is encrypted with ENCRYPTION_KEY. A pending secret is deliberately separate
    # so a scanned-but-unverified setup can never satisfy a login challenge.
    totp_secret_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    totp_pending_secret_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    totp_pending_expires_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)

    tenant: Mapped[Tenant] = relationship(back_populates="users")
    identities: Mapped[list[AuthIdentity]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    sessions: Mapped[list[UserSession]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class SignInProvider(enum.StrEnum):
    google = "google"
    microsoft = "microsoft"


class AuthIdentity(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A federated sign-in identity (OIDC) linked to a local user."""

    __tablename__ = "auth_identities"
    __table_args__ = (
        UniqueConstraint(
            "provider", "provider_subject", name="uq_auth_identities_provider_subject"
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[SignInProvider] = mapped_column(
        Enum(SignInProvider, name="sign_in_provider"), nullable=False
    )
    provider_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)

    user: Mapped[User] = relationship(back_populates="identities")


class UserSession(UUIDPrimaryKeyMixin, Base):
    """Server-side session. The cookie holds a random token; only its keyed hash is stored."""

    __tablename__ = "user_sessions"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TZDateTime(), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(TZDateTime(), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(TZDateTime(), nullable=False, index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)
    two_factor_verified_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)

    user: Mapped[User] = relationship(back_populates="sessions")

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None and self.expires_at > utcnow()
