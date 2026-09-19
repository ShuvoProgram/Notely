"""Tool registry. Integrations (Phase 4/5) register their tools here via their adapters."""

from functools import lru_cache

from app.ai.tools.base import ToolContext, ToolRegistry, ToolSpec, untrusted
from app.ai.tools.notely_tools import register_notely_tools


@lru_cache
def get_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    register_notely_tools(registry)
    return registry


__all__ = ["ToolContext", "ToolRegistry", "ToolSpec", "get_tool_registry", "untrusted"]
