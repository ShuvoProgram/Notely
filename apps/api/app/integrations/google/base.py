"""Shared Google OAuth plumbing for Gmail, Google Calendar and Google Drive.

All three use the same Google Cloud OAuth client (OAUTH_GOOGLE_CLIENT_ID/SECRET — the one also
used for Google sign-in) with different scopes; each is its own connection so users grant only
what they want."""

from __future__ import annotations

from typing import Any

from app.core.oauth import OAuthEndpoints
from app.integrations.base.provider import ConnectionIdentity, ProviderContext
from app.integrations.base.rest import RestOAuthProvider

GOOGLE_ENDPOINTS = OAuthEndpoints(
    authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
    token_url="https://oauth2.googleapis.com/token",
    # offline + consent → a refresh token on every connect, so connections survive the 1h token.
    extra_authorize_params={
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
    },
)


class GoogleProvider(RestOAuthProvider):
    settings_prefix = "google"
    endpoints = GOOGLE_ENDPOINTS
    use_pkce = True

    async def identity(self, ctx: ProviderContext) -> ConnectionIdentity:
        async with self.http(ctx, "https://www.googleapis.com/oauth2/v2") as http:
            me = (await http.get("/userinfo")).json()
        return ConnectionIdentity(
            external_account_id=str(me.get("id") or me.get("email")),
            external_account_name=str(me.get("email") or me.get("name") or "Google account"),
            metadata={"email": me.get("email")},
        )

    @staticmethod
    def items(body: dict[str, Any], key: str) -> list[dict[str, Any]]:
        value = body.get(key)
        return value if isinstance(value, list) else []
