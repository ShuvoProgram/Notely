"""The per-user capability catalog: every action this user can put in an automation.

Built-in Notely and AI actions are always present. Connector actions come from the tools of
the user's *usable* connections, filtered by the permissions actually granted — exactly what
the chat assistant is offered — so the builder, the AI planner and the engine can never
disagree about what is possible.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from typing import Any

from sqlalchemy import select

from app.ai.tools.base import ToolContext, ToolSpec
from app.automation.actions import ActionContext, ActionDefinition, ActionError, InputField, Safety
from app.automation.mapping import to_text, unwrap
from app.automation.native import native_actions
from app.integrations.base.capabilities import risk_for
from app.integrations.base.errors import ProviderError
from app.integrations.base.rest import RestOAuthProvider
from app.integrations.registry import get_providers
from app.models.ai import RiskLevel
from app.models.integration import ConnectionStatus, UserConnection

BUILTIN_APPS: dict[str, dict[str, Any]] = {
    "notely": {"name": "Notely", "logo": None, "category": "notely"},
    "ai": {"name": "AI", "logo": None, "category": "ai"},
}
_SAFETY: dict[RiskLevel, Safety] = {
    RiskLevel.read: "safe",
    RiskLevel.write: "ask",
    RiskLevel.external_communication: "ask",
    RiskLevel.destructive: "always_ask",
}
_BROKEN = {ConnectionStatus.needs_attention, ConnectionStatus.expired, ConnectionStatus.error}
_LONG_TEXT_KEYS = {
    "body",
    "content",
    "text",
    "message",
    "description",
    "notes",
    "agenda",
    "comment",
}


def _humanize(name: str) -> str:
    words = name.replace("_", " ").strip()
    return words[:1].upper() + words[1:]


def _plain_description(spec: ToolSpec) -> str:
    return re.sub(r"^\[[^\]]+\]\s*", "", spec.description).strip()


def _field_from_schema(key: str, raw: dict[str, Any], required: bool) -> InputField:
    schema = raw
    if isinstance(raw.get("anyOf"), list):  # Optional[...] in pydantic's JSON schema
        schema = next((s for s in raw["anyOf"] if s.get("type") != "null"), raw)
    kind = schema.get("type")
    label = str(raw.get("title") or _humanize(key))
    help_text = raw.get("description") or schema.get("description")
    options: tuple[tuple[str, str], ...] = ()
    field_type = "text"
    if schema.get("enum"):
        field_type = "choice"
        options = tuple((str(v), _humanize(str(v))) for v in schema["enum"])
    elif kind in ("integer", "number"):
        field_type = "number"
    elif kind == "boolean":
        field_type = "boolean"
    elif kind == "array":
        field_type = "list"
    elif schema.get("format") == "date-time":
        field_type = "datetime"
    elif schema.get("format") == "date":
        field_type = "date"
    elif key in _LONG_TEXT_KEYS or (schema.get("maxLength") or 0) > 500:
        field_type = "long_text"
    elif "email" in key or schema.get("format") == "email":
        field_type = "email"
    default = raw.get("default", schema.get("default"))
    return InputField(
        key=key,
        label=label,
        type=field_type,
        required=required,
        help=str(help_text) if help_text else None,
        options=options,
        default=default if isinstance(default, (str, int, float, bool)) else None,
    )


def fields_from_schema(schema: dict[str, Any]) -> tuple[InputField, ...]:
    required = set(schema.get("required") or [])
    properties = schema.get("properties") or {}
    return tuple(
        _field_from_schema(key, raw if isinstance(raw, dict) else {}, key in required)
        for key, raw in properties.items()
    )


def _schema_of(raw: dict[str, Any]) -> dict[str, Any]:
    if isinstance(raw.get("anyOf"), list):
        return next((s for s in raw["anyOf"] if s.get("type") != "null"), raw)
    return raw


def coerce(value: Any, raw_schema: dict[str, Any]) -> Any:
    """Shape a mapped value like the tool expects: one line per list item, a single value as a
    one-cell row for list-of-rows inputs (Sheets), numbers from text, text from records."""
    schema = _schema_of(raw_schema or {})
    kind = schema.get("type")
    if kind == "array":
        items = _schema_of(schema.get("items") or {})
        if isinstance(value, str):
            lines = [line.strip() for line in value.split("\n") if line.strip()]
            value = [lines] if items.get("type") == "array" else lines
        elif not isinstance(value, list):
            value = [value]
        if items.get("type") == "array":
            # The builder shows a row as "cell | cell"; turn that back into cells.
            value = [
                row
                if isinstance(row, list)
                else [c.strip() for c in row.split(" | ")]
                if isinstance(row, str)
                else [row]
                for row in value
            ]
        return [coerce(item, items) for item in value]
    if kind in ("integer", "number") and isinstance(value, str) and value.strip():
        try:
            number = float(value)
            return int(number) if kind == "integer" else number
        except ValueError:
            return value
    if kind == "string" and isinstance(value, (list, dict)):
        return to_text(value)
    if kind == "string" and isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    if kind == "object" and isinstance(value, dict):
        props = schema.get("properties") or {}
        return {k: coerce(v, props.get(k, {})) for k, v in value.items()}
    return value


def _provider_handler(provider_id: str, tool_name: str) -> Any:
    """Run a connector tool with fresh credentials; the ToolSpec is re-resolved per run."""

    async def handler(ctx: ActionContext, inputs: dict[str, Any]) -> dict[str, Any]:
        connection = await ctx.connections.get_by_provider(ctx.user, provider_id)
        name = get_providers().get(provider_id)
        app_name = name.manifest.name if name else provider_id
        fix = f"/app/settings/connections/{provider_id}"
        if connection is None:
            raise ActionError(f"Connect {app_name} to run this step.", fix_path=fix)
        if not connection.is_usable:
            raise ActionError(f"{app_name} needs to be reconnected.", fix_path=fix)
        await ctx.connections.refresh_if_needed(ctx.user, connection)
        adapter = ctx.connections.adapter(connection)
        tools = await adapter.tools(ctx.connections.context(ctx.user, connection))
        spec = next((t for t in tools if t.name == f"{provider_id}__{tool_name}"), None)
        if spec is None:
            raise ActionError(
                f"{app_name} no longer allows this action. Reconnect {app_name} and grant the "
                "permission it needs.",
                fix_path=fix,
            )
        properties = spec.openai_schema()["function"]["parameters"].get("properties") or {}
        clean = {
            k: coerce(v, properties.get(k, {})) for k, v in inputs.items() if v not in (None, "")
        }
        try:
            parsed = spec.parse_args(clean)
        except ValueError as exc:
            raise ActionError(
                f"Some details for this {app_name} step are missing or invalid: {exc}"
            ) from exc
        credential = ctx.connections.vault.load(connection).access_token
        tool_ctx = ToolContext(user=ctx.user, db=ctx.db, credential=credential)
        try:
            result = await spec.handler(tool_ctx, parsed)
            if spec.verify is not None and spec.risk != RiskLevel.read:
                verification = await spec.verify(tool_ctx, parsed, result)
                if verification.status == "failed":
                    raise ActionError(
                        f"{app_name} accepted the change but it didn't stick: {verification.detail}"
                    )
                result["verified"] = verification.status == "verified"
        except ProviderError as exc:
            await ctx.connections.record_tool_failure(connection, exc, user=ctx.user)
            raise
        result.pop("sources", None)
        return unwrap(result)

    return handler


def _describer(spec: ToolSpec, tool_name: str) -> Callable[[dict[str, Any]], str]:
    def describe(args: dict[str, Any]) -> str:
        if spec.args_schema is None:
            return _humanize(tool_name)
        return spec.summarize(spec.args_schema.model_construct(**args))

    return describe


def provider_action(spec: ToolSpec) -> ActionDefinition:
    tool_name = spec.name.split("__", 1)[-1]
    schema = spec.openai_schema()["function"]["parameters"]
    return ActionDefinition(
        id=f"{spec.provider}.{tool_name}",
        app=spec.provider,
        label=_humanize(tool_name),
        description=_plain_description(spec),
        group="find" if spec.risk == RiskLevel.read else "do",
        safety=_SAFETY.get(spec.risk, "ask"),
        handler=_provider_handler(spec.provider, tool_name),
        inputs=fields_from_schema(schema),
        outputs=spec.outputs,
        writes=spec.risk != RiskLevel.read,
        describe=_describer(spec, tool_name),
    )


@dataclass
class Catalog:
    actions: dict[str, ActionDefinition]
    apps: list[dict[str, Any]]
    # Actions of apps offered on this deployment but not connected by this user.
    locked: dict[str, ActionDefinition] = field(default_factory=dict)

    def get(self, action_id: str) -> ActionDefinition | None:
        return self.actions.get(action_id)

    def app_info(self, app_id: str) -> dict[str, Any]:
        return next((a for a in self.apps if a["id"] == app_id), {"id": app_id, "name": app_id})

    def to_dict(self) -> dict[str, Any]:
        return {
            "apps": self.apps,
            "actions": [
                action.to_dict(
                    self.app_info(action.app)["name"], self.app_info(action.app).get("logo")
                )
                for action in [*self.actions.values(), *self.locked.values()]
            ],
        }


_NATIVE: dict[str, ActionDefinition] | None = None


def builtin_actions() -> dict[str, ActionDefinition]:
    global _NATIVE
    if _NATIVE is None:
        _NATIVE = {action.id: action for action in native_actions()}
    return _NATIVE


async def _never(_: ToolContext, __: Any) -> dict[str, Any]:  # pragma: no cover
    raise ActionError("Connect this app first.")


def locked_actions(provider: Any) -> list[ActionDefinition]:
    """Describe an unconnected REST connector's actions from its static tool list."""
    if not isinstance(provider, RestOAuthProvider):
        return []  # MCP-backed apps only reveal their tools once connected
    manifest = provider.manifest
    out: list[ActionDefinition] = []
    for tool in provider.build_tools():
        spec = ToolSpec(
            name=f"{manifest.id}__{tool.name}",
            description=f"[{manifest.name}] {tool.description}",
            args_schema=tool.args_model,
            risk=risk_for(tool.capability),
            handler=_never,
            summarize=tool.summarize,
            provider=manifest.id,
            capability=tool.capability.value,
            outputs=tool.outputs,
        )
        out.append(replace(provider_action(spec), available=False))
    return out


async def build_catalog(ctx: ActionContext) -> Catalog:
    actions = dict(builtin_actions())
    usable = {c.provider: c for c in await ctx.connections.list_usable(ctx.user)}
    for spec in await ctx.connections.tools_for_user(ctx.user):
        action = provider_action(spec)
        actions.setdefault(action.id, action)
    rows = await ctx.db.scalars(select(UserConnection).where(UserConnection.user_id == ctx.user.id))
    all_connections = {c.provider: c for c in rows}
    apps: list[dict[str, Any]] = [
        {"id": app_id, **info, "connected": True, "status": "connected", "connect_path": None}
        for app_id, info in BUILTIN_APPS.items()
    ]
    for provider_id, provider in get_providers().items():
        if provider_id == "mcp_server":
            continue
        connection = all_connections.get(provider_id)
        if provider_id in usable:
            status = "connected"
        elif connection is not None and connection.status in _BROKEN:
            status = "needs_attention"
        elif provider.is_configured(ctx.settings) or provider.manifest.mcp_server_url:
            status = "not_connected"
        else:
            continue  # not offered on this deployment at all
        apps.append(
            {
                "id": provider_id,
                "name": provider.manifest.name,
                "logo": provider.manifest.logo_url,
                "category": provider.manifest.category,
                "connected": status == "connected",
                "status": status,
                "connect_path": f"/app/settings/connections/{provider_id}",
            }
        )
    locked: dict[str, ActionDefinition] = {}
    for app in apps:
        if app["status"] in ("not_connected", "needs_attention"):
            for action in locked_actions(get_providers()[app["id"]]):
                if action.id not in actions:
                    locked[action.id] = action
    return Catalog(actions=actions, apps=apps, locked=locked)


async def resolve_action(ctx: ActionContext, action_id: str) -> ActionDefinition:
    """One action for execution, without listing every connection's tools."""
    builtin = builtin_actions().get(action_id)
    if builtin is not None:
        return builtin
    provider_id, _, tool_name = action_id.partition(".")
    provider = get_providers().get(provider_id)
    if provider is None:
        raise ActionError("This step uses an app Notely doesn't support.")
    connection = await ctx.connections.get_by_provider(ctx.user, provider_id)
    fix = f"/app/settings/connections/{provider_id}"
    if connection is None:
        raise ActionError(f"Connect {provider.manifest.name} to run this step.", fix_path=fix)
    if not connection.is_usable:
        raise ActionError(f"{provider.manifest.name} needs to be reconnected.", fix_path=fix)
    await ctx.connections.refresh_if_needed(ctx.user, connection)
    tools = await ctx.connections.adapter(connection).tools(
        ctx.connections.context(ctx.user, connection)
    )
    spec = next((t for t in tools if t.name == f"{provider_id}__{tool_name}"), None)
    if spec is None:
        raise ActionError(
            f"{provider.manifest.name} can't do this with the permissions you granted. "
            f"Reconnect {provider.manifest.name} to allow it.",
            fix_path=fix,
        )
    return provider_action(spec)
