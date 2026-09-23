"""OneDrive via Graph: search, browse and read files; upload text files with approval."""

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
from app.integrations.microsoft.base import MicrosoftGraphProvider

MAX_TEXT = 12_000


class SearchFilesArgs(BaseModel):
    """Search your OneDrive by file name or content."""

    query: str = Field(min_length=1, max_length=200)
    limit: int = Field(default=10, ge=1, le=25)


class ListFolderArgs(BaseModel):
    """List a folder (root when no item id is given)."""

    item_id: str | None = Field(default=None, max_length=120)


class ReadTextFileArgs(BaseModel):
    """Read a text-like file (txt, md, csv, json) by item id."""

    item_id: str = Field(min_length=1, max_length=120)


class UploadTextFileArgs(BaseModel):
    """Create or overwrite a small text file at a path under the OneDrive root."""

    path: str = Field(min_length=1, max_length=400, description="e.g. Notes/summary.md")
    content: str = Field(min_length=1, max_length=100_000)


def _item(i: dict[str, Any]) -> dict[str, Any]:
    return {
        "item_id": i.get("id"),
        "name": i.get("name"),
        "kind": "folder" if "folder" in i else "file",
        "size": i.get("size"),
        "modified_at": i.get("lastModifiedDateTime"),
        "url": i.get("webUrl"),
    }


class OneDriveProvider(MicrosoftGraphProvider):
    manifest = ProviderManifest(
        id="onedrive",
        name="OneDrive",
        category="storage",
        description="Search, browse and read your OneDrive files; create files with approval.",
        logo_url="https://cdn.simpleicons.org/microsoftonedrive",
        docs_url="https://learn.microsoft.com/graph/api/resources/onedrive",
        auth=AuthType.oauth2,
        capabilities=[Capability.search, Capability.read, Capability.create],
        permissions=[
            PermissionSpec(
                scope="User.Read", label="Read your profile", capability=Capability.read
            ),
            PermissionSpec(scope="Files.Read", label="Read your files", capability=Capability.read),
            PermissionSpec(scope="offline_access", label="Stay connected (refresh tokens)"),
            PermissionSpec(
                scope="Files.ReadWrite",
                label="Create and update files",
                required=False,
                capability=Capability.create,
            ),
        ],
    )

    async def probe(self, ctx: ProviderContext) -> str:
        async with self.http(ctx) as http:
            drive = (await http.get("/me/drive", params={"$select": "id,driveType"})).json()
        return f"{drive.get('driveType', 'drive')} reachable"

    async def _search(self, ctx: ProviderContext, query: str, limit: int) -> list[dict[str, Any]]:
        safe = query.replace("'", "''")
        async with self.http(ctx) as http:
            body = (
                await http.get(f"/me/drive/root/search(q='{safe}')", params={"$top": limit})
            ).json()
        return self.graph_page(body)[:limit]

    async def search(self, ctx: ProviderContext, query: str, limit: int) -> list[dict[str, Any]]:
        return [
            {
                "id": i["id"],
                "kind": "folder" if "folder" in i else "file",
                "title": str(i.get("name", "")),
                "snippet": str((i.get("parentReference") or {}).get("path", "")),
                "url": i.get("webUrl"),
                "updated_at": i.get("lastModifiedDateTime"),
            }
            for i in await self._search(ctx, query, limit)
        ]

    def build_tools(self) -> list[ProviderTool]:
        def wrap_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
            return [
                {**_item(i), "name": self.wrap(str(i.get("name", "")), ref=str(i.get("id")))}
                for i in items
            ]

        async def search_files(ctx: ProviderContext, a: SearchFilesArgs) -> dict[str, Any]:
            items = await self._search(ctx, a.query, a.limit)
            return {
                "results": wrap_items(items),
                "sources": [
                    self.source(object_id=i["id"], title=str(i.get("name")), url=i.get("webUrl"))
                    for i in items
                ],
            }

        async def list_folder(ctx: ProviderContext, a: ListFolderArgs) -> dict[str, Any]:
            path = (
                f"/me/drive/items/{a.item_id}/children" if a.item_id else "/me/drive/root/children"
            )
            async with self.http(ctx) as http:
                items = self.graph_page((await http.get(path, params={"$top": 50})).json())
            return {"items": wrap_items(items)}

        async def read_text_file(ctx: ProviderContext, a: ReadTextFileArgs) -> dict[str, Any]:
            async with self.http(ctx) as http:
                meta = (
                    await http.get(
                        f"/me/drive/items/{a.item_id}", params={"$select": "id,name,webUrl,file"}
                    )
                ).json()
                resp = await http.get(
                    f"/me/drive/items/{a.item_id}/content", headers={"Accept": "*/*"}
                )
            text = resp.text[:MAX_TEXT]
            return {
                "item_id": meta.get("id"),
                "name": self.wrap(str(meta.get("name", "")), ref=a.item_id),
                "content": self.wrap(text, ref=a.item_id),
                "truncated": len(resp.text) > MAX_TEXT,
                "sources": [
                    self.source(
                        object_id=a.item_id, title=str(meta.get("name")), url=meta.get("webUrl")
                    )
                ],
            }

        async def upload_text_file(ctx: ProviderContext, a: UploadTextFileArgs) -> dict[str, Any]:
            path = a.path.strip("/")
            async with self.http(ctx) as http:
                item = (
                    await http.request(
                        "PUT",
                        f"/me/drive/root:/{path}:/content",
                        content=a.content.encode("utf-8"),
                        headers={"Content-Type": "text/plain"},
                    )
                ).json()
            return {
                "item_id": item.get("id"),
                "path": path,
                "url": item.get("webUrl"),
                "size": item.get("size"),
            }

        async def verify_upload(
            ctx: ProviderContext, a: UploadTextFileArgs, result: dict[str, Any]
        ) -> Verification:
            async with self.http(ctx) as http:
                item = (
                    await http.get(
                        f"/me/drive/items/{result['item_id']}",
                        params={"$select": "id,size,deleted"},
                    )
                ).json()
            if item.get("deleted"):
                return Verification.failed("The file was deleted")
            if item.get("size") not in (None, len(a.content.encode("utf-8"))):
                return Verification.failed("File exists but its size differs")
            return Verification.verified("File is in your OneDrive")

        return [
            ProviderTool(
                "search_files",
                "Search OneDrive by name or content.",
                SearchFilesArgs,
                Capability.search,
                search_files,
                lambda a: f"Search OneDrive for “{a.query}”",
                outputs=(listing("results", "Files", F("name", "Name"), F("url", "Link", "url")),),
            ),
            ProviderTool(
                "list_folder",
                "List a OneDrive folder.",
                ListFolderArgs,
                Capability.read,
                list_folder,
                lambda a: "List a OneDrive folder",
            ),
            ProviderTool(
                "read_text_file",
                "Read a text-like file.",
                ReadTextFileArgs,
                Capability.read,
                read_text_file,
                lambda a: "Read a OneDrive file",
                outputs=(F("name", "File name"), F("content", "File text", "long_text")),
            ),
            ProviderTool(
                "upload_text_file",
                "Create or overwrite a text file.",
                UploadTextFileArgs,
                Capability.create,
                upload_text_file,
                lambda a: f"Save “{a.path}” to OneDrive",
                verify=verify_upload,
            ),
        ]
