"""Shared Microsoft identity platform + Graph plumbing for Teams and Outlook.

Both providers use the same Azure app registration (OAUTH_MICROSOFT_CLIENT_ID/SECRET) with
different delegated scopes, and the same Graph base URL."""

from __future__ import annotations

from typing import Any

from app.core.config import Settings
from app.core.oauth import OAuthEndpoints
from app.integrations.base.provider import ConnectionIdentity, ProviderContext
from app.integrations.base.rest import RestOAuthProvider

GRAPH = "https://graph.microsoft.com/v1.0"


def microsoft_endpoints(tenant: str = "common") -> OAuthEndpoints:
    return OAuthEndpoints(
        authorize_url=f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize",
        token_url=f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
        extra_authorize_params={"response_mode": "query"},
    )


class MicrosoftGraphProvider(RestOAuthProvider):
    settings_prefix = "microsoft"
    api_base = GRAPH
    endpoints = microsoft_endpoints()

    def oauth_config(self, settings: Settings):  # type: ignore[no-untyped-def]
        self.endpoints = microsoft_endpoints(settings.oauth_microsoft_tenant)
        return super().oauth_config(settings)

    async def identity(self, ctx: ProviderContext) -> ConnectionIdentity:
        async with self.http(ctx) as http:
            me = (
                await http.get("/me", params={"$select": "id,displayName,mail,userPrincipalName"})
            ).json()
        return ConnectionIdentity(
            external_account_id=str(me.get("id")),
            external_account_name=(
                f"{me.get('displayName')} ({me.get('mail') or me.get('userPrincipalName')})"
            ),
        )

    async def probe(self, ctx: ProviderContext) -> str:
        async with self.http(ctx) as http:
            me = (await http.get("/me", params={"$select": "id"})).json()
        return "Microsoft Graph reachable" if me.get("id") else "Graph responded"

    @staticmethod
    def graph_page(body: dict[str, Any]) -> list[dict[str, Any]]:
        value = body.get("value")
        return value if isinstance(value, list) else []
