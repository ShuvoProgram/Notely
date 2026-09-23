"""Tool contract for the agent.

A tool is declared once with its argument schema, risk level and handler. The registry exposes
OpenAI-format schemas to the model and the agent's *execute* node runs handlers — the model never
calls a handler directly. Risk levels feed the ToolPolicyEngine; every execution is audited.

Arguments are described either by a pydantic model (internal tools) or by a raw JSON schema
(tools discovered at runtime from MCP servers). Handlers receive the parsed model or the
validated dict respectively.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import jsonschema
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
    # For provider tools: the decrypted access token, resolved by the framework just-in-time.
    credential: str | None = None


ToolHandler = Callable[[ToolContext, Any], Awaitable[dict[str, Any]]]
ToolSummarizer = Callable[[Any], str]


@dataclass(frozen=True)
class Verification:
    """Outcome of checking that a write actually happened.

    `verified`   – a read-back found the created/updated object.
    `unverified` – the provider accepted the write but exposes no way to read it back.
    `failed`     – the read-back ran and did not find (or contradicted) the change.
    """

    status: str  # verified | unverified | failed
    detail: str

    @classmethod
    def verified(cls, detail: str) -> Verification:
        return cls("verified", detail)

    @classmethod
    def unverified(cls, detail: str) -> Verification:
        return cls("unverified", detail)

    @classmethod
    def failed(cls, detail: str) -> Verification:
        return cls("failed", detail)

    def to_dict(self) -> dict[str, str]:
        return {"status": self.status, "detail": self.detail}


# (context, parsed args, handler result) -> Verification. Runs after a successful write.
ToolVerifier = Callable[[ToolContext, Any, dict[str, Any]], Awaitable[Verification]]


@dataclass(frozen=True)
class OutputField:
    """One piece of data a tool returns, described for people (automation "Insert data").

    `fields` describes the items of a list (or the keys of an object) so a workflow can use
    "the first message's subject" without anyone reading raw data.
    """

    key: str
    label: str
    type: str = "text"  # text | long_text | number | date | boolean | url | list | object
    fields: tuple[OutputField, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"key": self.key, "label": self.label, "type": self.type}
        if self.fields:
            out["fields"] = [f.to_dict() for f in self.fields]
        return out


class ToolArgumentError(ValueError):
    pass


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    risk: RiskLevel
    handler: ToolHandler
    summarize: ToolSummarizer
    args_schema: type[BaseModel] | None = None
    json_schema: dict[str, Any] | None = None
    provider: str = "notely"
    # Capability label from the PRD's unified model (search/read/create/update/delete/...).
    capability: str = "read"
    # Set for provider tools so execution can load the right credentials.
    connection_id: uuid.UUID | None = None
    tags: tuple[str, ...] = field(default_factory=tuple)
    # Optional read-back for write tools; the framework runs it and reports the outcome.
    verify: ToolVerifier | None = None
    # What the tool returns, for automations. Empty means "discover from a test run".
    outputs: tuple[OutputField, ...] = ()

    def __post_init__(self) -> None:
        if (self.args_schema is None) == (self.json_schema is None):
            raise ValueError("ToolSpec needs exactly one of args_schema or json_schema")

    def openai_schema(self) -> dict[str, Any]:
        if self.args_schema is not None:
            schema = convert_to_openai_tool(self.args_schema)
            schema["function"]["name"] = self.name
            schema["function"]["description"] = self.description
            return schema
        params = dict(self.json_schema or {"type": "object", "properties": {}})
        params.setdefault("type", "object")
        params.setdefault("properties", {})
        return {
            "type": "function",
            "function": {"name": self.name, "description": self.description, "parameters": params},
        }

    def parse_args(self, raw: dict[str, Any]) -> Any:
        """Validate model-provided arguments. Raises ToolArgumentError with a readable message."""
        if self.args_schema is not None:
            from pydantic import ValidationError

            try:
                return self.args_schema.model_validate(raw)
            except ValidationError as exc:
                problems = "; ".join(
                    f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()
                )
                raise ToolArgumentError(problems) from exc
        try:
            jsonschema.validate(raw, self.json_schema or {"type": "object"})
        except jsonschema.ValidationError as exc:
            path = ".".join(str(p) for p in exc.absolute_path) or "_"
            raise ToolArgumentError(f"{path}: {exc.message}") from exc
        return raw


def args_to_dict(args: Any) -> dict[str, Any]:
    if isinstance(args, BaseModel):
        return args.model_dump(mode="json")
    return dict(args) if isinstance(args, dict) else {}


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> ToolSpec:
        if spec.name in self._tools:
            raise ValueError(f"tool already registered: {spec.name}")
        self._tools[spec.name] = spec
        return spec

    def extend(self, specs: list[ToolSpec]) -> None:
        for spec in specs:
            self.register(spec)

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
