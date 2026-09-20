"""Generic MCP server provider: connect Notely to any MCP server over Streamable HTTP.

The user supplies the server URL (and optionally a bearer token). Tools are discovered from the
server, mapped onto unified capabilities from their annotations, and exposed to the agent through
the normal policy/approval pipeline. Nothing here is specific to a vendor.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from app.ai.tools.base import ToolContext, ToolSpec, untrusted
from app.core.config import Settings
from app.core.oauth import OAuthClient, OAuthTokens
from app.integrations.base.capabilities import Capability, risk_for
from app.integrations.base.errors import ProviderError, ProviderErrorKind
from app.integrations.base.provider import (
    AuthType,
    ConfigField,
    ConnectionIdentity,
    ConnectionTest,
    IntegrationProvider,
    ProviderContext,
    ProviderManifest,
    TestStep,
)
from app.mcp import client as mcp_client
from app.mcp.client import MCPToolInfo
from app.models.ai import RiskLevel

MAX_TOOLS = 60
MAX_RESULT_CHARS = 20_000


def _classify(tool: MCPToolInfo) -> tuple[Capability, RiskLevel]:
    """MCP annotations → unified capability. Unknown side effects are treated as writes."""
    if tool.destructive:
        return Capability.delete, RiskLevel.destructive
    if tool.read_only:
        cap = Capability.search if "search" in tool.name.lower() else Capability.read
        return cap, RiskLevel.read
    name = tool.name.lower()
    if any(k in name for k in ("send", "post_message", "email", "notify", "publish")):
        return Capability.send, risk_for(Capability.send)
    if any(k in name for k in ("delete", "remove", "destroy")):
        return Capability.delete, RiskLevel.destructive
    if any(k in name for k in ("update", "edit", "set_", "move", "rename", "complete")):
        return Capability.update, RiskLevel.write
    return Capability.create, RiskLevel.write


class MCPServerProvider(IntegrationProvider):
    manifest = ProviderManifest(
        id="mcp_server",
        name="MCP server",
        category="developer",
        description=(
            "Connect any Model Context Protocol server over HTTP. Its tools become available to "
            "the assistant with the same review rules as everything else."
        ),
        docs_url="https://modelcontextprotocol.io",
        auth=AuthType.token,
        capabilities=[
            Capability.search,
            Capability.read,
            Capability.create,
            Capability.update,
            Capability.delete,
        ],
        config_fields=[
            ConfigField(
                key="server_url",
                label="Server URL",
                kind="url",
                placeholder="https://mcp.example.com/mcp",
                help="The Streamable HTTP endpoint of the MCP server.",
            ),
            ConfigField(
                key="token",
                label="Access token",
                kind="secret",
                required=False,
                help="Sent as a Bearer token if the server requires one. Stored encrypted.",
            ),
        ],
    )

    def connect_methods(self, settings: Settings) -> list[str]:
        if self.manifest.id == "mcp_server":
            # Custom server: the user types a URL, Notely discovers OAuth (or none) — or a token.
            return ["mcp", "token"]
        return super().connect_methods(settings)

    # --- helpers --------------------------------------------------------------------------------

    @staticmethod
    def _url(ctx: ProviderContext) -> str:
        url = str(
            ctx.connection.metadata_.get("mcp_url") or ctx.connection.config.get("server_url", "")
        ).strip()
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ProviderError(
                ProviderErrorKind.invalid_request, "Invalid server URL", provider="mcp_server"
            )
        if (
            parsed.scheme == "http"
            and ctx.settings.is_production
            and parsed.hostname not in ("localhost", "127.0.0.1")
        ):
            raise ProviderError(
                ProviderErrorKind.invalid_request,
                "Server URL must use https",
                provider="mcp_server",
            )
        return url

    # --- lifecycle ------------------------------------------------------------------------------

    async def complete_connection(self, ctx: ProviderContext) -> ConnectionIdentity:
        url = self._url(ctx)
        async with mcp_client.connect(
            url, ctx.credentials.access_token, provider="mcp_server"
        ) as conn:
            tools = await conn.list_tools()
            info = conn.server_info
        ctx.connection.metadata_ = {
            **ctx.connection.metadata_,
            "server": info,
            "tools": [
                {
                    "name": t.name,
                    "description": t.description[:300],
                    "read_only": t.read_only,
                    "destructive": t.destructive,
                }
                for t in tools[:MAX_TOOLS]
            ],
        }
        return ConnectionIdentity(
            external_account_id=urlparse(url).netloc,
            external_account_name=info.get("name") or urlparse(url).netloc,
            metadata={"tool_count": len(tools)},
        )

    async def test_connection(self, ctx: ProviderContext) -> ConnectionTest:
        steps: list[TestStep] = []
        try:
            url = self._url(ctx)
            steps.append(TestStep("Configuration", True, url))
        except ProviderError as exc:
            return ConnectionTest([TestStep("Configuration", False, exc.detail or "Invalid URL")])
        try:
            async with mcp_client.connect(
                url, ctx.credentials.access_token, provider="mcp_server"
            ) as conn:
                steps.append(TestStep("Authentication", True, "Handshake succeeded"))
                steps.append(
                    TestStep(
                        "API availability", True, conn.server_info.get("name", "Server reachable")
                    )
                )
                tools = await conn.list_tools()
                steps.append(TestStep("Tool access", True, f"{len(tools)} tool(s) available"))
        except ProviderError as exc:
            failed = (
                "Authentication"
                if exc.kind in (ProviderErrorKind.auth_failed, ProviderErrorKind.expired)
                else "API availability"
            )
            steps.append(TestStep(failed, False, exc.user_message()[1]))
        return ConnectionTest(steps)

    # --- tools ----------------------------------------------------------------------------------

    def tool_prefix(self, ctx: ProviderContext) -> str:
        if self.manifest.id != "mcp_server":
            return self.manifest.id  # a known vendor: tools read as notion__search etc.
        return f"mcp_{_slug(str(ctx.connection.external_account_name or ctx.connection.id))}"

    async def refresh_credentials(self, ctx: ProviderContext) -> OAuthTokens | None:
        """Tokens issued by the server's authorization server refresh through the client this
        deployment registered there; token-based connections have nothing to refresh."""
        if not ctx.credentials.refresh_token:
            return None
        from app.mcp import oauth as mcp_oauth

        auth = await mcp_oauth.discover(self._url(ctx))
        if auth is None:
            return None
        redirect = (
            f"{ctx.settings.api_public_url.rstrip('/')}{ctx.settings.api_prefix}"
            f"/oauth/{self.manifest.id}/callback"
        )
        config = await mcp_oauth.dynamic_client(
            ctx.db, ctx.settings, auth, redirect, self.manifest.id
        )
        try:
            return await OAuthClient(config, redirect).refresh(ctx.credentials.refresh_token)
        except Exception as exc:  # noqa: BLE001 — refresh failures always mean re-consent
            raise ProviderError(ProviderErrorKind.expired, provider=self.manifest.id) from exc

    async def tools(self, ctx: ProviderContext) -> list[ToolSpec]:
        cached = ctx.connection.metadata_.get("tools")
        if not isinstance(cached, list):
            return []
        url = self._url(ctx)
        connection_id = ctx.connection.id
        prefix = self.tool_prefix(ctx)
        specs: list[ToolSpec] = []
        # Tool schemas need a live listing; cached metadata only tells us names/hints.
        async with mcp_client.connect(
            url, ctx.credentials.access_token, provider="mcp_server"
        ) as conn:
            live = {t.name: t for t in await conn.list_tools()}
        for entry in cached[:MAX_TOOLS]:
            info = live.get(str(entry.get("name")))
            if info is None:
                continue
            capability, risk = _classify(info)
            specs.append(
                ToolSpec(
                    name=f"{prefix}__{_slug(info.name)}",
                    description=f"[{ctx.connection.external_account_name}] {info.description}"[
                        :1000
                    ],
                    json_schema=info.input_schema,
                    risk=risk,
                    capability=capability.value,
                    provider=self.manifest.id,
                    connection_id=connection_id,
                    handler=_make_handler(url, info.name),
                    summarize=_make_summary(
                        str(ctx.connection.external_account_name or "MCP"), info.name
                    ),
                )
            )
        return specs


class MCPModeAdapter(MCPServerProvider):
    """A vendor connection made through the vendor's official MCP server (one-click OAuth).

    Wraps the vendor's manifest so ids, labels and audit rows still say "notion"/"linear",
    while connect/test/tools/refresh go through MCP and the dynamically registered client."""

    def __init__(self, manifest: ProviderManifest) -> None:
        self.manifest = manifest


def _slug(value: str) -> str:
    out = "".join(ch if ch.isalnum() else "_" for ch in value.lower()).strip("_")
    return out[:40] or "server"


def _make_summary(server: str, tool: str):  # type: ignore[no-untyped-def]
    def summarize(args: Any) -> str:
        return f"{tool.replace('_', ' ')} on {server}"

    return summarize


def _make_handler(url: str, tool_name: str):  # type: ignore[no-untyped-def]
    async def handler(tool_ctx: ToolContext, args: Any) -> dict[str, Any]:
        # Credentials are resolved by the framework and attached to the ToolContext.
        token = tool_ctx.credential
        async with mcp_client.connect(url, token, provider="mcp_server") as conn:
            result = await conn.call_tool(tool_name, dict(args) if isinstance(args, dict) else {})
        text = str(result.get("text", ""))[:MAX_RESULT_CHARS]
        out: dict[str, Any] = {}
        if text:
            out["content"] = untrusted(text, source=f"mcp:{tool_name}")
        if "structured" in result:
            out["structured"] = result["structured"]
        return out

    return handler
