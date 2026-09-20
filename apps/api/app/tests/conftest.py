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
# Scripted model by default; the opt-in agent evals (AI_EVAL=1) keep whatever provider is set.
if os.environ.get("AI_EVAL") == "1":
    os.environ.setdefault("AI_PROVIDER", "litellm")
else:
    os.environ["AI_PROVIDER"] = "fake"
os.environ["AI_CHECKPOINTER"] = "memory"
# Deterministic Fernet key so encrypted-at-rest assertions are stable.
os.environ["ENCRYPTION_KEY"] = "8bVJ7u2Q9mJmZcJ3b8lZ5G3Q0eVfG2Yg2b8nQx4bY9k="
# Tests must not pick up a developer's real vendor apps from .env; fixtures set what they need.
for _prefix in (
    "google",
    "microsoft",
    "slack",
    "notion",
    "todoist",
    "asana",
    "jira",
    "dropbox",
    "clickup",
):
    os.environ[f"OAUTH_{_prefix.upper()}_CLIENT_ID"] = ""
    os.environ[f"OAUTH_{_prefix.upper()}_CLIENT_SECRET"] = ""

from app.core.config import get_settings  # noqa: E402
from app.core.kv import kv  # noqa: E402
from app.db.session import configure_database, dispose_engine  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models import Base  # noqa: E402

pytest_plugins = ["app.tests.integrations_fixtures"]

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
    from app.workers import queue

    queue.reset()
    queue.force_memory()
    yield
    await dispose_engine()


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    from app.ai import checkpoint

    await checkpoint.close_checkpointer()
    await checkpoint.init_checkpointer()
    app = create_app(get_settings())
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c
    await checkpoint.close_checkpointer()


async def read_sse(response: Any) -> list[dict[str, Any]]:
    """Collect SSE events from an httpx response body."""
    import json

    events: list[dict[str, Any]] = []
    body = response.text if hasattr(response, "text") else (await response.aread()).decode()
    for block in body.split("\n\n"):
        for line in block.splitlines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
    return events


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
