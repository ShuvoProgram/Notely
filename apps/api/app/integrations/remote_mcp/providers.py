"""Vendors reachable only through their official remote MCP servers.

Each entry is the generic MCP provider with a fixed server URL and vendor identity. Connecting
is one click: the server publishes its authorization server, Notely registers itself there
(RFC 7591, once per deployment) and the user goes through the vendor's consent page. Servers
that need no auth connect immediately. Vendors that also offer personal tokens list them as a
fallback."""

from __future__ import annotations

from dataclasses import dataclass

from app.integrations.base.capabilities import Capability
from app.integrations.base.provider import (
    AuthType,
    PermissionSpec,
    ProviderManifest,
    TokenAuthSpec,
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
    token: TokenAuthSpec | None = None


# Official remote MCP endpoints as published by each vendor. If a vendor moves its endpoint the
# connect step fails with a clear "unavailable"; nothing else in the app depends on the URL.
CATALOG: tuple[RemoteMCP, ...] = (
    RemoteMCP(
        "sentry",
        "Sentry",
        "developer",
        "Search issues and errors in your Sentry projects; triage with approval.",
        "https://mcp.sentry.dev/mcp",
        "https://cdn.simpleicons.org/sentry",
        "https://docs.sentry.io/product/sentry-mcp/",
    ),
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
        "supabase",
        "Supabase",
        "developer",
        "Inspect your Supabase projects and run queries; changes need approval.",
        "https://mcp.supabase.com/mcp",
        "https://cdn.simpleicons.org/supabase",
        "https://supabase.com/docs/guides/getting-started/mcp",
    ),
    RemoteMCP(
        "vercel",
        "Vercel",
        "developer",
        "Read deployments, logs and projects; trigger changes with approval.",
        "https://mcp.vercel.com",
        "https://cdn.simpleicons.org/vercel",
        "https://vercel.com/docs/mcp/vercel-mcp",
    ),
    RemoteMCP(
        "figma",
        "Figma",
        "design",
        "Read your Figma files and design context.",
        "https://mcp.figma.com/mcp",
        "https://cdn.simpleicons.org/figma",
        "https://help.figma.com/hc/en-us/articles/32132100833559",
    ),
    RemoteMCP(
        "canva",
        "Canva",
        "design",
        "Search and create Canva designs with approval.",
        "https://mcp.canva.com/mcp",
        "https://cdn.simpleicons.org/canva",
        "https://www.canva.dev/docs/connect/canva-mcp-server-setup/",
    ),
    RemoteMCP(
        "intercom",
        "Intercom",
        "communication",
        "Search conversations and contacts in Intercom.",
        "https://mcp.intercom.com/mcp",
        "https://cdn.simpleicons.org/intercom",
        "https://developers.intercom.com/docs/guides/mcp",
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
    RemoteMCP(
        "zapier",
        "Zapier",
        "automation",
        "Run your Zapier actions across thousands of apps, each one reviewed first.",
        "https://mcp.zapier.com/api/mcp/mcp",
        "https://cdn.simpleicons.org/zapier",
        "https://zapier.com/mcp",
    ),
    RemoteMCP(
        "monday",
        "monday.com",
        "project_management",
        "Read boards and items; create and update items with approval.",
        "https://mcp.monday.com/mcp",
        "https://cdn.simpleicons.org/mondaydotcom",
        "https://developer.monday.com/apps/docs/mondaycom-mcp-integration",
    ),
    RemoteMCP(
        "box",
        "Box",
        "storage",
        "Search and read files in Box; upload with approval.",
        "https://mcp.box.com",
        "https://cdn.simpleicons.org/box",
        "https://developer.box.com/guides/box-mcp/remote/",
    ),
    RemoteMCP(
        "huggingface",
        "Hugging Face",
        "developer",
        "Search models, datasets, papers and Spaces on the Hub.",
        "https://huggingface.co/mcp",
        "https://cdn.simpleicons.org/huggingface",
        "https://huggingface.co/settings/mcp",
        token=TokenAuthSpec(
            label="Access token",
            help="Hugging Face → Settings → Access Tokens → Create new token (read).",
            help_url="https://huggingface.co/settings/tokens",
            placeholder="hf_…",
        ),
    ),
    RemoteMCP(
        "cloudflare_docs",
        "Cloudflare Docs",
        "developer",
        "Search Cloudflare's documentation (no sign-in needed).",
        "https://docs.mcp.cloudflare.com/mcp",
        "https://cdn.simpleicons.org/cloudflare",
        "https://developers.cloudflare.com/agents/model-context-protocol/mcp-servers-for-cloudflare/",
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
            token_auth=entry.token,
        )
        provider = MCPServerProvider()
        provider.manifest = manifest
        providers[entry.id] = provider
    return providers
