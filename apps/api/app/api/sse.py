"""Server-Sent Events helpers for streamed AI responses."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi.responses import StreamingResponse

from app.core.exceptions import APIError
from app.core.logging import get_logger

log = get_logger(__name__)

SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "X-Accel-Buffering": "no",  # disable proxy buffering (nginx)
    "Connection": "keep-alive",
}


def format_event(event: dict[str, Any]) -> str:
    kind = str(event.get("type", "message"))
    return f"event: {kind}\ndata: {json.dumps(event, default=str)}\n\n"


async def _guarded(events: AsyncIterator[dict[str, Any]]) -> AsyncIterator[str]:
    try:
        async for event in events:
            yield format_event(event)
    except APIError as exc:
        yield format_event(
            {"type": "error", "code": exc.code, "message": exc.message, "details": exc.details}
        )
    except Exception:  # noqa: BLE001
        log.exception("sse_stream_failed")
        yield format_event(
            {
                "type": "error",
                "code": "INTERNAL_ERROR",
                "message": "Something went wrong on our side.",
            }
        )


def sse_response(events: AsyncIterator[dict[str, Any]]) -> StreamingResponse:
    return StreamingResponse(_guarded(events), media_type="text/event-stream", headers=SSE_HEADERS)
