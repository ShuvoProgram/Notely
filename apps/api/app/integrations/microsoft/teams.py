"""Microsoft Teams via Graph: teams, channels, channel messages, sending as the user."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any

from pydantic import BaseModel, Field

from app.ai.tools.base import OutputField as F
from app.ai.tools.base import Verification
from app.integrations.base.capabilities import Capability
from app.integrations.base.outputs import listing
from app.integrations.base.provider import (
    AuthType,
    PermissionSpec,
    ProviderContext,
    ProviderManifest,
)
from app.integrations.base.rest import ProviderTool
from app.integrations.base.triggers import ProviderTrigger, TriggerEvent, parse_time
from app.integrations.microsoft.base import MicrosoftGraphProvider


def _strip_html(html: str) -> str:
    return re.sub(r"<[^>]+>", "", html or "").strip()


class ListTeamsArgs(BaseModel):
    """List the teams you belong to and their channels."""


class ReadChannelArgs(BaseModel):
    """Read recent messages from a channel."""

    team_id: str = Field(min_length=1, max_length=80)
    channel_id: str = Field(min_length=1, max_length=120)
    limit: int = Field(default=20, ge=1, le=50)


class SearchMessagesArgs(BaseModel):
    """Search channel and chat messages you can see (Microsoft Search)."""

    query: str = Field(min_length=1, max_length=200)
    limit: int = Field(default=10, ge=1, le=25)


class SendChannelMessageArgs(BaseModel):
    """Post a message to a channel as you."""

    team_id: str = Field(min_length=1, max_length=80)
    channel_id: str = Field(min_length=1, max_length=120)
    text: str = Field(min_length=1, max_length=4000)


class ChannelMessageParams(BaseModel):
    """Which channel to watch (ids from "List your teams and channels")."""

    team_id: str = Field(min_length=1, max_length=80)
    channel_id: str = Field(min_length=1, max_length=120)


class ReplyToMessageArgs(BaseModel):
    """Reply in a channel message's thread as you."""

    team_id: str = Field(min_length=1, max_length=80)
    channel_id: str = Field(min_length=1, max_length=120)
    message_id: str = Field(min_length=1, max_length=120)
    text: str = Field(min_length=1, max_length=4000)


class CreateMeetingArgs(BaseModel):
    """Create a Teams meeting and get its join link to share."""

    subject: str = Field(min_length=1, max_length=255)
    start: datetime = Field(description="ISO 8601 with a time zone offset")
    end: datetime | None = Field(default=None, description="Defaults to 30 minutes after start")


SEND = "ChannelMessage.Send"
MEETINGS = "OnlineMeetings.ReadWrite"


class TeamsProvider(MicrosoftGraphProvider):
    manifest = ProviderManifest(
        id="microsoft_teams",
        name="Microsoft Teams",
        category="communication",
        description=(
            "Search and read your teams and channel messages; post, reply and create Teams "
            "meetings with approval."
        ),
        logo_url="https://cdn.simpleicons.org/microsoftteams",
        docs_url="https://learn.microsoft.com/graph/api/resources/teams-api-overview",
        auth=AuthType.oauth2,
        capabilities=[Capability.search, Capability.read, Capability.send, Capability.schedule],
        permissions=[
            PermissionSpec(
                scope="User.Read", label="Read your profile", capability=Capability.read
            ),
            PermissionSpec(
                scope="Team.ReadBasic.All", label="See your teams", capability=Capability.read
            ),
            PermissionSpec(
                scope="Channel.ReadBasic.All", label="See channels", capability=Capability.read
            ),
            PermissionSpec(
                scope="ChannelMessage.Read.All",
                label="Read channel messages",
                capability=Capability.read,
            ),
            PermissionSpec(scope="offline_access", label="Stay connected (refresh tokens)"),
            PermissionSpec(
                scope=SEND,
                label="Post channel messages and replies as you",
                required=False,
                capability=Capability.send,
            ),
            PermissionSpec(
                scope=MEETINGS,
                label="Create Teams meetings",
                required=False,
                capability=Capability.schedule,
            ),
        ],
    )

    async def probe(self, ctx: ProviderContext) -> str:
        async with self.http(ctx) as http:
            teams = self.graph_page((await http.get("/me/joinedTeams")).json())
        return f"{len(teams)} team(s)"

    def build_triggers(self) -> list[ProviderTrigger]:
        async def message_posted(
            ctx: ProviderContext, p: ChannelMessageParams, since: datetime
        ) -> list[TriggerEvent]:
            async with self.http(ctx) as http:
                msgs = self.graph_page(
                    (
                        await http.get(
                            f"/teams/{p.team_id}/channels/{p.channel_id}/messages",
                            params={"$top": 25},
                        )
                    ).json()
                )
            events = []
            for m in msgs:
                created = parse_time(m.get("createdDateTime"))
                if m.get("messageType") not in (None, "message") or created is None:
                    continue
                if created <= since:
                    continue
                events.append(
                    TriggerEvent(
                        id=str(m["id"]),
                        occurred_at=created,
                        data={
                            "message_id": m["id"],
                            "text": _strip_html((m.get("body") or {}).get("content", "")),
                            "from": ((m.get("from") or {}).get("user") or {}).get("displayName"),
                            "sent_at": m.get("createdDateTime"),
                            "team_id": p.team_id,
                            "channel_id": p.channel_id,
                            "url": m.get("webUrl"),
                        },
                    )
                )
            return events

        return [
            ProviderTrigger(
                "message_posted",
                "New message in a channel",
                "Starts when someone posts in a Teams channel.",
                message_posted,
                ChannelMessageParams,
                outputs=(
                    F("text", "Message", "long_text"),
                    F("from", "From"),
                    F("sent_at", "Sent", "date"),
                    F("message_id", "Message ID"),
                    F("url", "Link", "url"),
                ),
                scope="ChannelMessage.Read.All",
            )
        ]

    def build_tools(self):  # type: ignore[no-untyped-def]
        async def list_teams(ctx: ProviderContext, a: ListTeamsArgs) -> dict[str, Any]:
            out = []
            async with self.http(ctx) as http:
                for team in self.graph_page((await http.get("/me/joinedTeams")).json())[:20]:
                    channels = self.graph_page(
                        (await http.get(f"/teams/{team['id']}/channels")).json()
                    )
                    out.append(
                        {
                            "team_id": team["id"],
                            "name": self.wrap(str(team.get("displayName", "")), ref=team["id"]),
                            "channels": [
                                {
                                    "channel_id": c["id"],
                                    "name": self.wrap(str(c.get("displayName", "")), ref=c["id"]),
                                }
                                for c in channels
                            ],
                        }
                    )
            return {"teams": out}

        async def read_channel(ctx: ProviderContext, a: ReadChannelArgs) -> dict[str, Any]:
            async with self.http(ctx) as http:
                msgs = self.graph_page(
                    (
                        await http.get(
                            f"/teams/{a.team_id}/channels/{a.channel_id}/messages",
                            params={"$top": a.limit},
                        )
                    ).json()
                )
            return {
                "messages": [
                    {
                        "id": m.get("id"),
                        "from": ((m.get("from") or {}).get("user") or {}).get("displayName"),
                        "created_at": m.get("createdDateTime"),
                        "text": self.wrap(
                            _strip_html((m.get("body") or {}).get("content", "")), ref=a.channel_id
                        ),
                    }
                    for m in msgs
                ],
                "sources": [self.source(object_id=a.channel_id, title="Teams channel", url=None)],
            }

        async def search_messages(ctx: ProviderContext, a: SearchMessagesArgs) -> dict[str, Any]:
            async with self.http(ctx) as http:
                body = (
                    await http.post(
                        "/search/query",
                        json={
                            "requests": [
                                {
                                    "entityTypes": ["chatMessage"],
                                    "query": {"queryString": a.query},
                                    "from": 0,
                                    "size": a.limit,
                                }
                            ]
                        },
                    )
                ).json()
            hits: list[dict[str, Any]] = []
            for container in body.get("value") or []:
                for hc in container.get("hitsContainers") or []:
                    hits.extend(hc.get("hits") or [])
            return {
                "results": [
                    {
                        "id": h.get("hitId"),
                        "summary": self.wrap(
                            _strip_html(str(h.get("summary", ""))), ref=str(h.get("hitId"))
                        ),
                        "from": (
                            ((h.get("resource") or {}).get("from") or {}).get("user") or {}
                        ).get("displayName"),
                        "created_at": (h.get("resource") or {}).get("createdDateTime"),
                        "web_url": (h.get("resource") or {}).get("webUrl"),
                    }
                    for h in hits
                ],
                "sources": [
                    self.source(
                        object_id=str(h.get("hitId", "")),
                        title="Teams message",
                        url=(h.get("resource") or {}).get("webUrl"),
                    )
                    for h in hits
                ],
            }

        async def send_channel_message(
            ctx: ProviderContext, a: SendChannelMessageArgs
        ) -> dict[str, Any]:
            async with self.http(ctx) as http:
                msg = (
                    await http.post(
                        f"/teams/{a.team_id}/channels/{a.channel_id}/messages",
                        json={"body": {"contentType": "text", "content": a.text}},
                    )
                ).json()
            return {"message_id": msg.get("id"), "web_url": msg.get("webUrl")}

        async def reply_to_message(ctx: ProviderContext, a: ReplyToMessageArgs) -> dict[str, Any]:
            async with self.http(ctx) as http:
                msg = (
                    await http.post(
                        f"/teams/{a.team_id}/channels/{a.channel_id}/messages/"
                        f"{a.message_id}/replies",
                        json={"body": {"contentType": "text", "content": a.text}},
                    )
                ).json()
            return {"reply_id": msg.get("id"), "web_url": msg.get("webUrl")}

        async def create_meeting(ctx: ProviderContext, a: CreateMeetingArgs) -> dict[str, Any]:
            end = a.end or a.start + timedelta(minutes=30)
            async with self.http(ctx) as http:
                meeting = (
                    await http.post(
                        "/me/onlineMeetings",
                        json={
                            "subject": a.subject,
                            "startDateTime": a.start.isoformat(),
                            "endDateTime": end.isoformat(),
                        },
                    )
                ).json()
            return {
                "meeting_id": meeting.get("id"),
                "join_url": meeting.get("joinWebUrl"),
                "subject": a.subject,
                "start": a.start.isoformat(),
            }

        async def verify_reply(
            ctx: ProviderContext, a: ReplyToMessageArgs, result: dict[str, Any]
        ) -> Verification:
            async with self.http(ctx) as http:
                msg = (
                    await http.get(
                        f"/teams/{a.team_id}/channels/{a.channel_id}/messages/{a.message_id}"
                        f"/replies/{result['reply_id']}"
                    )
                ).json()
            if msg.get("deletedDateTime"):
                return Verification.failed("The reply was deleted")
            return Verification.verified("Reply is visible in the thread")

        async def verify_meeting(
            ctx: ProviderContext, a: CreateMeetingArgs, result: dict[str, Any]
        ) -> Verification:
            async with self.http(ctx) as http:
                meeting = (await http.get(f"/me/onlineMeetings/{result['meeting_id']}")).json()
            if not meeting.get("joinWebUrl"):
                return Verification.failed("The meeting has no join link")
            return Verification.verified("Teams meeting is ready to join")

        async def verify_send_channel_message(
            ctx: ProviderContext, a: SendChannelMessageArgs, result: dict[str, Any]
        ) -> Verification:
            async with self.http(ctx) as http:
                msg = (
                    await http.get(
                        f"/teams/{a.team_id}/channels/{a.channel_id}/messages/"
                        f"{result['message_id']}"
                    )
                ).json()
            if msg.get("deletedDateTime"):
                return Verification.failed("The message was deleted")
            return Verification.verified("Message is visible in the channel")

        return [
            ProviderTool(
                "search_messages",
                "Search Teams messages you can see.",
                SearchMessagesArgs,
                Capability.search,
                search_messages,
                lambda a: f"Search Teams for “{a.query}”",
                scope="ChannelMessage.Read.All",
                outputs=(
                    listing(
                        "results",
                        "Messages",
                        F("summary", "Message"),
                        F("from", "From"),
                        F("created_at", "Sent", "date"),
                        F("web_url", "Link", "url"),
                    ),
                ),
            ),
            ProviderTool(
                "list_teams",
                "List your teams and channels.",
                ListTeamsArgs,
                Capability.read,
                list_teams,
                lambda a: "List Teams channels",
                outputs=(listing("teams", "Teams", F("name", "Team")),),
            ),
            ProviderTool(
                "read_channel",
                "Read recent channel messages.",
                ReadChannelArgs,
                Capability.read,
                read_channel,
                lambda a: "Read a Teams channel",
                outputs=(
                    listing(
                        "messages",
                        "Messages",
                        F("text", "Message"),
                        F("from", "From"),
                        F("created_at", "Sent", "date"),
                    ),
                ),
            ),
            ProviderTool(
                "send_channel_message",
                "Post a channel message as you.",
                SendChannelMessageArgs,
                Capability.send,
                send_channel_message,
                lambda a: f"Post to Teams channel: “{a.text[:60]}”",
                verify=verify_send_channel_message,
                scope=SEND,
                outputs=(F("message_id", "Message ID"), F("web_url", "Link", "url")),
            ),
            ProviderTool(
                "reply_to_message",
                "Reply in a Teams channel thread as you.",
                ReplyToMessageArgs,
                Capability.send,
                reply_to_message,
                lambda a: f"Reply in Teams thread: “{a.text[:60]}”",
                verify=verify_reply,
                scope=SEND,
                outputs=(F("web_url", "Link", "url"),),
            ),
            ProviderTool(
                "create_meeting",
                "Create a Teams meeting and get its join link.",
                CreateMeetingArgs,
                Capability.schedule,
                create_meeting,
                lambda a: (
                    f"Create Teams meeting “{a.subject}” at {a.start.isoformat(timespec='minutes')}"
                ),
                verify=verify_meeting,
                scope=MEETINGS,
                outputs=(F("join_url", "Join link", "url"), F("start", "Starts", "date")),
            ),
        ]
