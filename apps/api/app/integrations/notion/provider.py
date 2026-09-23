"""Notion: public integration OAuth (Basic-auth JSON token endpoint), REST API v1."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.ai.tools.base import OutputField as F
from app.ai.tools.base import Verification
from app.core.oauth import OAuthEndpoints
from app.integrations.base.capabilities import Capability
from app.integrations.base.outputs import HIT_FIELDS, listing
from app.integrations.base.provider import (
    AuthType,
    ConnectionIdentity,
    PermissionSpec,
    ProviderContext,
    ProviderManifest,
)
from app.integrations.base.rest import ProviderTool, RestOAuthProvider

NOTION_VERSION = "2022-06-28"


def _rich_text(blocks: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for b in blocks:
        inner = b.get(b.get("type", ""), {}) or {}
        parts = inner.get("rich_text") or inner.get("title") or []
        text = "".join(p.get("plain_text", "") for p in parts if isinstance(p, dict))
        if text:
            lines.append(text)
    return "\n".join(lines)


def _title_of(page: dict[str, Any]) -> str:
    for prop in (page.get("properties") or {}).values():
        if isinstance(prop, dict) and prop.get("type") == "title":
            return "".join(t.get("plain_text", "") for t in prop.get("title", [])) or "Untitled"
    return "Untitled"


class SearchPagesArgs(BaseModel):
    """Search Notion pages shared with the integration."""

    query: str = Field(min_length=1, max_length=200)
    limit: int = Field(default=10, ge=1, le=25)


class ReadPageArgs(BaseModel):
    """Read a page's text content by id."""

    page_id: str = Field(min_length=1, max_length=64)


class CreatePageArgs(BaseModel):
    """Create a page under a parent page."""

    parent_page_id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=300)
    body: str = Field(
        default="", max_length=20_000, description="Plain text; blank lines separate paragraphs"
    )


class NotionProvider(RestOAuthProvider):
    settings_prefix = "notion"
    use_pkce = False
    api_base = "https://api.notion.com/v1"
    api_headers = {"Notion-Version": NOTION_VERSION}
    endpoints = OAuthEndpoints(
        authorize_url="https://api.notion.com/v1/oauth/authorize",
        token_url="https://api.notion.com/v1/oauth/token",
        token_auth="basic",
        token_format="json",
        extra_authorize_params={"owner": "user"},
    )
    manifest = ProviderManifest(
        id="notion",
        name="Notion",
        category="notes",
        description="Search and read the pages you share with Notely; create pages with approval.",
        logo_url="https://cdn.simpleicons.org/notion",
        docs_url="https://developers.notion.com/docs/authorization",
        mcp_server_url="https://mcp.notion.com/mcp",
        auth=AuthType.oauth2,
        capabilities=[Capability.search, Capability.read, Capability.create],
        # Notion grants access per page the user selects during consent; there are no scopes.
        permissions=[
            PermissionSpec(
                scope="pages:selected",
                label="Access the pages you choose during setup",
                capability=Capability.read,
            )
        ],
    )

    async def identity(self, ctx: ProviderContext) -> ConnectionIdentity:
        async with self.http(ctx) as http:
            me = (await http.get("/users/me")).json()
        bot = me.get("bot") or {}
        owner = (bot.get("owner") or {}).get("user") or {}
        workspace = bot.get("workspace_name") or ctx.connection.metadata_.get("workspace_name")
        return ConnectionIdentity(
            external_account_id=str(me.get("id")),
            external_account_name=(
                f"{owner.get('name') or me.get('name') or 'Notion'} @ {workspace or 'Notion'}"
            ),
            metadata={"workspace_name": workspace},
        )

    async def probe(self, ctx: ProviderContext) -> str:
        async with self.http(ctx) as http:
            body = (await http.post("/search", json={"page_size": 1})).json()
        return f"{len(body.get('results', []))}+ page(s) shared"

    async def search(self, ctx: ProviderContext, query: str, limit: int) -> list[dict[str, Any]]:
        async with self.http(ctx) as http:
            body = (
                await http.post(
                    "/search",
                    json={
                        "query": query,
                        "page_size": limit,
                        "filter": {"property": "object", "value": "page"},
                    },
                )
            ).json()
        return [
            {
                "id": p["id"],
                "kind": "page",
                "title": _title_of(p),
                "snippet": "",
                "url": p.get("url"),
                "updated_at": p.get("last_edited_time"),
            }
            for p in body.get("results", [])
        ]

    def build_tools(self):  # type: ignore[no-untyped-def]
        async def search_pages(ctx: ProviderContext, a: SearchPagesArgs) -> dict[str, Any]:
            hits = await self.search(ctx, a.query, a.limit)
            return {
                "results": hits,
                "sources": [
                    self.source(object_id=h["id"], title=h["title"], url=h["url"]) for h in hits
                ],
            }

        async def read_page(ctx: ProviderContext, a: ReadPageArgs) -> dict[str, Any]:
            async with self.http(ctx) as http:
                page = (await http.get(f"/pages/{a.page_id}")).json()
                blocks = (
                    await http.get(f"/blocks/{a.page_id}/children", params={"page_size": 100})
                ).json()
            title = _title_of(page)
            return {
                "page_id": a.page_id,
                "title": title,
                "content": self.wrap(_rich_text(blocks.get("results", []))[:12_000], ref=a.page_id),
                "sources": [self.source(object_id=a.page_id, title=title, url=page.get("url"))],
            }

        async def create_page(ctx: ProviderContext, a: CreatePageArgs) -> dict[str, Any]:
            paragraphs = [p.strip() for p in a.body.split("\n\n") if p.strip()]
            payload = {
                "parent": {"page_id": a.parent_page_id},
                "properties": {"title": {"title": [{"text": {"content": a.title}}]}},
                "children": [
                    {
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": [{"type": "text", "text": {"content": p[:2000]}}]
                        },
                    }
                    for p in paragraphs[:50]
                ],
            }
            async with self.http(ctx) as http:
                page = (await http.post("/pages", json=payload)).json()
            return {"page_id": page.get("id"), "url": page.get("url"), "title": a.title}

        async def verify_create_page(
            ctx: ProviderContext, a: CreatePageArgs, result: dict[str, Any]
        ) -> Verification:
            async with self.http(ctx) as http:
                page = (await http.get(f"/pages/{result['page_id']}")).json()
            if page.get("archived") or page.get("in_trash"):
                return Verification.failed("The page exists but is archived")
            title = _title_of(page)
            if title and title != a.title:
                return Verification.failed(f"Page title is “{title}”, not what was requested")
            return Verification.verified("Page exists in Notion")

        return [
            ProviderTool(
                "search_pages",
                "Search Notion pages.",
                SearchPagesArgs,
                Capability.search,
                search_pages,
                lambda a: f"Search Notion for “{a.query}”",
                outputs=(listing("results", "Pages", *HIT_FIELDS),),
            ),
            ProviderTool(
                "read_page",
                "Read a Notion page.",
                ReadPageArgs,
                Capability.read,
                read_page,
                lambda a: "Read a Notion page",
                outputs=(F("title", "Title"), F("content", "Page text", "long_text")),
            ),
            ProviderTool(
                "create_page",
                "Create a Notion page under a parent page.",
                CreatePageArgs,
                Capability.create,
                create_page,
                lambda a: f"Create Notion page “{a.title}”",
                verify=verify_create_page,
            ),
        ]
