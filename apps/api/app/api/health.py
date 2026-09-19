"""Liveness/readiness probes. Never expose configuration values here."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Response, status

from app.ai.health import ai_gateway_healthy
from app.core.config import get_settings
from app.core.kv import redis_healthy
from app.db.session import database_healthy

router = APIRouter(tags=["health"])


@router.get("/health")
@router.get("/health/live")
async def live() -> dict[str, Any]:
    return {"status": "ok"}


@router.get("/health/ready")
async def ready(response: Response) -> dict[str, Any]:
    settings = get_settings()
    checks = {
        "database": await database_healthy(),
        "redis": await redis_healthy(),
        "configuration": not settings.validate_for_runtime(),
        "ai_gateway": await ai_gateway_healthy(),
    }
    healthy = all(checks.values())
    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "ok" if healthy else "degraded", "checks": checks}
