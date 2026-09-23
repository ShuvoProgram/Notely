"""Google Docs: find documents, read their text, and — with the optional write permission —
create documents and append to them.

Scopes (Docs API v1 + Drive API v3 for discovery):
- drive.metadata.readonly: list/search documents by name.
- documents.readonly: read document content.
- documents (optional): create and append. Declined → those tools are not offered.
"""

from __future__ import annotations

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
from app.integrations.google.base import GoogleProvider

API = "https://docs.googleapis.com/v1"
DRIVE = "https://www.googleapis.com/drive/v3"
DOC_MIME = "application/vnd.google-apps.document"
SCOPE_DISCOVER = "https://www.googleapis.com/auth/drive.metadata.readonly"
SCOPE_READ = "https://www.googleapis.com/auth/documents.readonly"
SCOPE_WRITE = "https://www.googleapis.com/auth/documents"
MAX_TEXT = 12_000


class SearchDocumentsArgs(BaseModel):
    """Find documents by name."""

    query: str = Field(min_length=1, max_length=200)
    limit: int = Field(default=10, ge=1, le=25)


class ReadDocumentArgs(BaseModel):
    """Read a document's text."""

    document_id: str = Field(min_length=1, max_length=120)


class CreateDocumentArgs(BaseModel):
    """Create a document with an optional initial body (plain text)."""

    title: str = Field(min_length=1, max_length=200)
    content: str | None = Field(default=None, max_length=100_000)


class AppendToDocumentArgs(BaseModel):
    """Append plain text at the end of a document."""

    document_id: str = Field(min_length=1, max_length=120)
    content: str = Field(min_length=1, max_length=100_000)


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _url(document_id: str) -> str:
    return f"https://docs.google.com/document/d/{document_id}"


def document_text(doc: dict[str, Any]) -> str:
    """Flatten the Docs body (paragraphs, tables, lists) into plain text."""
    out: list[str] = []

    def walk(elements: list[dict[str, Any]]) -> None:
        for el in elements:
            if "paragraph" in el:
                for pe in el["paragraph"].get("elements", []):
                    run = pe.get("textRun")
                    if run and run.get("content"):
                        out.append(str(run["content"]))
            elif "table" in el:
                for row in el["table"].get("tableRows", []):
                    cells: list[str] = []
                    for cell in row.get("tableCells", []):
                        before = len(out)
                        walk(cell.get("content", []))
                        cells.append("".join(out[before:]).strip())
                        del out[before:]
                    out.append(" | ".join(cells) + "\n")
            elif "tableOfContents" in el:
                walk(el["tableOfContents"].get("content", []))

    walk(((doc.get("body") or {}).get("content")) or [])
    return "".join(out)


class GoogleDocsProvider(GoogleProvider):
    api_base = API
    manifest = ProviderManifest(
        id="google_docs",
        name="Google Docs",
        category="documents",
        description="Find and read your documents; create docs and append to them with approval.",
        logo_url="https://cdn.simpleicons.org/googledocs",
        docs_url="https://developers.google.com/docs/api/how-tos/overview",
        auth=AuthType.oauth2,
        capabilities=[Capability.search, Capability.read, Capability.create, Capability.update],
        permissions=[
            PermissionSpec(
                scope=SCOPE_DISCOVER,
                label="See the names of your documents",
                description="Only file names and dates — never contents of other files.",
                capability=Capability.search,
            ),
            PermissionSpec(
                scope=SCOPE_READ, label="Read document text", capability=Capability.read
            ),
            PermissionSpec(
                scope=SCOPE_WRITE,
                label="Create documents and append to them",
                description="Only when you approve an action.",
                required=False,
                capability=Capability.update,
            ),
        ],
    )

    async def account_email(self, ctx: ProviderContext) -> str:
        async with self.http(ctx, DRIVE) as http:
            about = (await http.get("/about", params={"fields": "user"})).json()
        return str((about.get("user") or {}).get("emailAddress") or "Google Docs")

    async def probe(self, ctx: ProviderContext) -> str:
        files = await self._find(ctx, None, 1)
        return f"{len(files)} document(s) visible"

    async def _find(
        self, ctx: ProviderContext, query: str | None, limit: int
    ) -> list[dict[str, Any]]:
        q = f"mimeType = '{DOC_MIME}' and trashed = false"
        if query:
            q += f" and name contains '{_escape(query)}'"
        async with self.http(ctx, DRIVE) as http:
            body = (
                await http.get(
                    "/files",
                    params={
                        "q": q,
                        "pageSize": limit,
                        "fields": "files(id,name,modifiedTime,webViewLink)",
                        "orderBy": "modifiedTime desc",
                    },
                )
            ).json()
        return self.items(body, "files")

    async def search(self, ctx: ProviderContext, query: str, limit: int) -> list[dict[str, Any]]:
        return [
            {
                "id": f["id"],
                "kind": "document",
                "title": f.get("name", ""),
                "snippet": "Google Docs",
                "url": f.get("webViewLink") or _url(f["id"]),
                "updated_at": f.get("modifiedTime"),
            }
            for f in await self._find(ctx, query, limit)
        ]

    async def _read(self, ctx: ProviderContext, document_id: str) -> tuple[str, str]:
        async with self.http(ctx) as http:
            doc = (await http.get(f"/documents/{document_id}")).json()
        return str(doc.get("title", "")), document_text(doc)

    def build_tools(self) -> list[ProviderTool]:
        async def search_documents(ctx: ProviderContext, a: SearchDocumentsArgs) -> dict[str, Any]:
            files = await self._find(ctx, a.query, a.limit)
            return {
                "results": [
                    {
                        "document_id": f["id"],
                        "name": self.wrap(str(f.get("name", "")), ref=f["id"]),
                        "modified_at": f.get("modifiedTime"),
                        "url": f.get("webViewLink") or _url(f["id"]),
                    }
                    for f in files
                ],
                "sources": [
                    self.source(object_id=f["id"], title=str(f.get("name", "")), url=_url(f["id"]))
                    for f in files
                ],
            }

        async def read_document(ctx: ProviderContext, a: ReadDocumentArgs) -> dict[str, Any]:
            title, text = await self._read(ctx, a.document_id)
            return {
                "document_id": a.document_id,
                "title": self.wrap(title, ref=a.document_id),
                "content": self.wrap(text[:MAX_TEXT], ref=a.document_id),
                "truncated": len(text) > MAX_TEXT,
                "sources": [
                    self.source(object_id=a.document_id, title=title, url=_url(a.document_id))
                ],
            }

        async def create_document(ctx: ProviderContext, a: CreateDocumentArgs) -> dict[str, Any]:
            async with self.http(ctx) as http:
                created = (await http.post("/documents", json={"title": a.title})).json()
                doc_id = str(created.get("documentId", ""))
                if a.content:
                    await http.post(
                        f"/documents/{doc_id}:batchUpdate",
                        json={
                            "requests": [
                                {"insertText": {"location": {"index": 1}, "text": a.content}}
                            ]
                        },
                    )
            return {"document_id": doc_id, "title": a.title, "url": _url(doc_id)}

        async def verify_create(
            ctx: ProviderContext, a: CreateDocumentArgs, result: dict[str, Any]
        ) -> Verification:
            title, text = await self._read(ctx, result["document_id"])
            if title != a.title:
                return Verification.failed("Document exists but its title differs")
            if a.content and a.content.strip()[:40] not in text:
                return Verification.failed("Document exists but the text was not found in it")
            return Verification.verified("Document is in your Drive")

        async def append_to_document(
            ctx: ProviderContext, a: AppendToDocumentArgs
        ) -> dict[str, Any]:
            text = a.content if a.content.startswith("\n") else "\n" + a.content
            async with self.http(ctx) as http:
                await http.post(
                    f"/documents/{a.document_id}:batchUpdate",
                    json={"requests": [{"insertText": {"endOfSegmentLocation": {}, "text": text}}]},
                )
            return {
                "document_id": a.document_id,
                "appended_characters": len(a.content),
                "url": _url(a.document_id),
            }

        async def verify_append(
            ctx: ProviderContext, a: AppendToDocumentArgs, result: dict[str, Any]
        ) -> Verification:
            _, text = await self._read(ctx, a.document_id)
            if a.content.strip()[:40] not in text:
                return Verification.failed("The appended text was not found in the document")
            return Verification.verified("Text is at the end of the document")

        return [
            ProviderTool(
                "search_documents",
                "Find documents by name.",
                SearchDocumentsArgs,
                Capability.search,
                search_documents,
                lambda a: f"Search Google Docs for “{a.query}”",
                scope=SCOPE_DISCOVER,
                outputs=(
                    listing(
                        "results",
                        "Documents",
                        F("name", "Name"),
                        F("modified_at", "Last edited", "date"),
                        F("url", "Link", "url"),
                    ),
                ),
            ),
            ProviderTool(
                "read_document",
                "Read a document's text.",
                ReadDocumentArgs,
                Capability.read,
                read_document,
                lambda a: "Read a Google Doc",
                scope=SCOPE_READ,
                outputs=(F("title", "Title"), F("content", "Document text", "long_text")),
            ),
            ProviderTool(
                "create_document",
                "Create a new document, optionally with initial text.",
                CreateDocumentArgs,
                Capability.create,
                create_document,
                lambda a: f"Create document “{a.title}”",
                verify=verify_create,
                scope=SCOPE_WRITE,
            ),
            ProviderTool(
                "append_to_document",
                "Append text to the end of a document.",
                AppendToDocumentArgs,
                Capability.update,
                append_to_document,
                lambda a: f"Append {len(a.content)} characters to a document",
                verify=verify_append,
                scope=SCOPE_WRITE,
            ),
        ]
