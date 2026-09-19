"""Readiness probe for the model gateway."""

from __future__ import annotations

import httpx

from app.core.config import get_settings


async def ai_gateway_healthy() -> bool:
    settings = get_settings()
    if settings.ai_provider == "fake":
        return True
    try:
        async with httpx.AsyncClient(timeout=3) as http:
            resp = await http.get(f"{settings.litellm_api_base.rstrip('/')}/health/liveliness")
            return resp.status_code < 500
    except httpx.HTTPError:
        return False
