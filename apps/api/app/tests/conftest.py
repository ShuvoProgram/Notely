"""Test fixtures: isolated SQLite database per test module, in-memory KV, HTTP client."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://127.0.0.1:1/0")  # intentionally unreachable
os.environ.setdefault("SESSION_SECRET", "test-session-secret-0123456789")
os.environ.setdefault("FRONTEND_ORIGIN", "http://localhost:3000")
os.environ["RATE_LIMIT_AUTH_PER_MINUTE"] = "10"  # tests assert the production default

from app.core.config import get_settings  # noqa: E402
from app.core.kv import kv  # noqa: E402
from app.db.session import configure_database, dispose_engine  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models import Base  # noqa: E402

ORIGIN = {"Origin": "http://localhost:3000"}


@pytest.fixture(autouse=True)
async def _database() -> AsyncIterator[None]:
    from sqlalchemy.pool import StaticPool

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    # SQLite only enforces ON DELETE CASCADE / SET NULL with this pragma.
    from sqlalchemy import event

    @event.listens_for(engine.sync_engine, "connect")
    def _fk_on(dbapi_conn, _record):  # type: ignore[no-untyped-def]
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    configure_database(engine)
    kv.reset()
    kv.force_memory()
    yield
    await dispose_engine()


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    app = create_app(get_settings())
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


async def signup(
    client: AsyncClient, email: str = "ada@example.com", password: str = "correct horse battery"
) -> dict[str, Any]:
    resp = await client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": password, "display_name": "Ada"},
        headers=ORIGIN,
    )
    assert resp.status_code == 201, resp.text
    data: dict[str, Any] = resp.json()["data"]
    return data
