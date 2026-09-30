"""Runtime platform settings that admins change without a deploy.

Every key is declared here with its type, default and bounds; unknown keys are rejected. Values
are cached per process for a few seconds, so enforcement costs no query on hot paths.
Secrets never live here — provider keys and credentials stay in the environment.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import APIError, ValidationFailed
from app.db.base import utcnow
from app.models.admin import PlatformSetting

CACHE_SECONDS = 5.0


@dataclass(frozen=True)
class SettingSpec:
    key: str
    label: str
    description: str
    kind: str  # bool | int | text
    default: Any
    group: str
    minimum: int | None = None
    maximum: int | None = None
    max_length: int | None = None
    nullable: bool = False  # int settings: null = unlimited


SPECS: dict[str, SettingSpec] = {
    s.key: s
    for s in (
        SettingSpec(
            "maintenance_mode",
            "Maintenance mode",
            "Pause changes for everyone: people can still sign in and read, but saving is "
            "blocked with the message below. The admin area keeps working.",
            "bool",
            False,
            "availability",
        ),
        SettingSpec(
            "maintenance_message",
            "Maintenance message",
            "Shown in the app while maintenance mode is on.",
            "text",
            "Notely is undergoing maintenance. Changes are paused for a few minutes.",
            "availability",
            max_length=300,
        ),
        SettingSpec(
            "signups_enabled",
            "New sign-ups",
            "Allow new accounts (email and Google/Microsoft). Existing people can always sign in.",
            "bool",
            True,
            "availability",
        ),
        SettingSpec(
            "ai_enabled",
            "AI assistant",
            "Turn the AI assistant and AI workflow drafting on or off for everyone.",
            "bool",
            True,
            "features",
        ),
        SettingSpec(
            "automations_enabled",
            "Automations",
            "Allow creating and running automations. Scheduled runs pause while this is off.",
            "bool",
            True,
            "features",
        ),
        SettingSpec(
            "ai_daily_requests_per_user",
            "AI requests per person per day",
            "Daily cap on assistant requests for each person. Empty = no cap.",
            "int",
            None,
            "limits",
            minimum=1,
            maximum=100_000,
            nullable=True,
        ),
        SettingSpec(
            "automations_max_per_user",
            "Automations per person",
            "The most automations one person can have. Empty = no cap.",
            "int",
            None,
            "limits",
            minimum=1,
            maximum=10_000,
            nullable=True,
        ),
    )
}

_cache: tuple[float, dict[str, Any]] | None = None


def invalidate_cache() -> None:
    global _cache
    _cache = None


def _coerce(spec: SettingSpec, value: Any) -> Any:
    if spec.kind == "bool":
        if not isinstance(value, bool):
            raise ValidationFailed(f"{spec.label} must be on or off.")
        return value
    if spec.kind == "int":
        if value is None or value == "":
            if spec.nullable:
                return None
            raise ValidationFailed(f"{spec.label} is required.")
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValidationFailed(f"{spec.label} must be a whole number.")
        if spec.minimum is not None and value < spec.minimum:
            raise ValidationFailed(f"{spec.label} must be at least {spec.minimum}.")
        if spec.maximum is not None and value > spec.maximum:
            raise ValidationFailed(f"{spec.label} must be at most {spec.maximum}.")
        return value
    if not isinstance(value, str):
        raise ValidationFailed(f"{spec.label} must be text.")
    value = value.strip()
    if spec.max_length is not None and len(value) > spec.max_length:
        raise ValidationFailed(f"{spec.label} must be at most {spec.max_length} characters.")
    return value


class PlatformSettings:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def values(self, *, fresh: bool = False) -> dict[str, Any]:
        global _cache
        now = time.monotonic()
        if not fresh and _cache is not None and now - _cache[0] < CACHE_SECONDS:
            return dict(_cache[1])
        stored = {row.key: row.value for row in await self.db.scalars(select(PlatformSetting))}
        values = {key: stored.get(key, spec.default) for key, spec in SPECS.items()}
        _cache = (now, values)
        return dict(values)

    async def get(self, key: str) -> Any:
        return (await self.values())[key]

    async def rows(self) -> list[PlatformSetting]:
        return list(await self.db.scalars(select(PlatformSetting)))

    async def update(
        self, changes: dict[str, Any], *, actor_id: uuid.UUID
    ) -> dict[str, tuple[Any, Any]]:
        """Apply validated changes; returns {key: (old, new)} for what actually changed."""
        unknown = sorted(set(changes) - set(SPECS))
        if unknown:
            raise ValidationFailed(f"Unknown setting: {', '.join(unknown)}.")
        current = await self.values(fresh=True)
        diff: dict[str, tuple[Any, Any]] = {}
        for key, raw in changes.items():
            value = _coerce(SPECS[key], raw)
            if value == current[key]:
                continue
            row = await self.db.get(PlatformSetting, key)
            if row is None:
                row = PlatformSetting(key=key)
                self.db.add(row)
            row.value, row.updated_by, row.updated_at = value, actor_id, utcnow()
            diff[key] = (current[key], value)
        await self.db.flush()
        invalidate_cache()
        return diff


# --- enforcement helpers -------------------------------------------------------------------------


class FeatureDisabled(APIError):
    status_code = 403
    code = "FEATURE_DISABLED"


async def require_feature(db: AsyncSession, key: str, message: str) -> None:
    if not await PlatformSettings(db).get(key):
        raise FeatureDisabled(message)


async def enforce_ai_daily_limit(db: AsyncSession, user_id: uuid.UUID) -> None:
    from datetime import timedelta

    from app.core.exceptions import RateLimited
    from app.models.ai import AIRun

    limit = await PlatformSettings(db).get("ai_daily_requests_per_user")
    if not limit:
        return
    since = utcnow() - timedelta(days=1)
    used = await db.scalar(
        select(func.count(AIRun.id)).where(AIRun.user_id == user_id, AIRun.created_at >= since)
    )
    if int(used or 0) >= int(limit):
        raise RateLimited(
            "You've reached today's AI request limit. Try again tomorrow.", code="AI_DAILY_LIMIT"
        )


async def enforce_automation_limit(db: AsyncSession, user_id: uuid.UUID) -> None:
    from app.models.automation import Automation

    limit = await PlatformSettings(db).get("automations_max_per_user")
    if not limit:
        return
    count = await db.scalar(select(func.count(Automation.id)).where(Automation.user_id == user_id))
    if int(count or 0) >= int(limit):
        raise ValidationFailed(
            f"You can have at most {limit} automations. Delete one to add another.",
            code="AUTOMATION_LIMIT",
        )
