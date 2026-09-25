"""Outlook (mail + calendar) via Microsoft Graph. Drafts are writes; sending is external."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, EmailStr, Field

from app.ai.tools.base import OutputField as F
from app.ai.tools.base import Verification
from app.integrations.base.capabilities import Capability
from app.integrations.base.outputs import HIT_FIELDS, listing
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
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html or "")).strip()


class SearchMailArgs(BaseModel):
    """Search your mailbox."""

    query: str = Field(min_length=1, max_length=200)
    limit: int = Field(default=10, ge=1, le=25)


class ListMailArgs(BaseModel):
    """List recent emails, newest first: e.g. unread mail received since today."""

    folder: Literal["inbox", "sentitems", "drafts", "archive"] = "inbox"
    unread_only: bool = False
    received_after: datetime | None = Field(
        default=None, description="Only mail received after this moment (ISO 8601)"
    )
    from_address: EmailStr | None = None
    limit: int = Field(default=15, ge=1, le=50)


class FindPeopleArgs(BaseModel):
    """Find people you email by name, to get their address."""

    query: str = Field(min_length=1, max_length=120)
    limit: int = Field(default=5, ge=1, le=20)


class EmailReceivedParams(BaseModel):
    """Which new emails start the automation."""

    folder: Literal["inbox", "archive"] = "inbox"
    from_address: EmailStr | None = Field(default=None, description="Only mail from this sender")


class ReadMailArgs(BaseModel):
    """Read one email by id."""

    message_id: str = Field(min_length=1, max_length=300)


class DraftMailArgs(BaseModel):
    """Create an email draft (not sent)."""

    to: list[EmailStr] = Field(min_length=1, max_length=20)
    subject: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1, max_length=20_000)


class SendMailArgs(BaseModel):
    """Send an email immediately."""

    to: list[EmailStr] = Field(min_length=1, max_length=20)
    subject: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1, max_length=20_000)


class ListEventsArgs(BaseModel):
    """List calendar events in a window (defaults to the next 7 days)."""

    start: datetime | None = None
    end: datetime | None = None
    limit: int = Field(default=20, ge=1, le=50)


class CreateEventArgs(BaseModel):
    """Create a calendar event."""

    subject: str = Field(min_length=1, max_length=300)
    start: datetime
    end: datetime
    attendees: list[EmailStr] = Field(default_factory=list, max_length=50)
    body: str | None = Field(default=None, max_length=5000)
    timezone: str = Field(default="UTC", max_length=80)


def _snippet(m: dict[str, Any]) -> str:
    sender = ((m.get("from") or {}).get("emailAddress") or {}).get("name", "")
    return f"{sender}: {m.get('bodyPreview', '')}"[:240]


MAIL_WRITE = "Mail.ReadWrite"
MAIL_SEND = "Mail.Send"
CALENDAR_WRITE = "Calendars.ReadWrite"
PEOPLE_READ = "People.Read"


def _recipients(addresses: list[str]) -> list[dict[str, Any]]:
    return [{"emailAddress": {"address": a}} for a in addresses]


class OutlookProvider(MicrosoftGraphProvider):
    manifest = ProviderManifest(
        id="outlook",
        name="Outlook",
        category="email_calendar",
        description="Search and read mail and calendar; draft, send and schedule with approval.",
        logo_url="https://cdn.simpleicons.org/microsoftoutlook",
        docs_url="https://learn.microsoft.com/graph/api/resources/mail-api-overview",
        auth=AuthType.oauth2,
        capabilities=[
            Capability.search,
            Capability.read,
            Capability.draft,
            Capability.send,
            Capability.schedule,
        ],
        permissions=[
            PermissionSpec(
                scope="User.Read", label="Read your profile", capability=Capability.read
            ),
            PermissionSpec(
                scope="Mail.Read", label="Read and search your mail", capability=Capability.read
            ),
            PermissionSpec(
                scope="Calendars.Read", label="Read your calendar", capability=Capability.read
            ),
            PermissionSpec(scope="offline_access", label="Stay connected (refresh tokens)"),
            PermissionSpec(
                scope=MAIL_WRITE,
                label="Create drafts",
                required=False,
                capability=Capability.draft,
            ),
            PermissionSpec(
                scope=MAIL_SEND,
                label="Send mail as you",
                required=False,
                capability=Capability.send,
            ),
            PermissionSpec(
                scope=CALENDAR_WRITE,
                label="Create calendar events",
                required=False,
                capability=Capability.schedule,
            ),
            PermissionSpec(
                scope=PEOPLE_READ,
                label="Look up people you work with",
                description="Lets the assistant find an address from a name.",
                required=False,
                capability=Capability.read,
            ),
        ],
    )

    async def search(self, ctx: ProviderContext, query: str, limit: int) -> list[dict[str, Any]]:
        async with self.http(ctx) as http:
            body = (
                await http.get(
                    "/me/messages",
                    params={
                        "$search": f'"{query}"',
                        "$top": limit,
                        "$select": "id,subject,from,receivedDateTime,bodyPreview,webLink",
                    },
                )
            ).json()
        return [
            {
                "id": m["id"],
                "kind": "email",
                "title": m.get("subject") or "(no subject)",
                "snippet": _snippet(m),
                "url": m.get("webLink"),
                "updated_at": m.get("receivedDateTime"),
            }
            for m in self.graph_page(body)
        ]

    def build_triggers(self) -> list[ProviderTrigger]:
        async def email_received(
            ctx: ProviderContext, p: EmailReceivedParams, since: datetime
        ) -> list[TriggerEvent]:
            clauses = [
                f"receivedDateTime gt {since.astimezone(UTC).strftime('%Y-%m-%dT%H:%M:%SZ')}"
            ]
            if p.from_address:
                safe = str(p.from_address).replace("'", "''")
                clauses.append(f"from/emailAddress/address eq '{safe}'")
            async with self.http(ctx) as http:
                body = (
                    await http.get(
                        f"/me/mailFolders/{p.folder}/messages",
                        params={
                            "$filter": " and ".join(clauses),
                            "$orderby": "receivedDateTime desc",
                            "$top": 25,
                            "$select": "id,subject,from,receivedDateTime,bodyPreview,webLink,"
                            "importance,hasAttachments",
                        },
                    )
                ).json()
            events = []
            for m in self.graph_page(body):
                received = parse_time(m.get("receivedDateTime"))
                if received is None:
                    continue
                sender = (m.get("from") or {}).get("emailAddress") or {}
                events.append(
                    TriggerEvent(
                        id=str(m["id"]),
                        occurred_at=received,
                        data={
                            "message_id": m["id"],
                            "subject": m.get("subject") or "(no subject)",
                            "from_address": sender.get("address"),
                            "from_name": sender.get("name"),
                            "preview": m.get("bodyPreview") or "",
                            "received_at": m.get("receivedDateTime"),
                            "important": m.get("importance") == "high",
                            "has_attachments": bool(m.get("hasAttachments")),
                            "url": m.get("webLink"),
                        },
                    )
                )
            return events

        return [
            ProviderTrigger(
                "email_received",
                "New email received",
                "Starts when a new email arrives in your Outlook inbox.",
                email_received,
                EmailReceivedParams,
                outputs=(
                    F("subject", "Subject"),
                    F("from_address", "From (address)"),
                    F("from_name", "From (name)"),
                    F("preview", "Preview", "long_text"),
                    F("received_at", "Received", "date"),
                    F("important", "Marked important", "boolean"),
                    F("message_id", "Email ID"),
                    F("url", "Link", "url"),
                ),
                scope="Mail.Read",
            )
        ]

    def build_tools(self):  # type: ignore[no-untyped-def]
        async def search_mail(ctx: ProviderContext, a: SearchMailArgs) -> dict[str, Any]:
            hits = await self.search(ctx, a.query, a.limit)
            return {
                "results": [{**h, "snippet": self.wrap(h["snippet"], ref=h["id"])} for h in hits],
                "sources": [
                    self.source(object_id=h["id"], title=h["title"], url=h["url"]) for h in hits
                ],
            }

        async def list_mail(ctx: ProviderContext, a: ListMailArgs) -> dict[str, Any]:
            # $filter + $orderby (not $search, which Graph refuses to combine with either).
            clauses = []
            if a.unread_only:
                clauses.append("isRead eq false")
            if a.received_after:
                when = a.received_after.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
                clauses.append(f"receivedDateTime ge {when}")
            if a.from_address:
                safe = str(a.from_address).replace("'", "''")
                clauses.append(f"from/emailAddress/address eq '{safe}'")
            params: dict[str, Any] = {
                "$top": a.limit,
                "$orderby": "receivedDateTime desc",
                "$select": "id,subject,from,receivedDateTime,bodyPreview,isRead,importance,webLink",
            }
            if clauses:
                params["$filter"] = " and ".join(clauses)
            async with self.http(ctx) as http:
                body = (
                    await http.get(f"/me/mailFolders/{a.folder}/messages", params=params)
                ).json()
            messages = self.graph_page(body)
            return {
                "emails": [
                    {
                        "id": m["id"],
                        "subject": self.wrap(m.get("subject") or "(no subject)", ref=m["id"]),
                        "from": ((m.get("from") or {}).get("emailAddress") or {}).get("address"),
                        "received_at": m.get("receivedDateTime"),
                        "unread": not m.get("isRead", True),
                        "important": m.get("importance") == "high",
                        "preview": self.wrap(m.get("bodyPreview") or "", ref=m["id"]),
                        "url": m.get("webLink"),
                    }
                    for m in messages
                ],
                "sources": [
                    self.source(
                        object_id=m["id"],
                        title=m.get("subject") or "(no subject)",
                        url=m.get("webLink"),
                    )
                    for m in messages
                ],
            }

        async def find_people(ctx: ProviderContext, a: FindPeopleArgs) -> dict[str, Any]:
            async with self.http(ctx) as http:
                body = (
                    await http.get(
                        "/me/people",
                        params={
                            "$search": f'"{a.query}"',
                            "$top": a.limit,
                            "$select": "displayName,scoredEmailAddresses,jobTitle",
                        },
                    )
                ).json()
            return {
                "people": [
                    {
                        "name": p.get("displayName"),
                        "email": next(
                            (e.get("address") for e in p.get("scoredEmailAddresses") or []), None
                        ),
                        "title": p.get("jobTitle"),
                    }
                    for p in self.graph_page(body)
                ]
            }

        async def read_mail(ctx: ProviderContext, a: ReadMailArgs) -> dict[str, Any]:
            async with self.http(ctx) as http:
                m = (
                    await http.get(
                        f"/me/messages/{a.message_id}",
                        params={
                            "$select": "id,subject,from,toRecipients,receivedDateTime,body,webLink"
                        },
                    )
                ).json()
            body = m.get("body") or {}
            text = (
                _strip_html(body.get("content", ""))
                if body.get("contentType", "").lower() == "html"
                else str(body.get("content", ""))
            )
            return {
                "id": m.get("id"),
                "subject": m.get("subject"),
                "from": ((m.get("from") or {}).get("emailAddress") or {}).get("address"),
                "received_at": m.get("receivedDateTime"),
                "content": self.wrap(text[:12_000], ref=a.message_id),
                "sources": [
                    self.source(
                        object_id=a.message_id,
                        title=m.get("subject") or "(no subject)",
                        url=m.get("webLink"),
                    )
                ],
            }

        async def draft_mail(ctx: ProviderContext, a: DraftMailArgs) -> dict[str, Any]:
            payload = {
                "subject": a.subject,
                "body": {"contentType": "Text", "content": a.body},
                "toRecipients": _recipients(list(a.to)),
            }
            async with self.http(ctx) as http:
                draft = (await http.post("/me/messages", json=payload)).json()
            return {
                "draft_id": draft.get("id"),
                "web_url": draft.get("webLink"),
                "subject": a.subject,
            }

        async def send_mail(ctx: ProviderContext, a: SendMailArgs) -> dict[str, Any]:
            payload = {
                "message": {
                    "subject": a.subject,
                    "body": {"contentType": "Text", "content": a.body},
                    "toRecipients": _recipients(list(a.to)),
                },
                "saveToSentItems": True,
            }
            async with self.http(ctx) as http:
                await http.post("/me/sendMail", json=payload)
            return {"sent": True, "to": list(a.to), "subject": a.subject}

        async def list_events(ctx: ProviderContext, a: ListEventsArgs) -> dict[str, Any]:
            from datetime import timedelta

            start = a.start or datetime.now(UTC)
            end = a.end or start + timedelta(days=7)
            async with self.http(ctx) as http:
                body = (
                    await http.get(
                        "/me/calendarView",
                        params={
                            "startDateTime": start.isoformat(),
                            "endDateTime": end.isoformat(),
                            "$top": a.limit,
                            "$select": "id,subject,start,end,attendees,webLink,organizer",
                        },
                    )
                ).json()
            return {
                "events": [
                    {
                        "id": e.get("id"),
                        "subject": self.wrap(e.get("subject", ""), ref=str(e.get("id"))),
                        "start": (e.get("start") or {}).get("dateTime"),
                        "end": (e.get("end") or {}).get("dateTime"),
                        "attendees": [
                            ((x.get("emailAddress") or {}).get("address"))
                            for x in e.get("attendees", [])
                        ],
                        "url": e.get("webLink"),
                    }
                    for e in self.graph_page(body)
                ]
            }

        async def create_event(ctx: ProviderContext, a: CreateEventArgs) -> dict[str, Any]:
            payload: dict[str, Any] = {
                "subject": a.subject,
                "start": {
                    "dateTime": a.start.replace(tzinfo=None).isoformat(),
                    "timeZone": a.timezone,
                },
                "end": {"dateTime": a.end.replace(tzinfo=None).isoformat(), "timeZone": a.timezone},
                "attendees": [
                    {"emailAddress": {"address": x}, "type": "required"} for x in a.attendees
                ],
            }
            if a.body:
                payload["body"] = {"contentType": "Text", "content": a.body}
            async with self.http(ctx) as http:
                event = (await http.post("/me/events", json=payload)).json()
            return {
                "event_id": event.get("id"),
                "web_url": event.get("webLink"),
                "subject": a.subject,
            }

        async def verify_draft_mail(
            ctx: ProviderContext, a: DraftMailArgs, result: dict[str, Any]
        ) -> Verification:
            async with self.http(ctx) as http:
                msg = (
                    await http.get(
                        f"/me/messages/{result['draft_id']}", params={"$select": "isDraft,subject"}
                    )
                ).json()
            if msg.get("isDraft") is False:
                return Verification.failed("The message is not a draft any more")
            return Verification.verified("Draft is in your Outlook drafts")

        async def verify_send_mail(
            ctx: ProviderContext, a: SendMailArgs, result: dict[str, Any]
        ) -> Verification:
            # sendMail returns nothing to read back; look for the message in Sent Items.
            async with self.http(ctx) as http:
                sent = (
                    await http.get(
                        "/me/mailFolders/sentitems/messages",
                        params={"$top": 10, "$select": "subject", "$orderby": "sentDateTime desc"},
                    )
                ).json()
            if any(m.get("subject") == a.subject for m in sent.get("value", [])):
                return Verification.verified("Message is in Sent Items")
            return Verification.unverified(
                "Message not in Sent Items yet (it may still be sending)"
            )

        async def verify_create_event(
            ctx: ProviderContext, a: CreateEventArgs, result: dict[str, Any]
        ) -> Verification:
            async with self.http(ctx) as http:
                event = (
                    await http.get(
                        f"/me/events/{result['event_id']}",
                        params={"$select": "subject,isCancelled"},
                    )
                ).json()
            if event.get("isCancelled"):
                return Verification.failed("The event is cancelled")
            return Verification.verified("Event is on your calendar")

        return [
            ProviderTool(
                "search_mail",
                "Search your Outlook mail.",
                SearchMailArgs,
                Capability.search,
                search_mail,
                lambda a: f"Search Outlook mail for “{a.query}”",
                outputs=(listing("results", "Emails", *HIT_FIELDS),),
            ),
            ProviderTool(
                "list_mail",
                "List recent Outlook emails, e.g. unread ones received today.",
                ListMailArgs,
                Capability.read,
                list_mail,
                lambda a: (
                    "List " + ("unread " if a.unread_only else "") + f"Outlook mail in {a.folder}"
                ),
                outputs=(
                    listing(
                        "emails",
                        "Emails",
                        F("subject", "Subject"),
                        F("from", "From"),
                        F("received_at", "Received", "date"),
                        F("preview", "Preview", "long_text"),
                        F("url", "Link", "url"),
                    ),
                ),
            ),
            ProviderTool(
                "find_people",
                "Find someone's email address by name.",
                FindPeopleArgs,
                Capability.read,
                find_people,
                lambda a: f"Look up “{a.query}” in Outlook",
                scope=PEOPLE_READ,
                outputs=(listing("people", "People", F("name", "Name"), F("email", "Email")),),
            ),
            ProviderTool(
                "read_mail",
                "Read an email.",
                ReadMailArgs,
                Capability.read,
                read_mail,
                lambda a: "Read an Outlook email",
                outputs=(
                    F("subject", "Subject"),
                    F("from", "From"),
                    F("received_at", "Received", "date"),
                    F("content", "Email text", "long_text"),
                ),
            ),
            ProviderTool(
                "draft_mail",
                "Create an email draft.",
                DraftMailArgs,
                Capability.draft,
                draft_mail,
                lambda a: f"Draft email to {', '.join(a.to)}: “{a.subject}”",
                verify=verify_draft_mail,
                scope=MAIL_WRITE,
                outputs=(F("draft_id", "Draft ID"), F("web_url", "Link", "url")),
            ),
            ProviderTool(
                "send_mail",
                "Send an email now.",
                SendMailArgs,
                Capability.send,
                send_mail,
                lambda a: f"Send email to {', '.join(a.to)}: “{a.subject}”",
                verify=verify_send_mail,
                scope=MAIL_SEND,
            ),
            ProviderTool(
                "list_events",
                "List calendar events.",
                ListEventsArgs,
                Capability.read,
                list_events,
                lambda a: "List Outlook calendar events",
                outputs=(
                    listing(
                        "events",
                        "Events",
                        F("subject", "Title"),
                        F("start", "Starts", "date"),
                        F("end", "Ends", "date"),
                        F("attendees", "Attendees", "list"),
                        F("url", "Link", "url"),
                    ),
                ),
            ),
            ProviderTool(
                "create_event",
                "Create a calendar event.",
                CreateEventArgs,
                Capability.schedule,
                create_event,
                lambda a: f"Create event “{a.subject}” at {a.start.isoformat(timespec='minutes')}",
                verify=verify_create_event,
                scope=CALENDAR_WRITE,
                outputs=(F("event_id", "Event ID"), F("web_url", "Link", "url")),
            ),
        ]
