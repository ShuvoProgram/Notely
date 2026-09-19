"""Tool registry. Integrations (Phase 4/5) register their tools here via their adapters."""

from functools import lru_cache

from app.ai.tools.base import ToolContext, ToolRegistry, ToolSpec, untrusted
from app.ai.tools.notely_tools import register_notely_tools


@lru_cache
def get_tool_registry() -> ToolRegistry:
    """Built-in Notely tools only (static)."""
    registry = ToolRegistry()
    register_notely_tools(registry)
    return registry


def build_registry(extra: list[ToolSpec]) -> ToolRegistry:
    """Built-in tools plus tools discovered from a user's connected providers."""
    registry = ToolRegistry()
    register_notely_tools(registry)
    for spec in extra:
        if registry.get(spec.name) is None:
            registry.register(spec)
    return registry


__all__ = [
    "ToolContext",
    "ToolRegistry",
    "ToolSpec",
    "build_registry",
    "get_tool_registry",
    "untrusted",
]
