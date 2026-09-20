"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.ai.checkpoint import close_checkpointer, init_checkpointer
from app.api import health
from app.api.v1 import ai, auth, integrations, notes, tasks, users
from app.core.config import Settings, get_settings
from app.core.exceptions import register_exception_handlers
from app.core.kv import close_redis
from app.core.logging import configure_logging, get_logger
from app.core.middleware import (
    BodySizeLimitMiddleware,
    CSRFOriginMiddleware,
    RequestContextMiddleware,
    SecurityHeadersMiddleware,
)
from app.db.session import dispose_engine, get_session_factory
from app.workers.queue import close_queue

log = get_logger(__name__)


async def _sync_integration_catalog(settings: Settings) -> None:
    from app.services.connection_service import ConnectionService

    try:
        async with get_session_factory()() as db:
            await ConnectionService(db, settings).ensure_catalog()
    except Exception:  # noqa: BLE001 — a missing table before migrations must not block startup
        log.warning("integration_catalog_sync_skipped")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        problems = settings.validate_for_runtime()
        for problem in problems:
            log.error("configuration_problem", extra={"problem": problem})
        if problems and settings.is_production:
            raise RuntimeError("Refusing to start with invalid production configuration")
        await init_checkpointer()
        await _sync_integration_catalog(settings)
        yield
        await close_queue()
        await close_checkpointer()
        await close_redis()
        await dispose_engine()

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if not settings.is_production else None,
        redoc_url=None,
        openapi_url="/openapi.json" if not settings.is_production else None,
    )

    # Middleware executes in reverse registration order; CORS must be outermost.
    app.add_middleware(SecurityHeadersMiddleware, settings=settings)
    app.add_middleware(BodySizeLimitMiddleware, settings=settings)
    app.add_middleware(CSRFOriginMiddleware, settings=settings)
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list({*settings.allowed_origins, settings.frontend_origin}),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID", "Retry-After"],
    )

    register_exception_handlers(app)

    v1 = APIRouter(prefix=settings.api_prefix)
    v1.include_router(auth.router)
    v1.include_router(users.router)
    v1.include_router(notes.notes_router)
    v1.include_router(notes.folders_router)
    v1.include_router(notes.tags_router)
    v1.include_router(notes.search_router)
    v1.include_router(tasks.router)
    v1.include_router(ai.router)
    v1.include_router(ai.audit_router)
    v1.include_router(integrations.router)
    v1.include_router(integrations.oauth_router)
    v1.include_router(integrations.webhook_router)
    if settings.ai_provider == "fake" and not settings.is_production:
        from app.api.v1 import ai_dev

        v1.include_router(ai_dev.router)
    app.include_router(v1)
    app.include_router(health.router)
    if settings.metrics_enabled:
        from app.api.metrics import router as metrics_router

        app.include_router(metrics_router)
    return app


app = create_app()
