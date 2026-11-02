from collections.abc import AsyncIterable
from typing import Any

from fastapi import APIRouter
from fastapi.sse import EventSourceResponse, ServerSentEvent
from pydantic import BaseModel, Field

from app.core import ai
from app.core.access import AnyMember
from app.core.errors import ApiError

router = APIRouter(tags=["ai"])


class CompleteIn(BaseModel):
    messages: list[dict[str, Any]] = Field(min_length=1)
    tools: list[dict[str, Any]] | None = None
    temperature: float | None = None
    max_tokens: int | None = Field(default=None, gt=0)


class CompleteOut(BaseModel):
    content: str
    tool_calls: list[dict[str, Any]] | None
    provider: str
    model: str
    tokens_in: int | None
    tokens_out: int | None
    cached: bool


def _params(body: CompleteIn) -> dict[str, Any]:
    return body.model_dump(exclude={"messages", "tools"}, exclude_none=True)


def _out(c: ai.Completion) -> CompleteOut:
    return CompleteOut(
        content=c.content,
        tool_calls=c.tool_calls,
        provider=c.provider,
        model=c.model,
        tokens_in=c.tokens_in,
        tokens_out=c.tokens_out,
        cached=c.cached,
    )


@router.post("/workspaces/{ws}/ai/complete")
async def complete(body: CompleteIn, member: AnyMember) -> CompleteOut:
    try:
        reply = await ai.complete(
            body.messages, body.tools, workspace_id=member.workspace_id, **_params(body)
        )
    except ai.AiUnavailable as e:
        raise ApiError(503, "ai_unavailable", str(e)) from e
    return _out(reply)


@router.post("/workspaces/{ws}/ai/stream", response_class=EventSourceResponse)
async def stream(body: CompleteIn, member: AnyMember) -> AsyncIterable[ServerSentEvent]:
    """SSE: `delta` events ({"text"}), then `done` (the full completion) or `error`."""
    s = ai.complete(
        body.messages, body.tools, stream=True, workspace_id=member.workspace_id, **_params(body)
    )
    try:
        async for text in s:
            yield ServerSentEvent(data={"text": text}, event="delta")
    except ai.AiUnavailable as e:
        yield ServerSentEvent(data={"code": "ai_unavailable", "message": str(e)}, event="error")
        return
    except Exception as e:  # noqa: BLE001 - the stream broke after it started
        yield ServerSentEvent(data={"code": "ai_stream_failed", "message": str(e)}, event="error")
        return
    yield ServerSentEvent(data=_out(s.completion), event="done")
