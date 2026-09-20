"""Async engine/session factory. PostgreSQL is the source of truth."""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core import metrics
from app.core.config import get_settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        settings = get_settings()
        kwargs: dict[str, Any] = {"pool_pre_ping": True, "echo": settings.debug}
        if settings.database_url.startswith("postgresql"):
            kwargs.update(pool_size=settings.db_pool_size, max_overflow=settings.db_max_overflow)
        _engine = create_async_engine(settings.database_url, **kwargs)
        instrument(_engine)
    return _engine


def instrument(engine: AsyncEngine) -> None:
    """Statement latency by verb (SELECT/INSERT/...) — never the statement text or parameters."""
    sync_engine = engine.sync_engine

    @event.listens_for(sync_engine, "before_cursor_execute")
    def _before(conn: Any, cursor: Any, statement: str, *_: Any) -> None:
        conn.info.setdefault("query_start", []).append(time.perf_counter())

    @event.listens_for(sync_engine, "after_cursor_execute")
    def _after(conn: Any, cursor: Any, statement: str, *_: Any) -> None:
        starts = conn.info.get("query_start")
        if not starts:
            return
        verb = statement.lstrip().split(" ", 1)[0].upper()[:12] or "OTHER"
        metrics.db_query_latency.labels(verb).observe(time.perf_counter() - starts.pop())


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _session_factory


def configure_database(engine: AsyncEngine) -> None:
    """Override the engine (used by tests to point at a throwaway database)."""
    global _engine, _session_factory
    _engine = engine
    instrument(engine)
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
