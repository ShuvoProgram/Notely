"""Microsoft Teams via Graph: teams, channels, channel messages, sending as the user."""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field

from app.integrations.base.capabilities import Capability
from app.integrations.base.provider import (
    AuthType,
    PermissionSpec,
    ProviderContext,
    ProviderManifest,
)
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


class SendChannelMessageArgs(BaseModel):
    """Post a message to a channel as you."""

    team_id: str = Field(min_length=1, max_length=80)
    channel_id: str = Field(min_length=1, max_length=120)
    text: str = Field(min_length=1, max_length=4000)


class TeamsProvider(MicrosoftGraphProvider):
    manifest = ProviderManifest(
        id="microsoft_teams",
        name="Microsoft Teams",
        category="communication",
        description="Read your teams and channel messages; post to channels with approval.",
        logo_url="https://cdn.simpleicons.org/microsoftteams",
        docs_url="https://learn.microsoft.com/graph/api/resources/teams-api-overview",
        auth=AuthType.oauth2,
        capabilities=[Capability.read, Capability.send],
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
                scope="ChannelMessage.Send",
                label="Post channel messages as you",
                required=False,
                capability=Capability.send,
            ),
        ],
    )

    async def probe(self, ctx: ProviderContext) -> str:
        async with self.http(ctx) as http:
            teams = self.graph_page((await http.get("/me/joinedTeams")).json())
        return f"{len(teams)} team(s)"

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

        return [
            (
                "list_teams",
                "List your teams and channels.",
                ListTeamsArgs,
                Capability.read,
                list_teams,
                lambda a: "List Teams channels",
            ),
            (
                "read_channel",
                "Read recent channel messages.",
                ReadChannelArgs,
                Capability.read,
                read_channel,
                lambda a: "Read a Teams channel",
            ),
            (
                "send_channel_message",
                "Post a channel message as you.",
                SendChannelMessageArgs,
                Capability.send,
                send_channel_message,
                lambda a: f"Post to Teams channel: “{a.text[:60]}”",
            ),
        ]
