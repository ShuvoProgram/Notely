"""The integration provider contract.

Every provider — official MCP server, REST/GraphQL API adapter, custom MCP server — implements
this interface. Everything provider-specific (endpoints, scopes, payload shapes, error quirks)
lives inside the adapter; the framework handles OAuth, credential storage, status, policy,
approval, retries and auditing exactly once.
"""

from __future__ import annotations

import enum
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.tools.base import ToolSpec
from app.core.config import Settings
from app.core.oauth import OAuthClientConfig, OAuthTokens
from app.integrations.base.capabilities import Capability
from app.models.integration import UserConnection
from app.models.user import User


class AuthType(enum.StrEnum):
    oauth2 = "oauth2"
    token = "token"  # user-supplied API token / bearer
    none = "none"


class PermissionSpec(BaseModel):
    """One requestable permission, shown in the connect flow. `scope` is what we ask for."""

    scope: str
    label: str
    description: str = ""
    required: bool = True
    capability: Capability | None = None


class ConfigField(BaseModel):
    """A non-secret setting the user provides when connecting (e.g. an MCP server URL)."""

    key: str
    label: str
    kind: str = "text"  # text | url | secret | select
    required: bool = True
    placeholder: str = ""
    help: str = ""
    options: list[dict[str, str]] = Field(default_factory=list)


class TokenAuthSpec(BaseModel):
    """How a user can connect with a personal API token instead of (or as well as) OAuth.

    Shown as a form: `fields` (non-secret settings such as a site URL) plus the token itself.
    `help` tells the user where the vendor issues such tokens."""

    label: str = "Personal API token"
    help: str = ""
    help_url: str | None = None
    placeholder: str = ""
    fields: list[ConfigField] = Field(default_factory=list)


class ProviderManifest(BaseModel):
    id: str
    name: str
    category: str
    description: str = ""
    logo_url: str | None = None
    docs_url: str | None = None
    auth: AuthType
    capabilities: list[Capability]
    permissions: list[PermissionSpec] = Field(default_factory=list)
    config_fields: list[ConfigField] = Field(default_factory=list)
    # Optional second way in for OAuth providers: a user-issued token. Lets people connect on
    # deployments that have no vendor OAuth app registered (self-hosted, trials).
    token_auth: TokenAuthSpec | None = None
    # The vendor's official remote MCP server. Connecting through it needs no per-deployment
    # OAuth app: the server's authorization server registers Notely dynamically (RFC 7591) and
    # the user just clicks Connect. Tools then come from the MCP server instead of the adapter.
    mcp_server_url: str | None = None
    supports_webhooks: bool = False
    supports_sync: bool = False


@dataclass
class ProviderCredentials:
    access_token: str | None = None
    refresh_token: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProviderContext:
    """What an adapter gets for any operation. Credentials are decrypted just-in-time."""

    user: User
    db: AsyncSession
    connection: UserConnection
    credentials: ProviderCredentials
    settings: Settings


@dataclass(frozen=True)
class ConnectionIdentity:
    external_account_id: str | None
    external_account_name: str | None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TestStep:
    name: str  # "Authentication", "Permissions", "API availability", "Tool access"
    ok: bool
    detail: str = ""


@dataclass(frozen=True)
class ConnectionTest:
    steps: list[TestStep]

    @property
    def healthy(self) -> bool:
        return all(s.ok for s in self.steps)


@dataclass(frozen=True)
class WebhookVerification:
    ok: bool
    events: list[dict[str, Any]] = field(default_factory=list)  # each has at least "id"
    reason: str | None = None


class IntegrationProvider(ABC):
    manifest: ProviderManifest

    # --- configuration ----------------------------------------------------------------------

    def is_configured(self, settings: Settings) -> bool:
        """OAuth providers need client credentials on this deployment; others are always on."""
        return self.manifest.auth != AuthType.oauth2 or self.oauth_config(settings) is not None

    def connect_methods(self, settings: Settings) -> list[str]:
        """Ways this user can connect right now: `oauth` (when the deployment has client
        credentials), `token` (when the provider accepts user-issued tokens), `config`."""
        methods: list[str] = []
        if self.manifest.auth == AuthType.oauth2 and self.oauth_config(settings) is not None:
            methods.append("oauth")
        if self.manifest.mcp_server_url:
            methods.append("mcp")
        if self.manifest.auth == AuthType.token or self.manifest.token_auth is not None:
            methods.append("token")
        if self.manifest.auth == AuthType.none:
            methods.append("config")
        return methods

    def oauth_config(self, settings: Settings) -> OAuthClientConfig | None:  # noqa: ARG002
        return None

    def scopes_for(self, selected: list[str] | None) -> list[str]:
        """Minimum scopes: required permissions plus any optional ones the user selected."""
        required = [p.scope for p in self.manifest.permissions if p.required]
        optional = [p.scope for p in self.manifest.permissions if not p.required]
        chosen = [s for s in (selected or []) if s in optional]
        return list(dict.fromkeys([*required, *chosen]))

    # --- lifecycle --------------------------------------------------------------------------------

    @abstractmethod
    async def complete_connection(self, ctx: ProviderContext) -> ConnectionIdentity:
        """Called once credentials exist: verify them and return who we're connected as."""

    async def refresh_credentials(self, ctx: ProviderContext) -> OAuthTokens | None:  # noqa: ARG002
        """Return fresh tokens, or None if the provider has nothing to refresh."""
        return None

    async def revoke(self, ctx: ProviderContext) -> None:  # noqa: ARG002
        """Best-effort revocation at the provider on disconnect."""
        return None

    @abstractmethod
    async def test_connection(self, ctx: ProviderContext) -> ConnectionTest:
        """Harmless checks: credentials, scopes, availability, tool access."""

    # --- capabilities ---------------------------------------------------------------------------

    @abstractmethod
    async def tools(self, ctx: ProviderContext) -> list[ToolSpec]:
        """Tools the agent may use through this connection, mapped onto capabilities."""

    async def search(self, ctx: ProviderContext, query: str, limit: int) -> list[dict[str, Any]]:  # noqa: ARG002
        """Unified-search hits: {id, title, snippet, url, kind, updated_at}. Default: none."""
        return []

    async def sync(self, ctx: ProviderContext) -> int:  # noqa: ARG002
        """Selective indexing into external_items. Returns items touched. Default: nothing."""
        return 0

    # --- webhooks -------------------------------------------------------------------------------

    def verify_webhook(  # noqa: ARG002
        self, *, headers: Mapping[str, str], body: bytes, settings: Settings
    ) -> WebhookVerification:
        return WebhookVerification(ok=False, reason="Webhooks not supported")

    async def handle_webhook(self, ctx: ProviderContext | None, event: dict[str, Any]) -> None:  # noqa: ARG002
        return None
