"""Google Meet, through the Google Meet REST API (v2, GA) — the only supported programmatic
surface for Meet. There is no Meet-specific OAuth: it is the same Google client and consent
screen as Gmail/Calendar/Drive with Meet scopes.

What the API offers (and therefore what this connector does):
- create a meeting space (a join link) and end its active conference: `meetings.space.created`
  (limited to spaces this app created — the least privilege for creation);
- read spaces and past conference records (who joined, when): `meetings.space.readonly`.
Scheduling a Meet *on a calendar* is a Calendar API feature and lives in the Google Calendar
connector; Meet has no search API, so it does not take part in unified search.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.ai.tools.base import Verification
from app.integrations.base.capabilities import Capability
from app.integrations.base.provider import (
    AuthType,
    PermissionSpec,
    ProviderContext,
    ProviderManifest,
)
from app.integrations.base.rest import ProviderTool
from app.integrations.google.base import GoogleProvider

API = "https://meet.googleapis.com/v2"
USERINFO = "https://www.googleapis.com/oauth2/v2"
SCOPE_EMAIL = "https://www.googleapis.com/auth/userinfo.email"
SCOPE_CREATE = "https://www.googleapis.com/auth/meetings.space.created"
SCOPE_READ = "https://www.googleapis.com/auth/meetings.space.readonly"


class CreateSpaceArgs(BaseModel):
    """Create a new Google Meet space (an instant join link)."""

    access_type: str = Field(
        default="TRUSTED",
        pattern="^(OPEN|TRUSTED|RESTRICTED)$",
        description=(
            "OPEN: anyone with the link; TRUSTED: org members join directly, others knock; "
            "RESTRICTED: invited only."
        ),
    )


class GetSpaceArgs(BaseModel):
    """Details of a meeting space by its code (e.g. `abc-mnop-xyz`) or resource name."""

    space: str = Field(min_length=3, max_length=80)


class EndConferenceArgs(BaseModel):
    """End the active conference in a space you created."""

    space: str = Field(min_length=3, max_length=80)


class ListConferenceRecordsArgs(BaseModel):
    """Recent past meetings (conference records), newest first."""

    limit: int = Field(default=10, ge=1, le=50)


def _space_name(value: str) -> str:
    return value if value.startswith("spaces/") else f"spaces/{value}"


class GoogleMeetProvider(GoogleProvider):
    api_base = API
    manifest = ProviderManifest(
        id="google_meet",
        name="Google Meet",
        category="meetings",
        description="Create Meet links, look up meeting spaces and review past meetings.",
        logo_url="https://cdn.simpleicons.org/googlemeet",
        docs_url="https://developers.google.com/meet/api/guides/overview",
        auth=AuthType.oauth2,
        capabilities=[Capability.read, Capability.create, Capability.update],
        permissions=[
            PermissionSpec(
                scope=SCOPE_EMAIL,
                label="See which Google account is connected",
                capability=Capability.read,
            ),
            PermissionSpec(
                scope=SCOPE_READ,
                label="See meeting spaces and past meetings",
                description="Join links, who attended and when. Never recordings or transcripts.",
                capability=Capability.read,
            ),
            PermissionSpec(
                scope=SCOPE_CREATE,
                label="Create Meet links and end meetings Notely created",
                description="Only when you approve an action.",
                required=False,
                capability=Capability.create,
            ),
        ],
    )

    async def account_email(self, ctx: ProviderContext) -> str:
        async with self.http(ctx, USERINFO) as http:
            me = (await http.get("/userinfo")).json()
        return str(me.get("email") or "Google Meet")

    async def probe(self, ctx: ProviderContext) -> str:
        async with self.http(ctx) as http:
            body = (await http.get("/conferenceRecords", params={"pageSize": 1})).json()
        return "Meet API reachable" if isinstance(body, dict) else "ok"

    def build_tools(self) -> list[ProviderTool]:
        async def create_space(ctx: ProviderContext, a: CreateSpaceArgs) -> dict[str, Any]:
            async with self.http(ctx) as http:
                space = (
                    await http.post("/spaces", json={"config": {"accessType": a.access_type}})
                ).json()
            return {
                "space": space.get("name"),
                "meeting_code": space.get("meetingCode"),
                "url": space.get("meetingUri"),
            }

        async def verify_create(
            ctx: ProviderContext, a: CreateSpaceArgs, result: dict[str, Any]
        ) -> Verification:
            async with self.http(ctx) as http:
                space = (await http.get(f"/{result['space']}")).json()
            if space.get("meetingUri") != result.get("url"):
                return Verification.failed("The space could not be read back")
            return Verification.verified("Meet link is live")

        async def get_space(ctx: ProviderContext, a: GetSpaceArgs) -> dict[str, Any]:
            async with self.http(ctx) as http:
                space = (await http.get(f"/{_space_name(a.space)}")).json()
            active = space.get("activeConference") or {}
            return {
                "space": space.get("name"),
                "meeting_code": space.get("meetingCode"),
                "url": space.get("meetingUri"),
                "access_type": (space.get("config") or {}).get("accessType"),
                "active_conference": active.get("conferenceRecord"),
                "sources": [
                    self.source(
                        object_id=str(space.get("name", "")),
                        title=str(space.get("meetingCode", "Meet space")),
                        url=space.get("meetingUri"),
                    )
                ],
            }

        async def end_active_conference(
            ctx: ProviderContext, a: EndConferenceArgs
        ) -> dict[str, Any]:
            async with self.http(ctx) as http:
                await http.post(f"/{_space_name(a.space)}:endActiveConference", json={})
            return {"space": _space_name(a.space), "ended": True}

        async def verify_end(
            ctx: ProviderContext, a: EndConferenceArgs, result: dict[str, Any]
        ) -> Verification:
            async with self.http(ctx) as http:
                space = (await http.get(f"/{result['space']}")).json()
            if space.get("activeConference"):
                return Verification.failed("The conference is still active")
            return Verification.verified("No active conference in the space")

        async def list_conference_records(
            ctx: ProviderContext, a: ListConferenceRecordsArgs
        ) -> dict[str, Any]:
            async with self.http(ctx) as http:
                body = (await http.get("/conferenceRecords", params={"pageSize": a.limit})).json()
            records = self.items(body, "conferenceRecords")
            return {
                "meetings": [
                    {
                        "record": r.get("name"),
                        "space": self.wrap(str(r.get("space", "")), ref=str(r.get("name", ""))),
                        "started_at": r.get("startTime"),
                        "ended_at": r.get("endTime"),
                    }
                    for r in records
                ],
                "sources": [
                    self.source(
                        object_id=str(r.get("name", "")),
                        title=f"Meeting on {str(r.get('startTime', ''))[:10]}",
                        url=None,
                    )
                    for r in records
                ],
            }

        return [
            ProviderTool(
                "create_space",
                "Create a Google Meet link.",
                CreateSpaceArgs,
                Capability.create,
                create_space,
                lambda a: "Create a Google Meet link",
                verify=verify_create,
                scope=SCOPE_CREATE,
            ),
            ProviderTool(
                "get_space",
                "Look up a Meet space by meeting code.",
                GetSpaceArgs,
                Capability.read,
                get_space,
                lambda a: f"Look up Meet space {a.space}",
                scope=SCOPE_READ,
            ),
            ProviderTool(
                "list_conference_records",
                "List recent past meetings.",
                ListConferenceRecordsArgs,
                Capability.read,
                list_conference_records,
                lambda a: "List recent Meet meetings",
                scope=SCOPE_READ,
            ),
            ProviderTool(
                "end_active_conference",
                "End the active meeting in a space Notely created.",
                EndConferenceArgs,
                Capability.update,
                end_active_conference,
                lambda a: f"End the meeting in {a.space}",
                verify=verify_end,
                scope=SCOPE_CREATE,
            ),
        ]
