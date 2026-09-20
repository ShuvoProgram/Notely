"""Google Drive: search and read files (Docs are exported as text); upload text with approval."""

from __future__ import annotations

import json
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

API = "https://www.googleapis.com/drive/v3"
UPLOAD = "https://www.googleapis.com/upload/drive/v3"
FIELDS = "files(id,name,mimeType,modifiedTime,webViewLink,size)"
MAX_TEXT = 12_000
GOOGLE_DOC = "application/vnd.google-apps.document"
GOOGLE_SHEET = "application/vnd.google-apps.spreadsheet"


class SearchFilesArgs(BaseModel):
    """Search files by name or content."""

    query: str = Field(min_length=1, max_length=200)
    limit: int = Field(default=10, ge=1, le=25)


class ReadTextFileArgs(BaseModel):
    """Read a text file or Google Doc/Sheet (exported as plain text / CSV)."""

    file_id: str = Field(min_length=1, max_length=120)


class UploadTextFileArgs(BaseModel):
    """Create a text file in Drive (in My Drive root unless a folder id is given)."""

    name: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=100_000)
    folder_id: str | None = Field(default=None, max_length=120)


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


class GoogleDriveProvider(GoogleProvider):
    api_base = API
    manifest = ProviderManifest(
        id="google_drive",
        name="Google Drive",
        category="storage",
        description="Search and read your Drive files and Docs; create files with approval.",
        logo_url="https://cdn.simpleicons.org/googledrive",
        docs_url="https://developers.google.com/drive/api/guides/about-sdk",
        auth=AuthType.oauth2,
        capabilities=[Capability.search, Capability.read, Capability.create],
        permissions=[
            PermissionSpec(
                scope="https://www.googleapis.com/auth/drive.readonly",
                label="Read and search your files",
                capability=Capability.read,
            ),
            PermissionSpec(
                scope="https://www.googleapis.com/auth/drive.file",
                label="Create files Notely makes for you",
                required=False,
                capability=Capability.create,
            ),
        ],
    )

    async def probe(self, ctx: ProviderContext) -> str:
        async with self.http(ctx) as http:
            about = (await http.get("/about", params={"fields": "user,storageQuota"})).json()
        return f"Drive of {(about.get('user') or {}).get('emailAddress', 'ok')}"

    async def _search(self, ctx: ProviderContext, query: str, limit: int) -> list[dict[str, Any]]:
        term = _escape(query)
        q = f"(name contains '{term}' or fullText contains '{term}') and trashed = false"
        async with self.http(ctx) as http:
            body = (
                await http.get(
                    "/files",
                    params={
                        "q": q,
                        "pageSize": limit,
                        "fields": FIELDS,
                        "orderBy": "modifiedTime desc",
                    },
                )
            ).json()
        return self.items(body, "files")

    async def search(self, ctx: ProviderContext, query: str, limit: int) -> list[dict[str, Any]]:
        return [
            {
                "id": f["id"],
                "kind": "file",
                "title": f.get("name", ""),
                "snippet": f.get("mimeType", ""),
                "url": f.get("webViewLink"),
                "updated_at": f.get("modifiedTime"),
            }
            for f in await self._search(ctx, query, limit)
        ]

    def build_tools(self) -> list[ProviderTool]:
        async def search_files(ctx: ProviderContext, a: SearchFilesArgs) -> dict[str, Any]:
            files = await self._search(ctx, a.query, a.limit)
            return {
                "results": [
                    {
                        "file_id": f["id"],
                        "name": self.wrap(str(f.get("name", "")), ref=f["id"]),
                        "mime_type": f.get("mimeType"),
                        "modified_at": f.get("modifiedTime"),
                        "url": f.get("webViewLink"),
                    }
                    for f in files
                ],
                "sources": [
                    self.source(
                        object_id=f["id"], title=str(f.get("name", "")), url=f.get("webViewLink")
                    )
                    for f in files
                ],
            }

        async def read_text_file(ctx: ProviderContext, a: ReadTextFileArgs) -> dict[str, Any]:
            async with self.http(ctx) as http:
                meta = (
                    await http.get(
                        f"/files/{a.file_id}", params={"fields": "id,name,mimeType,webViewLink"}
                    )
                ).json()
                mime = str(meta.get("mimeType", ""))
                if mime == GOOGLE_DOC:
                    resp = await http.get(
                        f"/files/{a.file_id}/export", params={"mimeType": "text/plain"}
                    )
                elif mime == GOOGLE_SHEET:
                    resp = await http.get(
                        f"/files/{a.file_id}/export", params={"mimeType": "text/csv"}
                    )
                else:
                    resp = await http.get(f"/files/{a.file_id}", params={"alt": "media"})
            text = resp.text[:MAX_TEXT]
            return {
                "file_id": meta["id"],
                "name": self.wrap(str(meta.get("name", "")), ref=meta["id"]),
                "content": self.wrap(text, ref=meta["id"]),
                "truncated": len(resp.text) > MAX_TEXT,
                "sources": [
                    self.source(
                        object_id=meta["id"],
                        title=str(meta.get("name", "")),
                        url=meta.get("webViewLink"),
                    )
                ],
            }

        async def upload_text_file(ctx: ProviderContext, a: UploadTextFileArgs) -> dict[str, Any]:
            meta: dict[str, Any] = {"name": a.name, "mimeType": "text/plain"}
            if a.folder_id:
                meta["parents"] = [a.folder_id]
            boundary = "notely-upload"
            body = (
                f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n"
                f"{json.dumps(meta)}\r\n--{boundary}\r\nContent-Type: text/plain\r\n\r\n"
                f"{a.content}\r\n--{boundary}--"
            ).encode()
            async with self.http(ctx, UPLOAD) as http:
                created = (
                    await http.post(
                        "/files",
                        params={"uploadType": "multipart", "fields": "id,name,webViewLink"},
                        content=body,
                        headers={"Content-Type": f"multipart/related; boundary={boundary}"},
                    )
                ).json()
            return {"file_id": created.get("id"), "name": a.name, "url": created.get("webViewLink")}

        async def verify_upload(
            ctx: ProviderContext, a: UploadTextFileArgs, result: dict[str, Any]
        ) -> Verification:
            async with self.http(ctx) as http:
                meta = (
                    await http.get(
                        f"/files/{result['file_id']}", params={"fields": "id,name,trashed"}
                    )
                ).json()
            if meta.get("trashed"):
                return Verification.failed("The file is in the trash")
            if meta.get("name") not in (None, a.name):
                return Verification.failed("File exists but its name differs")
            return Verification.verified("File is in your Drive")

        return [
            ProviderTool(
                "search_files",
                "Search Drive files by name or content.",
                SearchFilesArgs,
                Capability.search,
                search_files,
                lambda a: f"Search Drive for “{a.query}”",
            ),
            ProviderTool(
                "read_text_file",
                "Read a text file, Google Doc or Sheet as text.",
                ReadTextFileArgs,
                Capability.read,
                read_text_file,
                lambda a: "Read a Drive file",
            ),
            ProviderTool(
                "upload_text_file",
                "Create a text file in Drive.",
                UploadTextFileArgs,
                Capability.create,
                upload_text_file,
                lambda a: f"Create Drive file “{a.name}”",
                verify=verify_upload,
            ),
        ]
