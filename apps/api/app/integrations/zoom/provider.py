"""Zoom: meetings on the connected user's account, through the Zoom REST API (v2) with a
user-managed OAuth app.

Zoom specifics worth knowing:
- Scopes are *granular* (`meeting:read:list_meetings`, `meeting:write:meeting`, …) and are
  configured on the app in the Zoom Marketplace, not chosen per authorization: the authorize
  URL carries no scope parameter and the token response reports what was granted. Tools are
  offered only for scopes the token actually has.
- The token endpoint wants HTTP Basic client auth; access tokens last an hour and refresh
  tokens rotate on every refresh (the framework stores the new one).
- An unpublished app can only be authorized by users of the developer's own Zoom account;
  publishing to the Marketplace (Zoom's review) lifts that. Documented in .env.example.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.ai.tools.base import OutputField as F
from app.ai.tools.base import Verification
from app.core.oauth import OAuthEndpoints
from app.integrations.base.capabilities import Capability
from app.integrations.base.outputs import listing
from app.integrations.base.provider import (
    AuthType,
    ConnectionIdentity,
    PermissionSpec,
    ProviderContext,
    ProviderManifest,
)
from app.integrations.base.rest import ProviderTool, RestOAuthProvider

API = "https://api.zoom.us/v2"
SCOPE_USER = "user:read:user"
SCOPE_LIST = "meeting:read:list_meetings"
SCOPE_READ = "meeting:read:meeting"
SCOPE_CREATE = "meeting:write:meeting"
SCOPE_UPDATE = "meeting:update:meeting"
SCOPE_DELETE = "meeting:delete:meeting"


class ListMeetingsArgs(BaseModel):
    """Your upcoming (or past) meetings."""

    kind: str = Field(default="upcoming", pattern="^(upcoming|scheduled|previous_meetings)$")
    limit: int = Field(default=20, ge=1, le=100)


class GetMeetingArgs(BaseModel):
    """Details and join link of one meeting."""

    meeting_id: str = Field(min_length=1, max_length=40)


class CreateMeetingArgs(BaseModel):
    """Schedule a meeting on your Zoom account."""

    topic: str = Field(min_length=1, max_length=200)
    start_time: str | None = Field(
        default=None,
        description="ISO 8601, e.g. 2026-09-23T10:00:00Z. Omit for an instant meeting.",
    )
    duration_minutes: int = Field(default=30, ge=5, le=720)
    timezone: str | None = Field(default=None, max_length=64)
    agenda: str | None = Field(default=None, max_length=2000)


class UpdateMeetingArgs(BaseModel):
    """Change a meeting's topic, time, duration or agenda."""

    meeting_id: str = Field(min_length=1, max_length=40)
    topic: str | None = Field(default=None, max_length=200)
    start_time: str | None = None
    duration_minutes: int | None = Field(default=None, ge=5, le=720)
    agenda: str | None = Field(default=None, max_length=2000)


class CancelMeetingArgs(BaseModel):
    """Delete (cancel) a meeting."""

    meeting_id: str = Field(min_length=1, max_length=40)


def _meeting_out(m: dict[str, Any]) -> dict[str, Any]:
    return {
        "meeting_id": str(m.get("id", "")),
        "topic": m.get("topic"),
        "start_time": m.get("start_time"),
        "duration_minutes": m.get("duration"),
        "timezone": m.get("timezone"),
        "join_url": m.get("join_url"),
        "type": m.get("type"),
    }


class ZoomProvider(RestOAuthProvider):
    settings_prefix = "zoom"
    use_pkce = True
    api_base = API
    endpoints = OAuthEndpoints(
        authorize_url="https://zoom.us/oauth/authorize",
        token_url="https://zoom.us/oauth/token",
        token_auth="basic",
        scope_param=None,
    )
    manifest = ProviderManifest(
        id="zoom",
        name="Zoom",
        category="meetings",
        description="See your meetings and join links; schedule, change or cancel with approval.",
        logo_url="https://cdn.simpleicons.org/zoom",
        docs_url="https://developers.zoom.us/docs/integrations/oauth/",
        auth=AuthType.oauth2,
        capabilities=[Capability.read, Capability.schedule, Capability.update, Capability.delete],
        permissions=[
            PermissionSpec(
                scope=SCOPE_USER,
                label="See which Zoom account is connected",
                capability=Capability.read,
            ),
            PermissionSpec(
                scope=SCOPE_LIST, label="List your meetings", capability=Capability.read
            ),
            PermissionSpec(
                scope=SCOPE_READ, label="Read meeting details", capability=Capability.read
            ),
            PermissionSpec(
                scope=SCOPE_CREATE,
                label="Schedule meetings",
                description="Only when you approve an action.",
                required=False,
                capability=Capability.schedule,
            ),
            PermissionSpec(
                scope=SCOPE_UPDATE,
                label="Change meetings",
                description="Only when you approve an action.",
                required=False,
                capability=Capability.update,
            ),
            PermissionSpec(
                scope=SCOPE_DELETE,
                label="Cancel meetings",
                description="Only when you approve an action.",
                required=False,
                capability=Capability.delete,
            ),
        ],
    )

    async def identity(self, ctx: ProviderContext) -> ConnectionIdentity:
        async with self.http(ctx) as http:
            me = (await http.get("/users/me")).json()
        email = str(me.get("email") or "")
        name = " ".join(p for p in (me.get("first_name"), me.get("last_name")) if p) or email
        return ConnectionIdentity(
            external_account_id=str(me.get("id") or email),
            external_account_name=f"{name} ({email})" if name != email else email,
            metadata={"email": email, "account_id": me.get("account_id")},
        )

    async def probe(self, ctx: ProviderContext) -> str:
        async with self.http(ctx) as http:
            body = (
                await http.get("/users/me/meetings", params={"type": "upcoming", "page_size": 1})
            ).json()
        return f"{body.get('total_records', 0)} upcoming meeting(s)"

    def build_tools(self) -> list[ProviderTool]:
        async def list_meetings(ctx: ProviderContext, a: ListMeetingsArgs) -> dict[str, Any]:
            async with self.http(ctx) as http:
                body = (
                    await http.get(
                        "/users/me/meetings", params={"type": a.kind, "page_size": a.limit}
                    )
                ).json()
            meetings = body.get("meetings") if isinstance(body.get("meetings"), list) else []
            return {
                "meetings": [
                    {
                        **_meeting_out(m),
                        "topic": self.wrap(str(m.get("topic", "")), ref=str(m.get("id"))),
                    }
                    for m in meetings
                ],
                "sources": [
                    self.source(
                        object_id=str(m.get("id", "")),
                        title=str(m.get("topic", "")),
                        url=m.get("join_url"),
                    )
                    for m in meetings
                ],
            }

        async def get_meeting(ctx: ProviderContext, a: GetMeetingArgs) -> dict[str, Any]:
            async with self.http(ctx) as http:
                m = (await http.get(f"/meetings/{a.meeting_id}")).json()
            return {
                **_meeting_out(m),
                "topic": self.wrap(str(m.get("topic", "")), ref=a.meeting_id),
                "agenda": self.wrap(str(m.get("agenda") or ""), ref=a.meeting_id),
                "sources": [
                    self.source(
                        object_id=a.meeting_id, title=str(m.get("topic", "")), url=m.get("join_url")
                    )
                ],
            }

        async def create_meeting(ctx: ProviderContext, a: CreateMeetingArgs) -> dict[str, Any]:
            payload: dict[str, Any] = {
                "topic": a.topic,
                "type": 2 if a.start_time else 1,  # 2 = scheduled, 1 = instant
                "duration": a.duration_minutes,
            }
            if a.start_time:
                payload["start_time"] = a.start_time
            if a.timezone:
                payload["timezone"] = a.timezone
            if a.agenda:
                payload["agenda"] = a.agenda
            async with self.http(ctx) as http:
                m = (await http.post("/users/me/meetings", json=payload)).json()
            return _meeting_out(m)

        async def verify_create(
            ctx: ProviderContext, a: CreateMeetingArgs, result: dict[str, Any]
        ) -> Verification:
            async with self.http(ctx) as http:
                m = (await http.get(f"/meetings/{result['meeting_id']}")).json()
            if m.get("topic") != a.topic:
                return Verification.failed("Meeting exists but its topic differs")
            return Verification.verified("Meeting is on your Zoom account")

        async def update_meeting(ctx: ProviderContext, a: UpdateMeetingArgs) -> dict[str, Any]:
            payload = {
                k: v
                for k, v in {
                    "topic": a.topic,
                    "start_time": a.start_time,
                    "duration": a.duration_minutes,
                    "agenda": a.agenda,
                }.items()
                if v is not None
            }
            async with self.http(ctx) as http:
                await http.patch(f"/meetings/{a.meeting_id}", json=payload)
            return {"meeting_id": a.meeting_id, "updated": sorted(payload)}

        async def verify_update(
            ctx: ProviderContext, a: UpdateMeetingArgs, result: dict[str, Any]
        ) -> Verification:
            async with self.http(ctx) as http:
                m = (await http.get(f"/meetings/{a.meeting_id}")).json()
            if a.topic is not None and m.get("topic") != a.topic:
                return Verification.failed("The topic did not change")
            if a.duration_minutes is not None and m.get("duration") != a.duration_minutes:
                return Verification.failed("The duration did not change")
            return Verification.verified("Meeting reflects the change")

        async def cancel_meeting(ctx: ProviderContext, a: CancelMeetingArgs) -> dict[str, Any]:
            async with self.http(ctx) as http:
                await http.delete(f"/meetings/{a.meeting_id}")
            return {"meeting_id": a.meeting_id, "cancelled": True}

        async def verify_cancel(
            ctx: ProviderContext, a: CancelMeetingArgs, result: dict[str, Any]
        ) -> Verification:
            from app.integrations.base.errors import ProviderError, ProviderErrorKind

            try:
                async with self.http(ctx) as http:
                    await http.get(f"/meetings/{a.meeting_id}")
            except ProviderError as exc:
                if exc.kind == ProviderErrorKind.not_found:
                    return Verification.verified("Meeting no longer exists")
                raise
            return Verification.failed("The meeting still exists")

        return [
            ProviderTool(
                "list_meetings",
                "List your upcoming or past meetings.",
                ListMeetingsArgs,
                Capability.read,
                list_meetings,
                lambda a: f"List {a.kind.replace('_', ' ')} Zoom meetings",
                scope=SCOPE_LIST,
                outputs=(
                    listing(
                        "meetings",
                        "Meetings",
                        F("topic", "Topic"),
                        F("start_time", "Starts", "date"),
                        F("duration_minutes", "Minutes", "number"),
                        F("join_url", "Join link", "url"),
                    ),
                ),
            ),
            ProviderTool(
                "get_meeting",
                "Read one meeting's details and join link.",
                GetMeetingArgs,
                Capability.read,
                get_meeting,
                lambda a: f"Read Zoom meeting {a.meeting_id}",
                scope=SCOPE_READ,
            ),
            ProviderTool(
                "create_meeting",
                "Schedule a Zoom meeting.",
                CreateMeetingArgs,
                Capability.schedule,
                create_meeting,
                lambda a: f"Schedule Zoom meeting “{a.topic}”",
                verify=verify_create,
                scope=SCOPE_CREATE,
            ),
            ProviderTool(
                "update_meeting",
                "Change a meeting's topic, time, duration or agenda.",
                UpdateMeetingArgs,
                Capability.update,
                update_meeting,
                lambda a: f"Update Zoom meeting {a.meeting_id}",
                verify=verify_update,
                scope=SCOPE_UPDATE,
            ),
            ProviderTool(
                "cancel_meeting",
                "Cancel (delete) a meeting.",
                CancelMeetingArgs,
                Capability.delete,
                cancel_meeting,
                lambda a: f"Cancel Zoom meeting {a.meeting_id}",
                verify=verify_cancel,
                scope=SCOPE_DELETE,
            ),
        ]
