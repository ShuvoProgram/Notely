"""Provider registry. Adding a provider = adding an adapter module and one line here; the UI
reads provider metadata from the backend, and the AI core never learns provider specifics."""

from __future__ import annotations

from functools import lru_cache

from app.integrations.base.provider import IntegrationProvider
from app.integrations.mcp_server.provider import MCPServerProvider

PROVIDER_CLASSES: dict[str, type[IntegrationProvider]] = {
    "mcp_server": MCPServerProvider,
}


@lru_cache
def get_providers() -> dict[str, IntegrationProvider]:
    return {pid: cls() for pid, cls in PROVIDER_CLASSES.items()}


def get_provider(provider_id: str) -> IntegrationProvider | None:
    return get_providers().get(provider_id)


def register_provider(provider: IntegrationProvider) -> None:
    """Runtime registration (tests, plugins). Clears the cached mapping."""
    PROVIDER_CLASSES[provider.manifest.id] = type(provider)
    get_providers.cache_clear()
    get_providers()[provider.manifest.id] = provider


def unregister_provider(provider_id: str) -> None:
    PROVIDER_CLASSES.pop(provider_id, None)
    get_providers.cache_clear()
