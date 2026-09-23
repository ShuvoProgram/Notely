"""Google Sheets: find spreadsheets, read ranges, and — with the optional write permission —
create spreadsheets, write cells and append rows.

Scopes (Sheets API v4 + Drive API v3 for discovery):
- drive.metadata.readonly: list/search spreadsheets by name (no file contents).
- spreadsheets.readonly: read cell values.
- spreadsheets (optional): create, write and append. Declined → the write tools are not
  offered to the assistant at all.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.ai.tools.base import OutputField as F
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

API = "https://sheets.googleapis.com/v4"
DRIVE = "https://www.googleapis.com/drive/v3"
SHEET_MIME = "application/vnd.google-apps.spreadsheet"
SCOPE_DISCOVER = "https://www.googleapis.com/auth/drive.metadata.readonly"
SCOPE_READ = "https://www.googleapis.com/auth/spreadsheets.readonly"
SCOPE_WRITE = "https://www.googleapis.com/auth/spreadsheets"
MAX_CELLS = 2_000


class SearchSpreadsheetsArgs(BaseModel):
    """Find spreadsheets by name."""

    query: str = Field(min_length=1, max_length=200)
    limit: int = Field(default=10, ge=1, le=25)


class ReadRangeArgs(BaseModel):
    """Read cells from a spreadsheet. `range` is A1 notation (e.g. `Sheet1!A1:D20`); omit it for
    the first sheet."""

    spreadsheet_id: str = Field(min_length=1, max_length=120)
    range: str | None = Field(default=None, max_length=200)


class CreateSpreadsheetArgs(BaseModel):
    """Create a new spreadsheet, optionally with header row values."""

    title: str = Field(min_length=1, max_length=200)
    headers: list[str] | None = Field(default=None, max_length=50)


class WriteRangeArgs(BaseModel):
    """Overwrite cells in an A1 range with a 2-D array of values."""

    spreadsheet_id: str = Field(min_length=1, max_length=120)
    range: str = Field(min_length=1, max_length=200)
    values: list[list[str | float | int | bool | None]] = Field(min_length=1, max_length=500)


class AppendRowsArgs(BaseModel):
    """Append rows after the last row of a table (`range` names the sheet/table, e.g. `Sheet1`)."""

    spreadsheet_id: str = Field(min_length=1, max_length=120)
    range: str = Field(default="Sheet1", max_length=200)
    rows: list[list[str | float | int | bool | None]] = Field(min_length=1, max_length=500)


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _url(spreadsheet_id: str) -> str:
    return f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}"


class GoogleSheetsProvider(GoogleProvider):
    api_base = API
    manifest = ProviderManifest(
        id="google_sheets",
        name="Google Sheets",
        category="documents",
        description="Find and read your spreadsheets; create sheets and add rows with approval.",
        logo_url="https://cdn.simpleicons.org/googlesheets",
        docs_url="https://developers.google.com/sheets/api/guides/concepts",
        auth=AuthType.oauth2,
        capabilities=[Capability.search, Capability.read, Capability.create, Capability.update],
        permissions=[
            PermissionSpec(
                scope=SCOPE_DISCOVER,
                label="See the names of your spreadsheets",
                description="Only file names and dates — never contents of other files.",
                capability=Capability.search,
            ),
            PermissionSpec(
                scope=SCOPE_READ, label="Read spreadsheet data", capability=Capability.read
            ),
            PermissionSpec(
                scope=SCOPE_WRITE,
                label="Create spreadsheets and write cells",
                description="Only when you approve an action.",
                required=False,
                capability=Capability.update,
            ),
        ],
    )

    async def account_email(self, ctx: ProviderContext) -> str:
        async with self.http(ctx, DRIVE) as http:
            about = (await http.get("/about", params={"fields": "user"})).json()
        return str((about.get("user") or {}).get("emailAddress") or "Google Sheets")

    async def probe(self, ctx: ProviderContext) -> str:
        files = await self._find(ctx, None, 1)
        return f"{len(files)} spreadsheet(s) visible"

    async def _find(
        self, ctx: ProviderContext, query: str | None, limit: int
    ) -> list[dict[str, Any]]:
        q = f"mimeType = '{SHEET_MIME}' and trashed = false"
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
                "kind": "spreadsheet",
                "title": f.get("name", ""),
                "snippet": "Google Sheets",
                "url": f.get("webViewLink") or _url(f["id"]),
                "updated_at": f.get("modifiedTime"),
            }
            for f in await self._find(ctx, query, limit)
        ]

    def build_tools(self) -> list[ProviderTool]:
        async def search_spreadsheets(
            ctx: ProviderContext, a: SearchSpreadsheetsArgs
        ) -> dict[str, Any]:
            files = await self._find(ctx, a.query, a.limit)
            return {
                "results": [
                    {
                        "spreadsheet_id": f["id"],
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

        async def read_range(ctx: ProviderContext, a: ReadRangeArgs) -> dict[str, Any]:
            async with self.http(ctx) as http:
                meta = (
                    await http.get(
                        f"/spreadsheets/{a.spreadsheet_id}",
                        params={"fields": "properties.title,sheets.properties.title"},
                    )
                ).json()
                sheets = [
                    str((s.get("properties") or {}).get("title", ""))
                    for s in self.items(meta, "sheets")
                ]
                rng = a.range or (sheets[0] if sheets else "A1:Z100")
                values = (
                    await http.get(
                        f"/spreadsheets/{a.spreadsheet_id}/values/{rng}",
                        params={"valueRenderOption": "FORMATTED_VALUE"},
                    )
                ).json()
            raw = values.get("values")
            rows: list[list[Any]] = [list(r) for r in raw] if isinstance(raw, list) else []
            cells = sum(len(r) for r in rows)
            truncated = cells > MAX_CELLS
            if truncated:
                kept: list[list[Any]] = []
                budget = MAX_CELLS
                for r in rows:
                    if budget <= 0:
                        break
                    kept.append(r[:budget])
                    budget -= len(r)
                rows = kept
            title = str((meta.get("properties") or {}).get("title", ""))
            return {
                "spreadsheet_id": a.spreadsheet_id,
                "title": self.wrap(title, ref=a.spreadsheet_id),
                "sheets": sheets,
                "range": values.get("range", rng),
                "rows": [[self.wrap(str(c), ref=a.spreadsheet_id) for c in r] for r in rows],
                "truncated": truncated,
                "sources": [
                    self.source(object_id=a.spreadsheet_id, title=title, url=_url(a.spreadsheet_id))
                ],
            }

        async def create_spreadsheet(
            ctx: ProviderContext, a: CreateSpreadsheetArgs
        ) -> dict[str, Any]:
            async with self.http(ctx) as http:
                created = (
                    await http.post("/spreadsheets", json={"properties": {"title": a.title}})
                ).json()
                sid = str(created.get("spreadsheetId", ""))
                if a.headers:
                    await http.put(
                        f"/spreadsheets/{sid}/values/A1",
                        params={"valueInputOption": "USER_ENTERED"},
                        json={"values": [a.headers]},
                    )
            return {
                "spreadsheet_id": sid,
                "title": a.title,
                "url": created.get("spreadsheetUrl") or _url(sid),
            }

        async def verify_create(
            ctx: ProviderContext, a: CreateSpreadsheetArgs, result: dict[str, Any]
        ) -> Verification:
            async with self.http(ctx) as http:
                meta = (
                    await http.get(
                        f"/spreadsheets/{result['spreadsheet_id']}",
                        params={"fields": "properties.title"},
                    )
                ).json()
            if (meta.get("properties") or {}).get("title") != a.title:
                return Verification.failed("Spreadsheet exists but its title differs")
            return Verification.verified("Spreadsheet is in your Drive")

        async def write_range(ctx: ProviderContext, a: WriteRangeArgs) -> dict[str, Any]:
            async with self.http(ctx) as http:
                out = (
                    await http.put(
                        f"/spreadsheets/{a.spreadsheet_id}/values/{a.range}",
                        params={"valueInputOption": "USER_ENTERED"},
                        json={"values": a.values},
                    )
                ).json()
            return {
                "spreadsheet_id": a.spreadsheet_id,
                "updated_range": out.get("updatedRange", a.range),
                "updated_cells": out.get("updatedCells", 0),
                "url": _url(a.spreadsheet_id),
            }

        async def verify_write(
            ctx: ProviderContext, a: WriteRangeArgs, result: dict[str, Any]
        ) -> Verification:
            async with self.http(ctx) as http:
                back = (
                    await http.get(
                        f"/spreadsheets/{a.spreadsheet_id}/values/{result['updated_range']}"
                    )
                ).json()
            rows = back.get("values") if isinstance(back.get("values"), list) else []
            first_sent = [str(v) if v is not None else "" for v in a.values[0]]
            first_back = [str(v) for v in (rows[0] if rows else [])]
            if first_back[: len(first_sent)] != first_sent:
                return Verification.failed("Cells were written but read back differently")
            return Verification.verified(f"{result.get('updated_cells', 0)} cell(s) updated")

        async def append_rows(ctx: ProviderContext, a: AppendRowsArgs) -> dict[str, Any]:
            async with self.http(ctx) as http:
                out = (
                    await http.post(
                        f"/spreadsheets/{a.spreadsheet_id}/values/{a.range}:append",
                        params={
                            "valueInputOption": "USER_ENTERED",
                            "insertDataOption": "INSERT_ROWS",
                        },
                        json={"values": a.rows},
                    )
                ).json()
            updates = out.get("updates") or {}
            return {
                "spreadsheet_id": a.spreadsheet_id,
                "updated_range": updates.get("updatedRange", a.range),
                "updated_rows": updates.get("updatedRows", len(a.rows)),
                "url": _url(a.spreadsheet_id),
            }

        async def verify_append(
            ctx: ProviderContext, a: AppendRowsArgs, result: dict[str, Any]
        ) -> Verification:
            async with self.http(ctx) as http:
                back = (
                    await http.get(
                        f"/spreadsheets/{a.spreadsheet_id}/values/{result['updated_range']}"
                    )
                ).json()
            rows = back.get("values") if isinstance(back.get("values"), list) else []
            if len(rows) < len(a.rows):
                return Verification.failed("Fewer rows were found than were appended")
            return Verification.verified(f"{len(a.rows)} row(s) appended")

        return [
            ProviderTool(
                "search_spreadsheets",
                "Find spreadsheets by name.",
                SearchSpreadsheetsArgs,
                Capability.search,
                search_spreadsheets,
                lambda a: f"Search Google Sheets for “{a.query}”",
                scope=SCOPE_DISCOVER,
            ),
            ProviderTool(
                "read_range",
                "Read cells from a spreadsheet (A1 range; first sheet by default).",
                ReadRangeArgs,
                Capability.read,
                read_range,
                lambda a: f"Read {a.range or 'the first sheet'} from a spreadsheet",
                scope=SCOPE_READ,
                outputs=(
                    F("title", "Spreadsheet name"),
                    F("rows", "Rows", "list"),
                    F("range", "Range read"),
                ),
            ),
            ProviderTool(
                "create_spreadsheet",
                "Create a new spreadsheet, optionally with a header row.",
                CreateSpreadsheetArgs,
                Capability.create,
                create_spreadsheet,
                lambda a: f"Create spreadsheet “{a.title}”",
                verify=verify_create,
                scope=SCOPE_WRITE,
            ),
            ProviderTool(
                "write_range",
                "Overwrite cells in an A1 range.",
                WriteRangeArgs,
                Capability.update,
                write_range,
                lambda a: f"Write {len(a.values)} row(s) to {a.range}",
                verify=verify_write,
                scope=SCOPE_WRITE,
            ),
            ProviderTool(
                "append_rows",
                "Append rows to the end of a sheet.",
                AppendRowsArgs,
                Capability.update,
                append_rows,
                lambda a: f"Append {len(a.rows)} row(s) to {a.range}",
                verify=verify_append,
                scope=SCOPE_WRITE,
            ),
        ]
