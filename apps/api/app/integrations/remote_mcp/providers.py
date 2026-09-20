"""Vendors reachable only through their official remote MCP servers.

Each entry is the generic MCP provider with a fixed server URL and vendor identity. Connecting
is one click: the server publishes its authorization server, Notely registers itself there
(RFC 7591, once per deployment) and the user goes through the vendor's consent page."""

from __future__ import annotations

from dataclasses import dataclass

from app.integrations.base.capabilities import Capability
from app.integrations.base.provider import (
    AuthType,
    PermissionSpec,
    ProviderManifest,
)
from app.integrations.mcp_server.provider import MCPServerProvider

ALL_CAPABILITIES = [
    Capability.search,
    Capability.read,
    Capability.create,
    Capability.update,
    Capability.delete,
]


@dataclass(frozen=True)
class RemoteMCP:
    id: str
    name: str
    category: str
    description: str
    url: str
    logo: str
    docs: str


# Official remote MCP endpoints as published by each vendor. If a vendor moves its endpoint the
# connect step fails with a clear "unavailable"; nothing else in the app depends on the URL.
CATALOG: tuple[RemoteMCP, ...] = (
    RemoteMCP(
        "stripe",
        "Stripe",
        "payments",
        "Look up customers, payments and subscriptions; create records with approval.",
        "https://mcp.stripe.com",
        "https://cdn.simpleicons.org/stripe",
        "https://docs.stripe.com/mcp",
    ),
    RemoteMCP(
        "paypal",
        "PayPal",
        "payments",
        "Look up orders, invoices and payouts; create invoices with approval.",
        "https://mcp.paypal.com/mcp",
        "https://cdn.simpleicons.org/paypal",
        "https://developer.paypal.com/tools/mcp-server/",
    ),
)


def build_remote_mcp_providers() -> dict[str, MCPServerProvider]:
    providers: dict[str, MCPServerProvider] = {}
    for entry in CATALOG:
        manifest = ProviderManifest(
            id=entry.id,
            name=entry.name,
            category=entry.category,
            description=entry.description,
            logo_url=entry.logo,
            docs_url=entry.docs,
            # OAuth via the MCP server's authorization server; no app registration needed.
            auth=AuthType.oauth2,
            capabilities=ALL_CAPABILITIES,
            permissions=[
                PermissionSpec(
                    scope="mcp",
                    label=f"Act in {entry.name} as you",
                    description=(
                        f"The exact permissions are shown and approved on {entry.name}'s own "
                        "consent screen. Reads run automatically; changes wait for your review."
                    ),
                    capability=Capability.read,
                )
            ],
            mcp_server_url=entry.url,
        )
        provider = MCPServerProvider()
        provider.manifest = manifest
        providers[entry.id] = provider
    return providers
