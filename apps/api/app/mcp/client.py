"""Thin wrapper over the official MCP Python SDK client.

Production connects over Streamable HTTP with an optional bearer token. Tests connect to an
in-process `MCPServer` through the SDK's in-memory transport — same code path, no network.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

import httpx
import httpx2
from mcp.client import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.types import CallToolResult, TextContent, Tool

from app.integrations.base.errors import ProviderError, ProviderErrorKind

DEFAULT_TIMEOUT = 30.0

# Tests swap this to point at an in-memory server; production uses the HTTP factory below.
ClientFactory = Callable[[str, str | None], Client]


def http_client_factory(url: str, token: str | None) -> Client:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    http = httpx2.AsyncClient(headers=headers, timeout=DEFAULT_TIMEOUT, follow_redirects=True)
    return Client(
        streamable_http_client(url, http_client=http), read_timeout_seconds=DEFAULT_TIMEOUT
    )


_client_factory: ClientFactory = http_client_factory


def set_client_factory(factory: ClientFactory | None) -> None:
    global _client_factory
    _client_factory = factory or http_client_factory


@dataclass(frozen=True)
class MCPToolInfo:
    name: str
    description: str
    input_schema: dict[str, Any]
    read_only: bool
    destructive: bool
    idempotent: bool

    @classmethod
    def from_tool(cls, tool: Tool) -> MCPToolInfo:
        ann = tool.annotations
        return cls(
            name=tool.name,
            description=tool.description or tool.title or tool.name,
            input_schema=dict(tool.input_schema or {"type": "object", "properties": {}}),
            read_only=bool(ann and ann.read_only_hint),
            destructive=bool(ann and ann.destructive_hint is True),
            idempotent=bool(ann and ann.idempotent_hint),
        )


class MCPConnection:
    def __init__(self, client: Client, provider: str) -> None:
        self._client = client
        self.provider = provider

    async def list_tools(self) -> list[MCPToolInfo]:
        result = await self._client.list_tools()
        return [MCPToolInfo.from_tool(t) for t in result.tools]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        result: CallToolResult = await self._client.call_tool(name, arguments)
        text_parts = [c.text for c in result.content if isinstance(c, TextContent)]
        payload: dict[str, Any] = {}
        if result.structured_content is not None:
            payload["structured"] = result.structured_content
        if text_parts:
            payload["text"] = "\n".join(text_parts)
        if result.is_error:
            raise ProviderError(
                ProviderErrorKind.invalid_request,
                payload.get("text") or "Tool reported an error",
                provider=self.provider,
            )
        return payload

    @property
    def server_info(self) -> dict[str, Any]:
        info = self._client.server_info
        return {"name": info.name, "version": info.version} if info else {}


@asynccontextmanager
async def connect(
    url: str, token: str | None, *, provider: str = "mcp"
) -> AsyncIterator[MCPConnection]:
    client = _client_factory(url, token)
    try:
        async with client:
            yield MCPConnection(client, provider)
    except ProviderError:
        raise
    except httpx.HTTPStatusError as exc:
        from app.integrations.base.errors import classify_http_status

        raise classify_http_status(exc.response.status_code, provider=provider) from exc
    except (httpx.HTTPError, TimeoutError, ConnectionError, OSError) as exc:
        raise ProviderError(
            ProviderErrorKind.unavailable, type(exc).__name__, provider=provider
        ) from exc
    except Exception as exc:  # noqa: BLE001 — SDK wraps protocol failures; probe to classify
        kind = await _classify_failure(url, token)
        raise ProviderError(kind, type(exc).__name__, provider=provider) from exc


async def _classify_failure(url: str, token: str | None) -> ProviderErrorKind:
    """The SDK hides HTTP status codes; a cheap probe tells auth problems from outages."""
    if not url.startswith("http"):
        return ProviderErrorKind.unavailable
    headers = {"Accept": "application/json, text/event-stream"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        async with httpx.AsyncClient(timeout=5, headers=headers) as http:
            resp = await http.post(url, json={"jsonrpc": "2.0", "id": 0, "method": "ping"})
    except httpx.HTTPError:
        return ProviderErrorKind.unavailable
    if resp.status_code == 401:
        return ProviderErrorKind.auth_failed
    if resp.status_code == 403:
        return ProviderErrorKind.permission_denied
    if resp.status_code == 404:
        return ProviderErrorKind.not_found
    return ProviderErrorKind.unavailable
