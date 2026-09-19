"""Development-only harness for the scripted AI provider.

Mounted only when AI_PROVIDER=fake (which production configuration refuses), so end-to-end
tests can script model replies over HTTP. Never part of the real API surface.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from langchain_core.messages import AIMessage
from pydantic import BaseModel, Field

from app.ai.llm import set_fake_script
from app.api.deps import CurrentAuth
from app.core.responses import Envelope, ok

router = APIRouter(prefix="/ai/_dev", tags=["ai-dev"])


class ScriptedToolCall(BaseModel):
    name: str
    args: dict[str, Any] = Field(default_factory=dict)
    id: str


class ScriptedReply(BaseModel):
    content: str = ""
    tool_calls: list[ScriptedToolCall] = Field(default_factory=list)


class ScriptRequest(BaseModel):
    replies: list[ScriptedReply] = Field(min_length=1, max_length=20)


@router.post("/script", response_model=Envelope[dict[str, int]])
async def set_script(payload: ScriptRequest, ctx: CurrentAuth) -> dict[str, Any]:
    set_fake_script(
        [
            AIMessage(
                content=r.content,
                tool_calls=[
                    {"name": t.name, "args": t.args, "id": t.id, "type": "tool_call"}
                    for t in r.tool_calls
                ],
            )
            for r in payload.replies
        ],
        user_id=str(ctx.user.id),
    )
    return ok({"replies": len(payload.replies)})
