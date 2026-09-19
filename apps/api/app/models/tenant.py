from __future__ import annotations

import enum
from typing import TYPE_CHECKING

from sqlalchemy import Enum, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.user import User


class TenantKind(enum.StrEnum):
    personal = "personal"
    team = "team"  # post-MVP team workspaces


class Tenant(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "tenants"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    kind: Mapped[TenantKind] = mapped_column(
        Enum(TenantKind, name="tenant_kind"), nullable=False, default=TenantKind.personal
    )

    users: Mapped[list[User]] = relationship(back_populates="tenant")
