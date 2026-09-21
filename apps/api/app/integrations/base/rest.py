"""Shared base for OAuth2 + REST providers. Adapters declare endpoints, scopes and tools; this
class handles client configuration, token refresh, the HTTP client and the standard health test."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from app.ai.tools.base import ToolContext, ToolSpec, Verification, untrusted
from app.core.config import Settings
from app.core.exceptions import OAuthExchangeFailed
from app.core.oauth import (
    OAuthClient,
    OAuthClientConfig,
    OAuthEndpoints,
    OAuthTokens,
    callback_uri,
)
from app.integrations.base.capabilities import Capability, risk_for
from app.integrations.base.errors import ProviderError, ProviderErrorKind
from app.integrations.base.http import ProviderHttpClient
from app.integrations.base.provider import (
    ConnectionIdentity,
    ConnectionTest,
    IntegrationProvider,
    ProviderContext,
    TestStep,
)

Handler = Callable[[ProviderContext, Any], Awaitable[dict[str, Any]]]
Verifier = Callable[[ProviderContext, Any, dict[str, Any]], Awaitable[Verification]]


log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProviderTool:
    """One tool an adapter exposes. `verify` (write tools) reads the object back after the
    write so the assistant can say "created and verified" rather than assuming."""

    name: str
    description: str
    args_model: type[BaseModel]
    capability: Capability
    handler: Handler
    summarize: Callable[[Any], str]
    verify: Verifier | None = None
    # The OAuth scope this tool needs. When the connection's granted scopes are known and do
    # not include it (an optional permission the user declined), the tool is not offered to
    # the assistant at all — never advertise what the provider would refuse.
    scope: str | None = None


class RestOAuthProvider(IntegrationProvider):
    """Subclasses set `settings_prefix`, `endpoints`, `use_pkce`, `api_base` and implement
    `identity`, `probe` and `build_tools`."""

    settings_prefix: str
    endpoints: OAuthEndpoints
    use_pkce: bool = True
    api_base: str = ""
    api_headers: dict[str, str] = {}
    token_parser: Callable[[dict[str, Any]], OAuthTokens] | None = None

    # --- configuration ----------------------------------------------------------------------

    def oauth_config(self, settings: Settings) -> OAuthClientConfig | None:
        client_id = getattr(settings, f"oauth_{self.settings_prefix}_client_id", "")
        client_secret = getattr(settings, f"oauth_{self.settings_prefix}_client_secret", "")
        if not client_id or not client_secret:
            return None
        return OAuthClientConfig(
            provider_id=self.manifest.id,
            client_id=client_id,
            client_secret=client_secret,
            scopes=tuple(self.scopes_for(None)),
            endpoints=self.endpoints,
            use_pkce=self.use_pkce,
            token_parser=self.token_parser,
        )

    def _oauth_client(self, ctx: ProviderContext) -> OAuthClient:
        config = self.oauth_config(ctx.settings)
        if config is None:
            raise ProviderError(ProviderErrorKind.misconfigured, provider=self.manifest.id)
        # Same callback slot as the connect flow (one redirect URI per vendor family).
        from dataclasses import replace

        return OAuthClient(
            replace(config, provider_id=self.settings_prefix),
            callback_uri(ctx.settings, f"/oauth/{self.settings_prefix}/callback"),
        )

    # --- HTTP -----------------------------------------------------------------------------------

    def http(self, ctx: ProviderContext, base_url: str | None = None) -> ProviderHttpClient:
        token = ctx.credentials.access_token
        if not token:
            raise ProviderError(
                ProviderErrorKind.expired, "no access token", provider=self.manifest.id
            )
        return ProviderHttpClient(
            provider=self.manifest.id,
            base_url=base_url or self.api_base,
            bearer_token=token,
            headers=self.api_headers,
        )

    # --- lifecycle ------------------------------------------------------------------------------

    async def refresh_credentials(self, ctx: ProviderContext) -> OAuthTokens | None:
        if not ctx.credentials.refresh_token:
            return None
        try:
            return await self._oauth_client(ctx).refresh(ctx.credentials.refresh_token)
        except OAuthExchangeFailed as exc:
            # Only a rejected grant means the user has to consent again. A vendor outage or a
            # network blip is reported as such so the connection is not torn down for nothing.
            if exc.transient or not exc.grant_rejected and exc.oauth_error is None:
                raise ProviderError(
                    ProviderErrorKind.unavailable,
                    "token refresh unavailable",
                    provider=self.manifest.id,
                ) from exc
            if exc.oauth_error == "invalid_client":
                raise ProviderError(
                    ProviderErrorKind.misconfigured,
                    "oauth client rejected",
                    provider=self.manifest.id,
                ) from exc
            raise ProviderError(
                ProviderErrorKind.expired,
                exc.oauth_error or "refresh rejected",
                provider=self.manifest.id,
            ) from exc
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "token_refresh_failed",
                extra={"provider": self.manifest.id, "reason": f"{type(exc).__name__}: {exc}"},
            )
            raise ProviderError(
                ProviderErrorKind.unavailable, type(exc).__name__, provider=self.manifest.id
            ) from exc

    async def complete_connection(self, ctx: ProviderContext) -> ConnectionIdentity:
        return await self.identity(ctx)

    async def test_connection(self, ctx: ProviderContext) -> ConnectionTest:
        steps: list[TestStep] = []
        try:
            who = await self.identity(ctx)
            steps.append(TestStep("Authentication", True, who.external_account_name or "OK"))
        except ProviderError as exc:
            return ConnectionTest([TestStep("Authentication", False, exc.user_message()[1])])
        required = {p.scope for p in self.manifest.permissions if p.required}
        granted = set(ctx.connection.scopes)
        missing = sorted(required - granted) if granted else []
        steps.append(
            TestStep(
                "Permissions",
                not missing,
                "All required permissions granted"
                if not missing
                else f"Missing: {', '.join(missing)}",
            )
        )
        try:
            detail = await self.probe(ctx)
            steps.append(TestStep("API availability", True, detail))
        except ProviderError as exc:
            steps.append(TestStep("API availability", False, exc.user_message()[1]))
        try:
            tools = await self.tools(ctx)
            steps.append(TestStep("Tool access", True, f"{len(tools)} tool(s) available"))
        except ProviderError as exc:
            steps.append(TestStep("Tool access", False, exc.user_message()[1]))
        return ConnectionTest(steps)

    # --- to implement -----------------------------------------------------------------------------

    async def identity(self, ctx: ProviderContext) -> ConnectionIdentity:
        raise NotImplementedError

    async def probe(self, ctx: ProviderContext) -> str:
        """A harmless read that proves the API is reachable. Returns a short human detail."""
        raise NotImplementedError

    def build_tools(self) -> list[ProviderTool]:
        raise NotImplementedError

    def tool_available(self, tool: ProviderTool, granted: list[str]) -> bool:
        if tool.scope is None or not granted:
            return True
        return tool.scope in granted

    async def tools(self, ctx: ProviderContext) -> list[ToolSpec]:
        specs: list[ToolSpec] = []
        granted = list(ctx.connection.scopes or [])
        for tool in self.build_tools():
            if not self.tool_available(tool, granted):
                continue
            specs.append(
                ToolSpec(
                    name=f"{self.manifest.id}__{tool.name}",
                    description=f"[{self.manifest.name}] {tool.description}",
                    args_schema=tool.args_model,
                    risk=risk_for(tool.capability),
                    capability=tool.capability.value,
                    provider=self.manifest.id,
                    connection_id=ctx.connection.id,
                    handler=self._bind(tool.handler),
                    summarize=tool.summarize,
                    verify=self._bind_verifier(tool.verify) if tool.verify else None,
                )
            )
        return specs

    async def _provider_context(self, tool_ctx: ToolContext) -> ProviderContext:
        """Rebuild a ProviderContext from the tool context: the framework already resolved the
        connection and decrypted the credential (ToolContext.credential)."""
        from app.core.config import get_settings
        from app.integrations.base.provider import ProviderCredentials
        from app.services.connection_service import ConnectionService

        settings = get_settings()
        connections = ConnectionService(tool_ctx.db, settings)
        spec_conn = next(
            (
                conn
                for conn in await connections.list_usable(tool_ctx.user)
                if conn.provider == self.manifest.id
            ),
            None,
        )
        if spec_conn is None:
            raise ProviderError(ProviderErrorKind.expired, provider=self.manifest.id)
        return ProviderContext(
            user=tool_ctx.user,
            db=tool_ctx.db,
            connection=spec_conn,
            credentials=ProviderCredentials(access_token=tool_ctx.credential),
            settings=settings,
        )

    def _bind(self, handler: Handler) -> Callable[[ToolContext, Any], Awaitable[dict[str, Any]]]:
        async def run(tool_ctx: ToolContext, args: Any) -> dict[str, Any]:
            return await handler(await self._provider_context(tool_ctx), args)

        return run

    def _bind_verifier(
        self, verifier: Verifier
    ) -> Callable[[ToolContext, Any, dict[str, Any]], Awaitable[Verification]]:
        async def run(tool_ctx: ToolContext, args: Any, result: dict[str, Any]) -> Verification:
            return await verifier(await self._provider_context(tool_ctx), args, result)

        return run

    # --- helpers for adapters ---------------------------------------------------------------------

    def wrap(self, text: str, *, ref: str) -> str:
        return untrusted(text, source=f"{self.manifest.id}:{ref}")

    def source(self, *, object_id: str, title: str, url: str | None) -> dict[str, Any]:
        return {"provider": self.manifest.id, "object_id": object_id, "title": title, "url": url}
