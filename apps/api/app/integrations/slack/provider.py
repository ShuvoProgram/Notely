"""Slack: OAuth v2 with *user* scopes (search acts as the user), Web API over REST."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from pydantic import AliasChoices, BaseModel, Field

from app.ai.tools.base import OutputField as F
from app.ai.tools.base import Verification
from app.core.exceptions import OAuthExchangeFailed
from app.core.oauth import OAuthEndpoints, OAuthTokens
from app.integrations.base.capabilities import Capability
from app.integrations.base.errors import ProviderError, ProviderErrorKind
from app.integrations.base.outputs import HIT_FIELDS, listing
from app.integrations.base.provider import (
    AuthType,
    ConnectionIdentity,
    PermissionSpec,
    ProviderContext,
    ProviderManifest,
)
from app.integrations.base.rest import ProviderTool, RestOAuthProvider
from app.integrations.base.triggers import ProviderTrigger, TriggerEvent, parse_time

USER_SCOPES = ("search:read", "channels:read", "channels:history", "users:read")
OPTIONAL_SCOPES = ("chat:write", "channels:manage")
CHANNEL_HELP = "A channel id (C0123…) or name, with or without the leading #"
# Channel names are lowercase, so an all-caps C/G-prefixed token can only be an id.
CHANNEL_ID = re.compile(r"[CG][A-Z0-9]{8,}")


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


def _channel_label(channel: str) -> str:
    raw = channel.strip()
    return raw if CHANNEL_ID.fullmatch(raw) else "#" + raw.removeprefix("#")


class SearchMessagesArgs(BaseModel):
    """Search Slack messages the user can see."""

    query: str = Field(min_length=1, max_length=200)
    limit: int = Field(default=10, ge=1, le=25)


class ListChannelsArgs(BaseModel):
    """List public channels in the workspace."""

    limit: int = Field(default=50, ge=1, le=200)


class ReadChannelArgs(BaseModel):
    """Read recent messages from a channel."""

    channel: str = Field(
        min_length=1,
        max_length=80,
        description=CHANNEL_HELP,
        # `channel_id` was the name before names were accepted; saved automations still use it.
        validation_alias=AliasChoices("channel", "channel_id"),
    )
    limit: int = Field(default=20, ge=1, le=100)


class ChannelInfoArgs(BaseModel):
    """A channel's topic, purpose and member count."""

    channel: str = Field(
        min_length=1,
        max_length=80,
        description=CHANNEL_HELP,
        # `channel_id` was the name before names were accepted; saved automations still use it.
        validation_alias=AliasChoices("channel", "channel_id"),
    )


class CreateChannelArgs(BaseModel):
    """Create a public channel (you become its first member)."""

    name: str = Field(
        min_length=1,
        max_length=80,
        pattern=r"^#?[a-z0-9][a-z0-9_-]*$",
        description="Lowercase letters, numbers, hyphens and underscores",
    )
    purpose: str | None = Field(default=None, max_length=250)


class ReadThreadArgs(BaseModel):
    """Read a thread: the parent message and its replies."""

    channel_id: str = Field(min_length=1, max_length=40)
    thread_ts: str = Field(min_length=1, max_length=40)
    limit: int = Field(default=50, ge=1, le=200)


class MessagePostedParams(BaseModel):
    """Which channel to watch."""

    channel: str = Field(min_length=1, max_length=80, description=CHANNEL_HELP)


class PostMessageArgs(BaseModel):
    """Post a message to a channel as the user; give `thread_ts` to reply in a thread."""

    channel: str = Field(
        min_length=1,
        max_length=80,
        description=CHANNEL_HELP,
        # `channel_id` was the name before names were accepted; saved automations still use it.
        validation_alias=AliasChoices("channel", "channel_id"),
    )
    text: str = Field(min_length=1, max_length=4000)
    thread_ts: str | None = Field(default=None, max_length=40)


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
        description=(
            "Search messages, read channels and threads; post, reply and create channels with "
            "your approval."
        ),
        logo_url="https://cdn.simpleicons.org/slack",
        docs_url="https://api.slack.com/authentication/oauth-v2",
        auth=AuthType.oauth2,
        capabilities=[Capability.search, Capability.read, Capability.send, Capability.create],
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
            PermissionSpec(
                scope="channels:manage",
                label="Create public channels",
                required=False,
                capability=Capability.create,
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

    async def resolve_channel(self, ctx: ProviderContext, channel: str) -> str:
        """A channel id from an id or a (#)name, so people can say "#marketing"."""
        raw = channel.strip()
        if CHANNEL_ID.fullmatch(raw):
            return raw
        name = raw.removeprefix("#").lower()
        cursor = ""
        for _ in range(10):  # 10 pages of 200: far beyond most workspaces
            params: dict[str, Any] = {
                "limit": 200,
                "types": "public_channel",
                "exclude_archived": "true",
            }
            if cursor:
                params["cursor"] = cursor
            body = await self._call(ctx, "conversations.list", **params)
            for c in body.get("channels", []):
                if c.get("id") == raw or str(c.get("name", "")).lower() == name:
                    return str(c["id"])
            cursor = (body.get("response_metadata") or {}).get("next_cursor") or ""
            if not cursor:
                break
        raise ProviderError(
            ProviderErrorKind.not_found, f"No channel named #{name}", provider="slack"
        )

    async def user_names(self, ctx: ProviderContext, ids: set[str]) -> dict[str, str]:
        """Display names for message authors (at most 25 lookups per call)."""
        names: dict[str, str] = {}
        for uid in list(ids)[:25]:
            try:
                user = (await self._call(ctx, "users.info", user=uid)).get("user") or {}
            except ProviderError:
                continue
            profile = user.get("profile") or {}
            names[uid] = profile.get("display_name") or user.get("real_name") or uid
        return names

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

    def build_triggers(self) -> list[ProviderTrigger]:
        async def message_posted(
            ctx: ProviderContext, p: MessagePostedParams, since: datetime
        ) -> list[TriggerEvent]:
            channel_id = await self.resolve_channel(ctx, p.channel)
            body = await self._call(
                ctx,
                "conversations.history",
                channel=channel_id,
                oldest=f"{since.timestamp():.6f}",
                limit=50,
            )
            # Real messages only: not joins, topic changes or other channel housekeeping.
            raw = [m for m in body.get("messages", []) if not m.get("subtype")]
            names = await self.user_names(ctx, {str(m["user"]) for m in raw if m.get("user")})
            events = []
            for m in raw:
                sent = parse_time(m.get("ts"))
                if sent is None or sent <= since:
                    continue
                events.append(
                    TriggerEvent(
                        id=f"{channel_id}:{m['ts']}",
                        occurred_at=sent,
                        data={
                            "text": m.get("text", ""),
                            "user": names.get(str(m.get("user")), m.get("user")),
                            "channel": p.channel.removeprefix("#"),
                            "channel_id": channel_id,
                            "ts": m.get("ts"),
                            "sent_at": sent.isoformat(),
                            "thread_ts": m.get("thread_ts"),
                        },
                    )
                )
            return events

        return [
            ProviderTrigger(
                "message_posted",
                "New message in a channel",
                "Starts when someone posts in a Slack channel. Add a filter to react only to "
                "messages that contain certain words.",
                message_posted,
                MessagePostedParams,
                outputs=(
                    F("text", "Message", "long_text"),
                    F("user", "From"),
                    F("channel", "Channel"),
                    F("sent_at", "Sent", "date"),
                    F("ts", "Message timestamp"),
                    F("channel_id", "Channel ID"),
                ),
                scope="channels:history",
            )
        ]

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
            channel_id = await self.resolve_channel(ctx, a.channel)
            body = await self._call(ctx, "conversations.history", channel=channel_id, limit=a.limit)
            raw = body.get("messages", [])
            names = await self.user_names(ctx, {str(m["user"]) for m in raw if m.get("user")})
            messages = [
                {
                    "ts": m.get("ts"),
                    "user": names.get(str(m.get("user")), m.get("user")),
                    "text": self.wrap(str(m.get("text", "")), ref=channel_id),
                    "thread_replies": m.get("reply_count", 0),
                }
                for m in raw
            ]
            return {
                "channel_id": channel_id,
                "messages": messages,
                "sources": [
                    self.source(object_id=channel_id, title=f"Channel {a.channel}", url=None)
                ],
            }

        async def channel_info(ctx: ProviderContext, a: ChannelInfoArgs) -> dict[str, Any]:
            channel_id = await self.resolve_channel(ctx, a.channel)
            c = (
                await self._call(
                    ctx, "conversations.info", channel=channel_id, include_num_members="true"
                )
            ).get("channel") or {}
            return {
                "channel_id": channel_id,
                "name": c.get("name"),
                "topic": self.wrap(str((c.get("topic") or {}).get("value", "")), ref=channel_id),
                "purpose": self.wrap(
                    str((c.get("purpose") or {}).get("value", "")), ref=channel_id
                ),
                "members": c.get("num_members"),
                "archived": c.get("is_archived", False),
            }

        async def create_channel(ctx: ProviderContext, a: CreateChannelArgs) -> dict[str, Any]:
            name = a.name.removeprefix("#")
            c = (await self._call(ctx, "conversations.create", name=name)).get("channel") or {}
            if a.purpose:
                await self._call(
                    ctx, "conversations.setPurpose", channel=c["id"], purpose=a.purpose
                )
            return {"channel_id": c.get("id"), "name": c.get("name")}

        async def verify_create_channel(
            ctx: ProviderContext, a: CreateChannelArgs, result: dict[str, Any]
        ) -> Verification:
            c = (await self._call(ctx, "conversations.info", channel=result["channel_id"])).get(
                "channel"
            ) or {}
            if c.get("name") != a.name.removeprefix("#"):
                return Verification.failed("The channel was not found")
            return Verification.verified(f"#{c.get('name')} exists")

        async def read_thread(ctx: ProviderContext, a: ReadThreadArgs) -> dict[str, Any]:
            body = await self._call(
                ctx, "conversations.replies", channel=a.channel_id, ts=a.thread_ts, limit=a.limit
            )
            return {
                "messages": [
                    {
                        "ts": m.get("ts"),
                        "user": m.get("user"),
                        "text": self.wrap(str(m.get("text", "")), ref=a.thread_ts),
                    }
                    for m in body.get("messages", [])
                ],
                "sources": [
                    self.source(object_id=a.thread_ts, title=f"Thread in {a.channel_id}", url=None)
                ],
            }

        async def post_message(ctx: ProviderContext, a: PostMessageArgs) -> dict[str, Any]:
            params: dict[str, Any] = {
                "channel": await self.resolve_channel(ctx, a.channel),
                "text": a.text,
            }
            if a.thread_ts:
                params["thread_ts"] = a.thread_ts
            body = await self._call(ctx, "chat.postMessage", **params)
            return {"ts": body.get("ts"), "channel": body.get("channel"), "thread_ts": a.thread_ts}

        async def verify_post_message(
            ctx: ProviderContext, a: PostMessageArgs, result: dict[str, Any]
        ) -> Verification:
            ts = str(result.get("ts") or "")
            channel_id = str(result.get("channel") or "")
            if a.thread_ts:
                body = await self._call(
                    ctx, "conversations.replies", channel=channel_id, ts=a.thread_ts, limit=200
                )
            else:
                body = await self._call(
                    ctx,
                    "conversations.history",
                    channel=channel_id,
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
                outputs=(listing("results", "Messages", *HIT_FIELDS),),
            ),
            ProviderTool(
                "list_channels",
                "List public channels.",
                ListChannelsArgs,
                Capability.read,
                list_channels,
                lambda a: "List Slack channels",
                outputs=(listing("channels", "Channels", F("name", "Channel")),),
            ),
            ProviderTool(
                "channel_info",
                "Get a Slack channel's topic, purpose and member count.",
                ChannelInfoArgs,
                Capability.read,
                channel_info,
                lambda a: f"Get details of Slack channel {a.channel}",
                outputs=(
                    F("name", "Channel"),
                    F("topic", "Topic"),
                    F("purpose", "Purpose"),
                    F("members", "Members", "number"),
                ),
            ),
            ProviderTool(
                "read_channel",
                "Read recent messages in a channel.",
                ReadChannelArgs,
                Capability.read,
                read_channel,
                lambda a: f"Read Slack channel {a.channel}",
                outputs=(
                    listing(
                        "messages",
                        "Messages",
                        F("text", "Message"),
                        F("user", "From"),
                        F("ts", "Sent", "date"),
                    ),
                ),
            ),
            ProviderTool(
                "read_thread",
                "Read a thread's replies.",
                ReadThreadArgs,
                Capability.read,
                read_thread,
                lambda a: "Read a Slack thread",
                scope="channels:history",
            ),
            ProviderTool(
                "post_message",
                "Post a message to a channel as you.",
                PostMessageArgs,
                Capability.send,
                post_message,
                lambda a: f"Post to Slack {_channel_label(a.channel)}: “{a.text[:60]}”",
                verify=verify_post_message,
                scope="chat:write",
                outputs=(F("ts", "Message timestamp"), F("channel", "Channel ID")),
            ),
            ProviderTool(
                "create_channel",
                "Create a public Slack channel.",
                CreateChannelArgs,
                Capability.create,
                create_channel,
                lambda a: f"Create Slack channel #{a.name.removeprefix('#')}",
                verify=verify_create_channel,
                scope="channels:manage",
                outputs=(F("channel_id", "Channel ID"), F("name", "Channel")),
            ),
        ]
