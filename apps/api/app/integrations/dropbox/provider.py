"""Dropbox: OAuth2 with PKCE + offline refresh tokens; RPC-style JSON API v2."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.ai.tools.base import OutputField as F
from app.ai.tools.base import Verification
from app.core.oauth import OAuthEndpoints
from app.integrations.base.capabilities import Capability
from app.integrations.base.outputs import SEARCH_RESULTS, listing
from app.integrations.base.provider import (
    AuthType,
    ConnectionIdentity,
    PermissionSpec,
    ProviderContext,
    ProviderManifest,
)
from app.integrations.base.rest import ProviderTool, RestOAuthProvider
from app.integrations.base.triggers import ProviderTrigger, TriggerEvent, parse_time

CONTENT = "https://content.dropboxapi.com/2"
BLOCK = 4 * 1024 * 1024


def dropbox_content_hash(data: bytes) -> str:
    """Dropbox's content_hash: sha256 of the concatenated sha256s of 4 MiB blocks."""
    import hashlib

    blocks = [data[i : i + BLOCK] for i in range(0, len(data), BLOCK)] or [b""]
    return hashlib.sha256(b"".join(hashlib.sha256(b).digest() for b in blocks)).hexdigest()


WRITE_SCOPE = "files.content.write"
TEXT_EXTENSIONS = (".txt", ".md", ".markdown", ".csv", ".json", ".paper")
MAX_TEXT_BYTES = 200_000


class SearchFilesArgs(BaseModel):
    """Search files and folders by name/content."""

    query: str = Field(min_length=1, max_length=200)
    limit: int = Field(default=10, ge=1, le=25)


class ListFolderArgs(BaseModel):
    """List a folder ('' for the root)."""

    path: str = Field(default="", max_length=1000)
    limit: int = Field(default=50, ge=1, le=200)


class ReadTextFileArgs(BaseModel):
    """Read a small text file (txt, md, csv, json)."""

    path: str = Field(min_length=1, max_length=1000)


class FileInfoArgs(BaseModel):
    """Details of one file or folder: size, modified time, full path."""

    path: str = Field(min_length=1, max_length=1000)


class CreateFolderArgs(BaseModel):
    """Create a folder."""

    path: str = Field(min_length=2, max_length=1000, description="e.g. /Projects/Alpha")


class MoveArgs(BaseModel):
    """Move or rename a file or folder (renaming = moving within the same folder)."""

    from_path: str = Field(min_length=2, max_length=1000)
    to_path: str = Field(min_length=2, max_length=1000)


class FileChangedParams(BaseModel):
    """Which folder to watch."""

    path: str = Field(default="", max_length=1000, description="e.g. /Projects; empty = top level")


class UploadTextFileArgs(BaseModel):
    """Create or overwrite a text file."""

    path: str = Field(min_length=1, max_length=1000, description="e.g. /Notes/summary.md")
    content: str = Field(max_length=200_000)
    overwrite: bool = False


class DropboxProvider(RestOAuthProvider):
    settings_prefix = "dropbox"
    api_base = "https://api.dropboxapi.com/2"
    endpoints = OAuthEndpoints(
        authorize_url="https://www.dropbox.com/oauth2/authorize",
        token_url="https://api.dropboxapi.com/oauth2/token",
        extra_authorize_params={"token_access_type": "offline"},
    )
    manifest = ProviderManifest(
        id="dropbox",
        name="Dropbox",
        category="storage",
        description=(
            "Search, browse and read your files; save text files, create folders and move or "
            "rename items with approval."
        ),
        logo_url="https://cdn.simpleicons.org/dropbox",
        docs_url="https://www.dropbox.com/developers/documentation/http/documentation",
        auth=AuthType.oauth2,
        capabilities=[Capability.search, Capability.read, Capability.create, Capability.update],
        permissions=[
            PermissionSpec(
                scope="account_info.read",
                label="Read your account name",
                capability=Capability.read,
            ),
            PermissionSpec(
                scope="files.metadata.read",
                label="Search and list files",
                capability=Capability.search,
            ),
            PermissionSpec(
                scope="files.content.read", label="Read file contents", capability=Capability.read
            ),
            PermissionSpec(
                scope=WRITE_SCOPE,
                label="Save files, create folders, move and rename",
                required=False,
                capability=Capability.create,
            ),
        ],
    )

    async def identity(self, ctx: ProviderContext) -> ConnectionIdentity:
        async with self.http(ctx) as http:
            me = (await http.post("/users/get_current_account", json=None)).json()
        return ConnectionIdentity(
            external_account_id=str(me.get("account_id")),
            external_account_name=(
                f"{(me.get('name') or {}).get('display_name')} ({me.get('email')})"
            ),
        )

    async def probe(self, ctx: ProviderContext) -> str:
        async with self.http(ctx) as http:
            body = (await http.post("/files/list_folder", json={"path": "", "limit": 1})).json()
        return f"{len(body.get('entries', []))}+ item(s) in root"

    async def search(self, ctx: ProviderContext, query: str, limit: int) -> list[dict[str, Any]]:
        async with self.http(ctx) as http:
            body = (
                await http.post(
                    "/files/search_v2", json={"query": query, "options": {"max_results": limit}}
                )
            ).json()
        hits = []
        for match in body.get("matches", []):
            meta = (match.get("metadata") or {}).get("metadata") or {}
            hits.append(
                {
                    "id": meta.get("id") or meta.get("path_lower"),
                    "kind": meta.get(".tag", "file"),
                    "title": meta.get("name", ""),
                    "snippet": meta.get("path_display", ""),
                    "url": None,
                    "updated_at": meta.get("server_modified"),
                }
            )
        return hits

    def build_triggers(self) -> list[ProviderTrigger]:
        async def file_changed(
            ctx: ProviderContext, p: FileChangedParams, since: datetime
        ) -> list[TriggerEvent]:
            async with self.http(ctx) as http:
                body = (
                    await http.post("/files/list_folder", json={"path": p.path, "limit": 500})
                ).json()
            events = []
            for e in body.get("entries", []):
                modified = parse_time(e.get("server_modified"))
                if e.get(".tag") != "file" or modified is None or modified <= since:
                    continue
                events.append(
                    TriggerEvent(
                        # `rev` changes with every upload, so each new version fires once.
                        id=f"{e.get('id')}:{e.get('rev')}",
                        occurred_at=modified,
                        data={
                            "name": e.get("name"),
                            "path": e.get("path_display"),
                            "size": e.get("size"),
                            "modified_at": e.get("server_modified"),
                            "file_id": e.get("id"),
                        },
                    )
                )
            return events

        return [
            ProviderTrigger(
                "file_changed",
                "File added or updated in a folder",
                "Starts when a file in a Dropbox folder is added or changed.",
                file_changed,
                FileChangedParams,
                outputs=(
                    F("name", "File name"),
                    F("path", "File path"),
                    F("size", "Size", "number"),
                    F("modified_at", "Modified", "date"),
                ),
                scope="files.metadata.read",
            )
        ]

    def build_tools(self):  # type: ignore[no-untyped-def]
        async def search_files(ctx: ProviderContext, a: SearchFilesArgs) -> dict[str, Any]:
            hits = await self.search(ctx, a.query, a.limit)
            return {
                "results": hits,
                "sources": [
                    self.source(object_id=str(h["id"]), title=h["title"], url=None) for h in hits
                ],
            }

        async def list_folder(ctx: ProviderContext, a: ListFolderArgs) -> dict[str, Any]:
            async with self.http(ctx) as http:
                body = (
                    await http.post("/files/list_folder", json={"path": a.path, "limit": a.limit})
                ).json()
            return {
                "entries": [
                    {
                        "kind": e.get(".tag"),
                        "name": self.wrap(str(e.get("name", "")), ref=str(e.get("path_lower"))),
                        "path": e.get("path_display"),
                        "size": e.get("size"),
                        "modified": e.get("server_modified"),
                    }
                    for e in body.get("entries", [])
                ]
            }

        async def read_text_file(ctx: ProviderContext, a: ReadTextFileArgs) -> dict[str, Any]:
            from app.integrations.base.errors import ProviderError, ProviderErrorKind

            if not a.path.lower().endswith(TEXT_EXTENSIONS):
                raise ProviderError(
                    ProviderErrorKind.invalid_request,
                    "only text files can be read",
                    provider="dropbox",
                )
            async with self.http(ctx, CONTENT) as http:
                resp = await http.post(
                    "/files/download",
                    headers={
                        "Dropbox-API-Arg": json.dumps({"path": a.path}),
                        "Content-Type": "text/plain",
                    },
                )
            text = resp.content[:MAX_TEXT_BYTES].decode("utf-8", errors="replace")
            return {
                "path": a.path,
                "content": self.wrap(text, ref=a.path),
                "sources": [
                    self.source(object_id=a.path, title=a.path.rsplit("/", 1)[-1], url=None)
                ],
            }

        async def file_info(ctx: ProviderContext, a: FileInfoArgs) -> dict[str, Any]:
            async with self.http(ctx) as http:
                meta = (await http.post("/files/get_metadata", json={"path": a.path})).json()
            return {
                "kind": meta.get(".tag"),
                "name": self.wrap(str(meta.get("name", "")), ref=a.path),
                "path": meta.get("path_display"),
                "size": meta.get("size"),
                "modified": meta.get("server_modified"),
                "id": meta.get("id"),
            }

        async def create_folder(ctx: ProviderContext, a: CreateFolderArgs) -> dict[str, Any]:
            async with self.http(ctx) as http:
                body = (
                    await http.post(
                        "/files/create_folder_v2", json={"path": a.path, "autorename": False}
                    )
                ).json()
            meta = body.get("metadata") or {}
            return {"path": meta.get("path_display", a.path), "id": meta.get("id")}

        async def move(ctx: ProviderContext, a: MoveArgs) -> dict[str, Any]:
            async with self.http(ctx) as http:
                body = (
                    await http.post(
                        "/files/move_v2",
                        json={"from_path": a.from_path, "to_path": a.to_path, "autorename": False},
                    )
                ).json()
            meta = body.get("metadata") or {}
            return {"path": meta.get("path_display", a.to_path), "id": meta.get("id")}

        async def verify_path(ctx: ProviderContext, path: str, what: str) -> Verification:
            async with self.http(ctx) as http:
                meta = (await http.post("/files/get_metadata", json={"path": path})).json()
            if (meta.get("path_display") or "").lower() != path.lower():
                return Verification.failed(f"The {what} is not where it should be")
            return Verification.verified(f"The {what} is at {meta.get('path_display')}")

        async def verify_create_folder(
            ctx: ProviderContext, a: CreateFolderArgs, result: dict[str, Any]
        ) -> Verification:
            return await verify_path(ctx, result["path"], "folder")

        async def verify_move(
            ctx: ProviderContext, a: MoveArgs, result: dict[str, Any]
        ) -> Verification:
            return await verify_path(ctx, result["path"], "item")

        async def upload_text_file(ctx: ProviderContext, a: UploadTextFileArgs) -> dict[str, Any]:
            arg = {
                "path": a.path,
                "mode": "overwrite" if a.overwrite else "add",
                "autorename": not a.overwrite,
                "mute": True,
            }
            async with self.http(ctx, CONTENT) as http:
                meta = (
                    await http.post(
                        "/files/upload",
                        headers={
                            "Dropbox-API-Arg": json.dumps(arg),
                            "Content-Type": "application/octet-stream",
                        },
                        content=a.content.encode(),
                    )
                ).json()
            return {
                "path": meta.get("path_display", a.path),
                "id": meta.get("id"),
                "size": meta.get("size"),
            }

        async def verify_upload_text_file(
            ctx: ProviderContext, a: UploadTextFileArgs, result: dict[str, Any]
        ) -> Verification:
            async with self.http(ctx) as http:
                meta = (
                    await http.post("/files/get_metadata", json={"path": result["path"]})
                ).json()
            expected = dropbox_content_hash(a.content.encode("utf-8"))
            if meta.get("content_hash") and meta["content_hash"] != expected:
                return Verification.failed("File exists but its content differs")
            return Verification.verified("File is in Dropbox with the expected content")

        return [
            ProviderTool(
                "search_files",
                "Search Dropbox files.",
                SearchFilesArgs,
                Capability.search,
                search_files,
                lambda a: f"Search Dropbox for “{a.query}”",
                outputs=SEARCH_RESULTS,
            ),
            ProviderTool(
                "list_folder",
                "List a Dropbox folder.",
                ListFolderArgs,
                Capability.read,
                list_folder,
                lambda a: f"List Dropbox folder {a.path or '/'}",
                outputs=(
                    listing(
                        "entries",
                        "Items",
                        F("name", "Name"),
                        F("path", "Path"),
                        F("kind", "Type"),
                        F("modified", "Modified", "date"),
                    ),
                ),
            ),
            ProviderTool(
                "file_info",
                "Get a Dropbox file's or folder's details (size, modified time, path).",
                FileInfoArgs,
                Capability.read,
                file_info,
                lambda a: f"Get details of Dropbox item {a.path}",
                outputs=(
                    F("path", "Path"),
                    F("size", "Size", "number"),
                    F("modified", "Modified", "date"),
                ),
            ),
            ProviderTool(
                "read_text_file",
                "Read a text file from Dropbox.",
                ReadTextFileArgs,
                Capability.read,
                read_text_file,
                lambda a: f"Read Dropbox file {a.path}",
                outputs=(F("path", "File path"), F("content", "File text", "long_text")),
            ),
            ProviderTool(
                "upload_text_file",
                "Save a text file to Dropbox.",
                UploadTextFileArgs,
                Capability.create,
                upload_text_file,
                lambda a: f"Save Dropbox file {a.path}",
                verify=verify_upload_text_file,
                scope=WRITE_SCOPE,
                outputs=(F("path", "File path"),),
            ),
            ProviderTool(
                "create_folder",
                "Create a Dropbox folder.",
                CreateFolderArgs,
                Capability.create,
                create_folder,
                lambda a: f"Create Dropbox folder {a.path}",
                verify=verify_create_folder,
                scope=WRITE_SCOPE,
                outputs=(F("path", "Folder path"),),
            ),
            ProviderTool(
                "move",
                "Move or rename a Dropbox file or folder.",
                MoveArgs,
                Capability.update,
                move,
                lambda a: f"Move Dropbox {a.from_path} to {a.to_path}",
                verify=verify_move,
                scope=WRITE_SCOPE,
                outputs=(F("path", "New path"),),
            ),
        ]
