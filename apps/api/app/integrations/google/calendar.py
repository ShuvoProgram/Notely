"""Google Calendar: list/search events; create events with approval."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import BaseModel, EmailStr, Field

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

API = "https://www.googleapis.com/calendar/v3"


class ListEventsArgs(BaseModel):
    """List upcoming events on your primary calendar (optionally filtered by text)."""

    days: int = Field(default=7, ge=1, le=60, description="How many days ahead to look")
    query: str | None = Field(default=None, max_length=200)
    limit: int = Field(default=20, ge=1, le=50)


class CreateEventArgs(BaseModel):
    """Create a calendar event and invite attendees."""

    summary: str = Field(min_length=1, max_length=300)
    start: datetime = Field(description="Start (ISO 8601 with timezone)")
    end: datetime = Field(description="End (ISO 8601 with timezone)")
    attendees: list[EmailStr] = Field(default_factory=list, max_length=50)
    description: str | None = Field(default=None, max_length=5000)


def _when(event: dict[str, Any], key: str) -> str:
    slot = event.get(key) or {}
    return str(slot.get("dateTime") or slot.get("date") or "")


class GoogleCalendarProvider(GoogleProvider):
    api_base = API
    manifest = ProviderManifest(
        id="google_calendar",
        name="Google Calendar",
        category="email_calendar",
        description="See what's on your calendar; schedule events with approval.",
        logo_url="https://cdn.simpleicons.org/googlecalendar",
        docs_url="https://developers.google.com/calendar/api/guides/overview",
        auth=AuthType.oauth2,
        capabilities=[Capability.search, Capability.read, Capability.schedule],
        permissions=[
            PermissionSpec(
                scope="https://www.googleapis.com/auth/calendar.readonly",
                label="Read your calendars and events",
                capability=Capability.read,
            ),
            PermissionSpec(
                scope="https://www.googleapis.com/auth/calendar.events",
                label="Create and update events",
                required=False,
                capability=Capability.schedule,
            ),
        ],
    )

    async def probe(self, ctx: ProviderContext) -> str:
        async with self.http(ctx) as http:
            cal = (await http.get("/calendars/primary")).json()
        return f"Primary calendar: {cal.get('summary', 'ok')}"

    async def _events(
        self, ctx: ProviderContext, *, days: int, query: str | None, limit: int
    ) -> list[dict[str, Any]]:
        now = datetime.now(UTC)
        params: dict[str, Any] = {
            "timeMin": now.isoformat(),
            "timeMax": (now + timedelta(days=days)).isoformat(),
            "singleEvents": "true",
            "orderBy": "startTime",
            "maxResults": limit,
        }
        if query:
            params["q"] = query
        async with self.http(ctx) as http:
            body = (await http.get("/calendars/primary/events", params=params)).json()
        return self.items(body, "items")

    async def search(self, ctx: ProviderContext, query: str, limit: int) -> list[dict[str, Any]]:
        return [
            {
                "id": e["id"],
                "kind": "event",
                "title": e.get("summary") or "(untitled event)",
                "snippet": f"{_when(e, 'start')} → {_when(e, 'end')}",
                "url": e.get("htmlLink"),
                "updated_at": e.get("updated"),
            }
            for e in await self._events(ctx, days=30, query=query, limit=limit)
        ]

    def build_tools(self) -> list[ProviderTool]:
        async def list_events(ctx: ProviderContext, a: ListEventsArgs) -> dict[str, Any]:
            events = await self._events(ctx, days=a.days, query=a.query, limit=a.limit)
            return {
                "events": [
                    {
                        "event_id": e["id"],
                        "summary": self.wrap(str(e.get("summary", "")), ref=e["id"]),
                        "start": _when(e, "start"),
                        "end": _when(e, "end"),
                        "attendees": [
                            str(x.get("email", "")) for x in e.get("attendees", []) or []
                        ],
                        "url": e.get("htmlLink"),
                    }
                    for e in events
                ],
                "sources": [
                    self.source(
                        object_id=e["id"],
                        title=str(e.get("summary") or "(untitled event)"),
                        url=e.get("htmlLink"),
                    )
                    for e in events
                ],
            }

        async def create_event(ctx: ProviderContext, a: CreateEventArgs) -> dict[str, Any]:
            payload: dict[str, Any] = {
                "summary": a.summary,
                "start": {"dateTime": a.start.isoformat()},
                "end": {"dateTime": a.end.isoformat()},
                "attendees": [{"email": x} for x in a.attendees],
            }
            if a.description:
                payload["description"] = a.description
            async with self.http(ctx) as http:
                event = (
                    await http.post(
                        "/calendars/primary/events",
                        params={"sendUpdates": "all" if a.attendees else "none"},
                        json=payload,
                    )
                ).json()
            return {"event_id": event.get("id"), "url": event.get("htmlLink"), "summary": a.summary}

        async def verify_event(
            ctx: ProviderContext, a: CreateEventArgs, result: dict[str, Any]
        ) -> Verification:
            async with self.http(ctx) as http:
                event = (await http.get(f"/calendars/primary/events/{result['event_id']}")).json()
            if event.get("status") == "cancelled":
                return Verification.failed("The event is cancelled")
            return Verification.verified("Event is on your Google Calendar")

        return [
            ProviderTool(
                "list_events",
                "List upcoming events on your primary calendar.",
                ListEventsArgs,
                Capability.read,
                list_events,
                lambda a: f"List events for the next {a.days} day(s)",
            ),
            ProviderTool(
                "create_event",
                "Create a calendar event (invites attendees).",
                CreateEventArgs,
                Capability.schedule,
                create_event,
                lambda a: f"Create event “{a.summary}” at {a.start.isoformat()}",
                verify=verify_event,
            ),
        ]
