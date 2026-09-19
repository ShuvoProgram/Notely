"""A small, real MCP server (Streamable HTTP) for local development and end-to-end tests.

Run:  uv run python scripts/demo_mcp_server.py --port 8765 --token demo-token
Then connect it in Notely: Settings → Connections → MCP server → URL http://localhost:8765/mcp

It exposes read-only, write and destructive tools so the approval pipeline can be exercised.
"""

from __future__ import annotations

import argparse

import uvicorn
from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

PAGES: dict[str, dict[str, str]] = {
    "p1": {"title": "Pricing FAQ", "body": "Annual plans get two months free."},
    "p2": {"title": "Launch checklist", "body": "Announce, monitor, celebrate."},
}


def build_server() -> MCPServer:
    server = MCPServer("Demo Docs")

    @server.tool(annotations=ToolAnnotations(read_only_hint=True))
    def search_docs(query: str) -> list[dict[str, str]]:
        """Search documentation pages by keyword."""
        q = query.lower()
        return [
            {"id": pid, "title": p["title"], "snippet": p["body"]}
            for pid, p in PAGES.items()
            if q in p["title"].lower() or q in p["body"].lower()
        ]

    @server.tool(annotations=ToolAnnotations(read_only_hint=True))
    def read_page(page_id: str) -> dict[str, str]:
        """Read one page by id."""
        page = PAGES.get(page_id)
        if page is None:
            raise ValueError("no such page")
        return {"id": page_id, **page}

    @server.tool()
    def create_page(title: str, body: str = "") -> dict[str, str]:
        """Create a documentation page."""
        pid = f"p{len(PAGES) + 1}"
        PAGES[pid] = {"title": title, "body": body}
        return {"id": pid, "title": title}

    @server.tool(annotations=ToolAnnotations(destructive_hint=True))
    def delete_page(page_id: str) -> str:
        """Delete a page permanently."""
        PAGES.pop(page_id, None)
        return f"deleted {page_id}"

    return server


class BearerAuth(BaseHTTPMiddleware):
    def __init__(self, app, token: str | None) -> None:  # type: ignore[no-untyped-def]
        super().__init__(app)
        self.token = token

    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        if self.token and request.headers.get("authorization") != f"Bearer {self.token}":
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        response: Response = await call_next(request)
        return response


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--token", default=None, help="Require this bearer token (optional)")
    args = parser.parse_args()

    mcp_app = build_server().streamable_http_app()
    app = Starlette(routes=mcp_app.routes, lifespan=mcp_app.router.lifespan_context)
    app.add_middleware(BearerAuth, token=args.token)
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
