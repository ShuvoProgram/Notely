"""LangGraph checkpointer lifecycle. Postgres in real deployments so runs can pause for approval
and resume later (even on another worker); in-memory for tests."""

from __future__ import annotations

from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from app.core.config import get_settings

_saver: BaseCheckpointSaver[Any] | None = None
_pool: AsyncConnectionPool | None = None


def _psycopg_dsn(url: str) -> str:
    # postgresql+asyncpg://user:pw@host/db -> postgresql://user:pw@host/db
    return url.replace("postgresql+asyncpg://", "postgresql://", 1).replace(
        "postgresql+psycopg://", "postgresql://", 1
    )


async def init_checkpointer() -> BaseCheckpointSaver[Any]:
    global _saver, _pool
    if _saver is not None:
        return _saver
    settings = get_settings()
    if settings.ai_checkpointer == "memory":
        _saver = MemorySaver()
        return _saver
    _guard_event_loop()
    _pool = AsyncConnectionPool(
        conninfo=_psycopg_dsn(settings.database_url),
        min_size=1,
        max_size=5,
        open=False,
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
    )
    await _pool.open()
    saver = AsyncPostgresSaver(_pool)  # type: ignore[arg-type]
    await saver.setup()  # idempotent: creates checkpoint tables + migrations
    _saver = saver
    return _saver


def _guard_event_loop() -> None:
    """psycopg's async driver cannot run on Windows' default ProactorEventLoop."""
    import asyncio
    import sys

    if sys.platform == "win32" and type(asyncio.get_running_loop()).__name__.startswith("Proactor"):
        raise RuntimeError(
            "The Postgres checkpointer needs a selector event loop on Windows. Run uvicorn with "
            "--reload (dev), set AI_CHECKPOINTER=memory, or use the Docker stack."
        )


def get_checkpointer() -> BaseCheckpointSaver[Any]:
    if _saver is None:
        raise RuntimeError("checkpointer not initialised; call init_checkpointer() at startup")
    return _saver


async def close_checkpointer() -> None:
    global _saver, _pool
    if _pool is not None:
        await _pool.close(timeout=5)
    _saver = None
    _pool = None
