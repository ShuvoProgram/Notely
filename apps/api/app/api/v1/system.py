"""Public platform status: what the app shell needs to show (maintenance banner) and what the
sign-up page needs to know. Booleans and an admin-written message only."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.api.deps import DbDep
from app.core.responses import Envelope, ok
from app.services.platform_settings import PlatformSettings

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/status", response_model=Envelope[dict[str, Any]])
async def status(db: DbDep) -> dict[str, Any]:
    values = await PlatformSettings(db).values()
    return ok(
        {
            "maintenance": {
                "enabled": bool(values["maintenance_mode"]),
                "message": values["maintenance_message"] if values["maintenance_mode"] else None,
            },
            "signups_enabled": bool(values["signups_enabled"]),
            "ai_enabled": bool(values["ai_enabled"]),
            "automations_enabled": bool(values["automations_enabled"]),
        }
    )
