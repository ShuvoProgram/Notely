"""Async engine/session factory. PostgreSQL is the source of truth."""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.database_url, pool_pre_ping=True, echo=settings.debug
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _session_factory


def configure_database(engine: AsyncEngine) -> None:
    """Override the engine (used by tests to point at a throwaway database)."""
    global _engine, _session_factory
    _engine = engine
    _session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def get_db_session() -> AsyncIterator[AsyncSession]:
    async with get_session_factory()() as session:
        yield session


async def database_healthy() -> bool:
    try:
        async with get_engine().connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


async def dispose_engine() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None
