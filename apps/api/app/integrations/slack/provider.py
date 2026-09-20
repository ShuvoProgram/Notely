"""Slack: OAuth v2 with *user* scopes (search acts as the user), Web API over REST."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.ai.tools.base import Verification
from app.core.exceptions import OAuthExchangeFailed
from app.core.oauth import OAuthEndpoints, OAuthTokens
from app.integrations.base.capabilities import Capability
from app.integrations.base.errors import ProviderError, ProviderErrorKind
from app.integrations.base.provider import (
    AuthType,
    ConnectionIdentity,
    PermissionSpec,
    ProviderContext,
    ProviderManifest,
    TokenAuthSpec,
)
from app.integrations.base.rest import ProviderTool, RestOAuthProvider

USER_SCOPES = ("search:read", "channels:read", "channels:history", "users:read")
OPTIONAL_SCOPES = ("chat:write",)


def parse_slack_tokens(payload: dict[str, Any]) -> OAuthTokens:
    """Slack returns the user token under `authed_user`, not top-level."""
    if not payload.get("ok"):
        raise OAuthExchangeFailed()
    user = payload.get("authed_user") or {}
    token = user.get("access_token") or payload.get("access_token")
    if not token:
        raise OAuthExchangeFailed()
    return OAuthTokens(
        access_token=token,
        refresh_token=user.get("refresh_token"),
        expires_in=user.get("expires_in"),
        id_token=None,
        scope=user.get("scope"),
        raw=payload,
    )


class SearchMessagesArgs(BaseModel):
    """Search Slack messages the user can see."""

    query: str = Field(min_length=1, max_length=200)
    limit: int = Field(default=10, ge=1, le=25)


class ListChannelsArgs(BaseModel):
    """List public channels in the workspace."""

    limit: int = Field(default=50, ge=1, le=200)


class ReadChannelArgs(BaseModel):
    """Read recent messages from a channel by id."""

    channel_id: str = Field(min_length=1, max_length=40)
    limit: int = Field(default=20, ge=1, le=100)


class PostMessageArgs(BaseModel):
    """Post a message to a channel as the user."""

    channel_id: str = Field(min_length=1, max_length=40)
    text: str = Field(min_length=1, max_length=4000)


class SlackProvider(RestOAuthProvider):
    settings_prefix = "slack"
    use_pkce = False
    api_base = "https://slack.com/api"
    token_parser = staticmethod(parse_slack_tokens)
    endpoints = OAuthEndpoints(
        authorize_url="https://slack.com/oauth/v2/authorize",
        token_url="https://slack.com/api/oauth.v2.access",
        scope_param="user_scope",
        scope_separator=",",
    )
    manifest = ProviderManifest(
        id="slack",
        name="Slack",
        category="communication",
        description="Search and read the channels you're in; post messages with your approval.",
        logo_url="https://cdn.simpleicons.org/slack",
        docs_url="https://api.slack.com/authentication/oauth-v2",
        token_auth=TokenAuthSpec(
            label="User token",
            help=(
                "Create a Slack app for your workspace, add the user scopes listed under "
                "Permissions, install it, and paste the User OAuth Token (starts with xoxp-)."
            ),
            help_url="https://api.slack.com/apps",
            placeholder="xoxp-…",
        ),
        auth=AuthType.oauth2,
        capabilities=[Capability.search, Capability.read, Capability.send],
        permissions=[
            PermissionSpec(
                scope="search:read", label="Search messages", capability=Capability.search
            ),
            PermissionSpec(
                scope="channels:read", label="Read channel list", capability=Capability.read
            ),
            PermissionSpec(
                scope="channels:history", label="Read channel messages", capability=Capability.read
            ),
            PermissionSpec(
                scope="users:read", label="Resolve user names", capability=Capability.read
            ),
            PermissionSpec(
                scope="chat:write",
                label="Send messages as you",
                required=False,
                capability=Capability.send,
            ),
        ],
    )

    async def _call(self, ctx: ProviderContext, method: str, **params: Any) -> dict[str, Any]:
        async with self.http(ctx) as http:
            resp = await http.post(f"/{method}", data=params)
        body: dict[str, Any] = resp.json()
        if not body.get("ok"):
            error = str(body.get("error", "unknown_error"))
            kind = {
                "invalid_auth": ProviderErrorKind.expired,
                "token_revoked": ProviderErrorKind.expired,
                "token_expired": ProviderErrorKind.expired,
                "not_authed": ProviderErrorKind.expired,
                "missing_scope": ProviderErrorKind.permission_denied,
                "not_in_channel": ProviderErrorKind.permission_denied,
                "channel_not_found": ProviderErrorKind.not_found,
                "ratelimited": ProviderErrorKind.rate_limited,
            }.get(error, ProviderErrorKind.invalid_request)
            raise ProviderError(kind, error, provider="slack")
        return body

    async def identity(self, ctx: ProviderContext) -> ConnectionIdentity:
        me = await self._call(ctx, "auth.test")
        return ConnectionIdentity(
            external_account_id=str(me.get("user_id")),
            external_account_name=f"{me.get('user')} @ {me.get('team')}",
            metadata={"team_id": me.get("team_id"), "team": me.get("team")},
        )

    async def probe(self, ctx: ProviderContext) -> str:
        body = await self._call(ctx, "conversations.list", limit=1, types="public_channel")
        return f"{len(body.get('channels', []))} channel(s) visible"

    async def search(self, ctx: ProviderContext, query: str, limit: int) -> list[dict[str, Any]]:
        body = await self._call(ctx, "search.messages", query=query, count=limit)
        hits = []
        for m in (body.get("messages") or {}).get("matches", []):
            hits.append(
                {
                    "id": m.get("iid") or m.get("ts"),
                    "kind": "message",
                    "title": f"#{(m.get('channel') or {}).get('name', 'channel')}",
                    "snippet": str(m.get("text", ""))[:240],
                    "url": m.get("permalink"),
                    "updated_at": None,
                }
            )
        return hits

    def build_tools(self):  # type: ignore[no-untyped-def]
        async def search_messages(ctx: ProviderContext, a: SearchMessagesArgs) -> dict[str, Any]:
            hits = await self.search(ctx, a.query, a.limit)
            return {
                "results": [
                    {**h, "snippet": self.wrap(h["snippet"], ref=str(h["id"]))} for h in hits
                ],
                "sources": [
                    self.source(object_id=str(h["id"]), title=h["title"], url=h["url"])
                    for h in hits
                ],
            }

        async def list_channels(ctx: ProviderContext, a: ListChannelsArgs) -> dict[str, Any]:
            body = await self._call(
                ctx,
                "conversations.list",
                limit=a.limit,
                types="public_channel",
                exclude_archived="true",
            )
            return {
                "channels": [
                    {"id": c["id"], "name": self.wrap(c["name"], ref=c["id"])}
                    for c in body.get("channels", [])
                ]
            }

        async def read_channel(ctx: ProviderContext, a: ReadChannelArgs) -> dict[str, Any]:
            body = await self._call(
                ctx, "conversations.history", channel=a.channel_id, limit=a.limit
            )
            messages = [
                {
                    "ts": m.get("ts"),
                    "user": m.get("user"),
                    "text": self.wrap(str(m.get("text", "")), ref=a.channel_id),
                }
                for m in body.get("messages", [])
            ]
            return {
                "messages": messages,
                "sources": [
                    self.source(object_id=a.channel_id, title=f"Channel {a.channel_id}", url=None)
                ],
            }

        async def post_message(ctx: ProviderContext, a: PostMessageArgs) -> dict[str, Any]:
            body = await self._call(ctx, "chat.postMessage", channel=a.channel_id, text=a.text)
            return {"ts": body.get("ts"), "channel": body.get("channel")}

        async def verify_post_message(
            ctx: ProviderContext, a: PostMessageArgs, result: dict[str, Any]
        ) -> Verification:
            ts = str(result.get("ts") or "")
            body = await self._call(
                ctx,
                "conversations.history",
                channel=a.channel_id,
                latest=ts,
                oldest=ts,
                inclusive="true",
                limit=1,
            )
            found = [m for m in body.get("messages", []) if str(m.get("ts")) == ts]
            if not found:
                return Verification.failed("The message is not in the channel history")
            return Verification.verified("Message is visible in the channel")

        return [
            ProviderTool(
                "search_messages",
                "Search Slack messages.",
                SearchMessagesArgs,
                Capability.search,
                search_messages,
                lambda a: f"Search Slack for “{a.query}”",
            ),
            ProviderTool(
                "list_channels",
                "List public channels.",
                ListChannelsArgs,
                Capability.read,
                list_channels,
                lambda a: "List Slack channels",
            ),
            ProviderTool(
                "read_channel",
                "Read recent messages in a channel.",
                ReadChannelArgs,
                Capability.read,
                read_channel,
                lambda a: f"Read Slack channel {a.channel_id}",
            ),
            ProviderTool(
                "post_message",
                "Post a message to a channel as you.",
                PostMessageArgs,
                Capability.send,
                post_message,
                lambda a: f"Post to Slack channel {a.channel_id}: “{a.text[:60]}”",
                verify=verify_post_message,
            ),
        ]
