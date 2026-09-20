"""Trello: boards, cards and search; create cards with approval.

Trello authorises with an API key + user token (its 1.0a-style "authorize" page returns a token
the user pastes), sent as query parameters — so this is a token provider, not OAuth2."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.ai.tools.base import Verification
from app.core.oauth import OAuthEndpoints, OAuthTokens
from app.integrations.base.capabilities import Capability
from app.integrations.base.errors import ProviderError, ProviderErrorKind
from app.integrations.base.http import ProviderHttpClient
from app.integrations.base.provider import (
    AuthType,
    ConfigField,
    ConnectionIdentity,
    PermissionSpec,
    ProviderContext,
    ProviderManifest,
    TokenAuthSpec,
)
from app.integrations.base.rest import ProviderTool, RestOAuthProvider

API = "https://api.trello.com/1"


class _TrelloHttp(ProviderHttpClient):
    """Adds key/token query parameters to every request."""

    def __init__(self, *, key: str, token: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._auth_params = {"key": key, "token": token}

    async def request(self, method: str, url: str, **kwargs: Any) -> Any:
        params = {**(kwargs.pop("params", None) or {}), **self._auth_params}
        return await super().request(method, url, params=params, **kwargs)


class SearchCardsArgs(BaseModel):
    """Search cards across your boards."""

    query: str = Field(min_length=1, max_length=200)
    limit: int = Field(default=10, ge=1, le=50)


class ListBoardsArgs(BaseModel):
    """List your boards and their lists (list ids are needed to create cards)."""


class ReadCardArgs(BaseModel):
    """Read one card by id."""

    card_id: str = Field(min_length=1, max_length=40)


class CreateCardArgs(BaseModel):
    """Create a card in a list."""

    list_id: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=10_000)
    due: str | None = Field(default=None, description="ISO date/time", max_length=40)


class TrelloProvider(RestOAuthProvider):
    settings_prefix = "trello"
    api_base = API
    endpoints = OAuthEndpoints(authorize_url="", token_url="")  # not OAuth2; token only
    manifest = ProviderManifest(
        id="trello",
        name="Trello",
        category="project_management",
        description="Search your boards and cards; create cards with approval.",
        logo_url="https://cdn.simpleicons.org/trello",
        docs_url="https://developer.atlassian.com/cloud/trello/guides/rest-api/authorization/",
        auth=AuthType.token,
        capabilities=[Capability.search, Capability.read, Capability.create],
        permissions=[
            PermissionSpec(
                scope="read", label="Read your boards and cards", capability=Capability.read
            ),
            PermissionSpec(
                scope="write", label="Create cards", required=False, capability=Capability.create
            ),
        ],
        token_auth=TokenAuthSpec(
            label="Token",
            help=(
                "Get an API key from the Trello Power-Up admin page, then open "
                "https://trello.com/1/authorize?expiration=never&scope=read,write&response_type=token"
                "&name=Notely&key=YOUR_KEY to generate a token."
            ),
            help_url="https://trello.com/power-ups/admin",
            fields=[ConfigField(key="api_key", label="API key", kind="text")],
        ),
    )

    def oauth_config(self, settings: Any) -> None:
        return None

    async def refresh_credentials(self, ctx: ProviderContext) -> OAuthTokens | None:  # noqa: ARG002
        return None

    def http(self, ctx: ProviderContext, base_url: str | None = None) -> ProviderHttpClient:
        token = ctx.credentials.access_token
        key = str(ctx.connection.config.get("api_key", ""))
        if not token or not key:
            raise ProviderError(ProviderErrorKind.expired, "missing key/token", provider="trello")
        return _TrelloHttp(
            key=key, token=token, provider="trello", base_url=base_url or self.api_base
        )

    async def identity(self, ctx: ProviderContext) -> ConnectionIdentity:
        async with self.http(ctx) as http:
            me = (await http.get("/members/me", params={"fields": "id,fullName,username"})).json()
        return ConnectionIdentity(
            external_account_id=str(me.get("id")),
            external_account_name=str(me.get("fullName") or me.get("username")),
        )

    async def probe(self, ctx: ProviderContext) -> str:
        async with self.http(ctx) as http:
            boards = (
                await http.get("/members/me/boards", params={"fields": "id", "filter": "open"})
            ).json()
        return f"{len(boards)} board(s)"

    def _hit(self, c: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": c["id"],
            "kind": "task",
            "title": str(c.get("name", "")),
            "snippet": str(c.get("desc") or "")[:200],
            "url": c.get("shortUrl") or c.get("url"),
            "updated_at": c.get("dateLastActivity"),
        }

    async def search(self, ctx: ProviderContext, query: str, limit: int) -> list[dict[str, Any]]:
        async with self.http(ctx) as http:
            body = (
                await http.get(
                    "/search",
                    params={
                        "query": query,
                        "modelTypes": "cards",
                        "cards_limit": limit,
                        "card_fields": "name,desc,shortUrl,dateLastActivity",
                    },
                )
            ).json()
        return [self._hit(c) for c in body.get("cards") or []]

    def _card_out(self, c: dict[str, Any]) -> dict[str, Any]:
        return {
            "card_id": c["id"],
            "name": self.wrap(str(c.get("name", "")), ref=c["id"]),
            "due": c.get("due"),
            "closed": c.get("closed"),
            "url": c.get("shortUrl") or c.get("url"),
        }

    def build_tools(self) -> list[ProviderTool]:
        async def search_cards(ctx: ProviderContext, a: SearchCardsArgs) -> dict[str, Any]:
            hits = await self.search(ctx, a.query, a.limit)
            return {
                "results": [
                    {
                        "card_id": h["id"],
                        "name": self.wrap(h["title"], ref=h["id"]),
                        "url": h["url"],
                    }
                    for h in hits
                ],
                "sources": [
                    self.source(object_id=h["id"], title=h["title"], url=h["url"]) for h in hits
                ],
            }

        async def list_boards(ctx: ProviderContext, a: ListBoardsArgs) -> dict[str, Any]:
            async with self.http(ctx) as http:
                boards = (
                    await http.get(
                        "/members/me/boards",
                        params={"fields": "id,name,url", "filter": "open", "lists": "open"},
                    )
                ).json()
            return {
                "boards": [
                    {
                        "board_id": b["id"],
                        "name": self.wrap(str(b.get("name", "")), ref=b["id"]),
                        "lists": [
                            {
                                "list_id": lst["id"],
                                "name": self.wrap(str(lst.get("name", "")), ref=lst["id"]),
                            }
                            for lst in b.get("lists") or []
                        ],
                    }
                    for b in boards
                ]
            }

        async def read_card(ctx: ProviderContext, a: ReadCardArgs) -> dict[str, Any]:
            async with self.http(ctx) as http:
                c = (
                    await http.get(
                        f"/cards/{a.card_id}", params={"fields": "name,desc,due,closed,shortUrl"}
                    )
                ).json()
            return {
                **self._card_out(c),
                "description": self.wrap(str(c.get("desc") or ""), ref=c["id"]),
                "sources": [
                    self.source(object_id=c["id"], title=str(c.get("name")), url=c.get("shortUrl"))
                ],
            }

        async def create_card(ctx: ProviderContext, a: CreateCardArgs) -> dict[str, Any]:
            params: dict[str, Any] = {"idList": a.list_id, "name": a.name}
            if a.description:
                params["desc"] = a.description
            if a.due:
                params["due"] = a.due
            async with self.http(ctx) as http:
                c = (await http.post("/cards", params=params)).json()
            return {"card_id": c.get("id"), "url": c.get("shortUrl"), "name": a.name}

        async def verify_card(
            ctx: ProviderContext, a: CreateCardArgs, result: dict[str, Any]
        ) -> Verification:
            async with self.http(ctx) as http:
                c = (
                    await http.get(f"/cards/{result['card_id']}", params={"fields": "name,closed"})
                ).json()
            if c.get("closed"):
                return Verification.failed("The card is archived")
            if c.get("name") != a.name:
                return Verification.failed("Card exists but its name differs")
            return Verification.verified("Card is on the board")

        return [
            ProviderTool(
                "search_cards",
                "Search cards across your boards.",
                SearchCardsArgs,
                Capability.search,
                search_cards,
                lambda a: f"Search Trello for “{a.query}”",
            ),
            ProviderTool(
                "list_boards",
                "List your boards and lists.",
                ListBoardsArgs,
                Capability.read,
                list_boards,
                lambda a: "List Trello boards",
            ),
            ProviderTool(
                "read_card",
                "Read one card.",
                ReadCardArgs,
                Capability.read,
                read_card,
                lambda a: f"Read Trello card {a.card_id}",
            ),
            ProviderTool(
                "create_card",
                "Create a card in a list.",
                CreateCardArgs,
                Capability.create,
                create_card,
                lambda a: f"Create Trello card “{a.name}”",
                verify=verify_card,
            ),
        ]
