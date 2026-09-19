"""SQLAlchemy declarative base and shared column mixins.

Types are chosen to be portable between PostgreSQL (production) and SQLite (unit tests):
`Uuid` and `JSON().with_variant(JSONB)` map to native types on Postgres.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, ForeignKey, MetaData, TypeDecorator, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

JSONType = JSON().with_variant(JSONB(), "postgresql")


def utcnow() -> datetime:
    return datetime.now(UTC)


class TZDateTime(TypeDecorator[datetime]):
    """Timezone-aware datetime that survives SQLite (which drops tzinfo on read)."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("naive datetimes are not allowed; use utcnow()")
        return value

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map = {dict: JSONType}


class UUIDPrimaryKeyMixin:
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        TZDateTime(), nullable=False, default=utcnow, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TZDateTime(),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
        server_default=func.now(),
    )


class TenantScopedMixin:
    """Every user-owned record carries tenant_id + user_id. Repositories must filter on both."""

    @declared_attr
    def tenant_id(cls) -> Mapped[uuid.UUID]:
        return mapped_column(
            Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
        )

    @declared_attr
    def user_id(cls) -> Mapped[uuid.UUID]:
        return mapped_column(
            Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
        )
