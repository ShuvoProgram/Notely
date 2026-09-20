"""Where an adapter's OAuth client credentials come from.

Order: the workspace's own app (entered in Settings → Connections, stored encrypted) beats the
deployment-wide `OAUTH_<PREFIX>_*` settings. The service loads the workspace's apps into a
context variable before any provider method runs, so adapters stay synchronous and unaware of
the database."""

from __future__ import annotations

import contextvars

from app.core.config import Settings

Override = tuple[str, str]  # (client_id, client_secret)

_overrides: contextvars.ContextVar[dict[str, Override] | None] = contextvars.ContextVar(
    "oauth_app_overrides", default=None
)


def set_overrides(apps: dict[str, Override]) -> None:
    _overrides.set(dict(apps))


def current_overrides() -> dict[str, Override]:
    return _overrides.get() or {}


def client_credentials(settings: Settings, prefix: str) -> Override | None:
    override = current_overrides().get(prefix)
    if override and override[0] and override[1]:
        return override
    client_id = getattr(settings, f"oauth_{prefix}_client_id", "")
    client_secret = getattr(settings, f"oauth_{prefix}_client_secret", "")
    if client_id and client_secret:
        return (str(client_id), str(client_secret))
    return None


def is_workspace_app(prefix: str) -> bool:
    return prefix in current_overrides()
