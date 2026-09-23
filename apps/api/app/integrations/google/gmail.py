"""Gmail: search and read mail; draft and send with approval."""

from __future__ import annotations

import base64
from email.message import EmailMessage
from typing import Any

from pydantic import BaseModel, EmailStr, Field

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
from app.integrations.google.base import GoogleProvider

API = "https://gmail.googleapis.com/gmail/v1/users/me"
MAX_BODY = 12_000


class SearchMailArgs(BaseModel):
    """Search mail with Gmail query syntax (e.g. 'from:bob subject:pricing newer_than:7d')."""

    query: str = Field(min_length=1, max_length=300)
    limit: int = Field(default=10, ge=1, le=25)


class ReadMailArgs(BaseModel):
    """Read one message by id (ids come from search results)."""

    message_id: str = Field(min_length=1, max_length=80)


class DraftMailArgs(BaseModel):
    """Create a draft in Gmail (nothing is sent)."""

    to: list[EmailStr] = Field(min_length=1, max_length=20)
    subject: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1, max_length=20_000)


class SendMailArgs(BaseModel):
    """Send an email from your Gmail account."""

    to: list[EmailStr] = Field(min_length=1, max_length=20)
    subject: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1, max_length=20_000)


def _raw(to: list[str], subject: str, body: str) -> str:
    msg = EmailMessage()
    msg["To"] = ", ".join(to)
    msg["Subject"] = subject
    msg.set_content(body)
    return base64.urlsafe_b64encode(msg.as_bytes()).decode().rstrip("=")


def _header(message: dict[str, Any], name: str) -> str:
    for h in (message.get("payload") or {}).get("headers", []) or []:
        if str(h.get("name", "")).lower() == name.lower():
            return str(h.get("value", ""))
    return ""


def _decode(data: str) -> str:
    padded = data + "=" * (-len(data) % 4)
    try:
        return base64.urlsafe_b64decode(padded).decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        return ""


def _text_body(payload: dict[str, Any]) -> str:
    """First text/plain part, walking multipart payloads."""
    if not payload:
        return ""
    mime = str(payload.get("mimeType", ""))
    body = payload.get("body") or {}
    if mime == "text/plain" and body.get("data"):
        return _decode(str(body["data"]))
    for part in payload.get("parts", []) or []:
        text = _text_body(part)
        if text:
            return text
    if mime == "text/html" and body.get("data"):
        import re

        return re.sub(r"<[^>]+>", "", _decode(str(body["data"])))
    return ""


class GmailProvider(GoogleProvider):
    api_base = API
    manifest = ProviderManifest(
        id="gmail",
        name="Gmail",
        category="email_calendar",
        description="Search and read your mail; draft and send messages with approval.",
        logo_url="https://cdn.simpleicons.org/gmail",
        docs_url="https://developers.google.com/gmail/api/guides",
        auth=AuthType.oauth2,
        capabilities=[Capability.search, Capability.read, Capability.draft, Capability.send],
        permissions=[
            PermissionSpec(
                scope="https://www.googleapis.com/auth/gmail.readonly",
                label="Read and search your mail",
                capability=Capability.read,
            ),
            PermissionSpec(
                scope="https://www.googleapis.com/auth/gmail.compose",
                label="Create drafts",
                required=False,
                capability=Capability.draft,
            ),
            PermissionSpec(
                scope="https://www.googleapis.com/auth/gmail.send",
                label="Send mail as you",
                required=False,
                capability=Capability.send,
            ),
        ],
    )

    async def account_email(self, ctx: ProviderContext) -> str:
        async with self.http(ctx) as http:
            profile = (await http.get("/profile")).json()
        return str(profile.get("emailAddress") or "Gmail account")

    async def probe(self, ctx: ProviderContext) -> str:
        async with self.http(ctx) as http:
            profile = (await http.get("/profile")).json()
        return f"{profile.get('messagesTotal', '?')} messages in {profile.get('emailAddress', '')}"

    async def _list(self, ctx: ProviderContext, query: str, limit: int) -> list[dict[str, Any]]:
        async with self.http(ctx) as http:
            listing = (await http.get("/messages", params={"q": query, "maxResults": limit})).json()
            out = []
            for ref in self.items(listing, "messages")[:limit]:
                msg = (
                    await http.get(
                        f"/messages/{ref['id']}",
                        params={
                            "format": "metadata",
                            "metadataHeaders": ["Subject", "From", "Date"],
                        },
                    )
                ).json()
                out.append(msg)
        return out

    async def search(self, ctx: ProviderContext, query: str, limit: int) -> list[dict[str, Any]]:
        return [
            {
                "id": m["id"],
                "kind": "email",
                "title": _header(m, "Subject") or "(no subject)",
                "snippet": f"{_header(m, 'From')} · {m.get('snippet', '')}",
                "url": f"https://mail.google.com/mail/u/0/#all/{m['id']}",
                "updated_at": None,
            }
            for m in await self._list(ctx, query, limit)
        ]

    def build_tools(self) -> list[ProviderTool]:
        async def search_mail(ctx: ProviderContext, a: SearchMailArgs) -> dict[str, Any]:
            msgs = await self._list(ctx, a.query, a.limit)
            return {
                "results": [
                    {
                        "message_id": m["id"],
                        "subject": self.wrap(_header(m, "Subject"), ref=m["id"]),
                        "from": self.wrap(_header(m, "From"), ref=m["id"]),
                        "date": _header(m, "Date"),
                        "snippet": self.wrap(str(m.get("snippet", "")), ref=m["id"]),
                    }
                    for m in msgs
                ],
                "sources": [
                    self.source(
                        object_id=m["id"],
                        title=_header(m, "Subject") or "(no subject)",
                        url=f"https://mail.google.com/mail/u/0/#all/{m['id']}",
                    )
                    for m in msgs
                ],
            }

        async def read_mail(ctx: ProviderContext, a: ReadMailArgs) -> dict[str, Any]:
            async with self.http(ctx) as http:
                m = (await http.get(f"/messages/{a.message_id}", params={"format": "full"})).json()
            text = _text_body(m.get("payload") or {})[:MAX_BODY]
            subject = _header(m, "Subject")
            return {
                "message_id": m["id"],
                "subject": self.wrap(subject, ref=m["id"]),
                "from": self.wrap(_header(m, "From"), ref=m["id"]),
                "date": _header(m, "Date"),
                "body": self.wrap(text, ref=m["id"]),
                "sources": [
                    self.source(
                        object_id=m["id"],
                        title=subject or "(no subject)",
                        url=f"https://mail.google.com/mail/u/0/#all/{m['id']}",
                    )
                ],
            }

        async def draft_mail(ctx: ProviderContext, a: DraftMailArgs) -> dict[str, Any]:
            async with self.http(ctx) as http:
                draft = (
                    await http.post(
                        "/drafts", json={"message": {"raw": _raw(list(a.to), a.subject, a.body)}}
                    )
                ).json()
            return {"draft_id": draft.get("id"), "subject": a.subject, "to": list(a.to)}

        async def verify_draft(
            ctx: ProviderContext, a: DraftMailArgs, result: dict[str, Any]
        ) -> Verification:
            async with self.http(ctx) as http:
                draft = (await http.get(f"/drafts/{result['draft_id']}")).json()
            if str(draft.get("id")) != str(result["draft_id"]):
                return Verification.failed("The draft was not found in Gmail")
            return Verification.verified("Draft is in your Gmail drafts")

        async def send_mail(ctx: ProviderContext, a: SendMailArgs) -> dict[str, Any]:
            async with self.http(ctx) as http:
                sent = (
                    await http.post(
                        "/messages/send", json={"raw": _raw(list(a.to), a.subject, a.body)}
                    )
                ).json()
            return {"message_id": sent.get("id"), "subject": a.subject, "to": list(a.to)}

        async def verify_send(
            ctx: ProviderContext, a: SendMailArgs, result: dict[str, Any]
        ) -> Verification:
            async with self.http(ctx) as http:
                m = (
                    await http.get(
                        f"/messages/{result['message_id']}", params={"format": "minimal"}
                    )
                ).json()
            if "SENT" in (m.get("labelIds") or []):
                return Verification.verified("Message is in Sent")
            return Verification.unverified("Message exists but is not labelled Sent yet")

        return [
            ProviderTool(
                "search_mail",
                "Search your Gmail with Gmail query syntax.",
                SearchMailArgs,
                Capability.search,
                search_mail,
                lambda a: f"Search Gmail for “{a.query}”",
                outputs=(
                    listing(
                        "results",
                        "Emails",
                        F("subject", "Subject"),
                        F("from", "From"),
                        F("date", "Date", "date"),
                        F("snippet", "Preview"),
                    ),
                ),
            ),
            ProviderTool(
                "read_mail",
                "Read one email by id.",
                ReadMailArgs,
                Capability.read,
                read_mail,
                lambda a: "Read an email",
                outputs=(
                    F("subject", "Subject"),
                    F("from", "From"),
                    F("date", "Date", "date"),
                    F("body", "Email text", "long_text"),
                ),
            ),
            ProviderTool(
                "draft_mail",
                "Create a Gmail draft (not sent).",
                DraftMailArgs,
                Capability.draft,
                draft_mail,
                lambda a: f"Draft email “{a.subject}” to {', '.join(a.to)}",
                verify=verify_draft,
            ),
            ProviderTool(
                "send_mail",
                "Send an email from your Gmail account.",
                SendMailArgs,
                Capability.send,
                send_mail,
                lambda a: f"Send email “{a.subject}” to {', '.join(a.to)}",
                verify=verify_send,
            ),
        ]
