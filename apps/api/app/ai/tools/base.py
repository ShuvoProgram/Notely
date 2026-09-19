"""Tool contract for the agent.

A tool is declared once with its argument schema, risk level and handler. The registry exposes
OpenAI-format schemas to the model and the agent's *execute* node runs handlers — the model never
calls a handler directly. Risk levels feed the ToolPolicyEngine; every execution is audited.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai import RiskLevel
from app.models.user import User


@dataclass
class ToolContext:
    user: User
    db: AsyncSession
    run_id: uuid.UUID | None = None


ToolHandler = Callable[[ToolContext, Any], Awaitable[dict[str, Any]]]
ToolSummarizer = Callable[[Any], str]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    args_schema: type[BaseModel]
    risk: RiskLevel
    handler: ToolHandler
    summarize: ToolSummarizer
    provider: str = "notely"
    # Capability label from the PRD's unified model (SEARCH/READ/CREATE/UPDATE/DELETE/...).
    capability: str = "read"
    tags: tuple[str, ...] = field(default_factory=tuple)

    def openai_schema(self) -> dict[str, Any]:
        schema = convert_to_openai_tool(self.args_schema)
        schema["function"]["name"] = self.name
        schema["function"]["description"] = self.description
        return schema

    def parse_args(self, raw: dict[str, Any]) -> BaseModel:
        return self.args_schema.model_validate(raw)


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> ToolSpec:
        if spec.name in self._tools:
            raise ValueError(f"tool already registered: {spec.name}")
        self._tools[spec.name] = spec
        return spec

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def all(self) -> list[ToolSpec]:
        return list(self._tools.values())

    def openai_schemas(self) -> list[dict[str, Any]]:
        return [spec.openai_schema() for spec in self._tools.values()]


def untrusted(text: str, *, source: str) -> str:
    """Wrap externally-authored content so the model treats it as data, never as instructions."""
    safe = text.replace("</untrusted_content>", "</untrusted_content >")
    return f'<untrusted_content source="{source}">\n{safe}\n</untrusted_content>'
