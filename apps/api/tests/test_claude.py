"""Claude through the gateway: the OpenAI-style conversation is translated both ways, Claude's own
blocks (thinking included) are replayed to Claude only, and failures fall back like any provider."""

import asyncio
import json

import httpx2
import pytest

from app.core import ai, claude
from app.core.config import get_settings
from tests.test_agent import _events
from tests.test_workspaces import _workspace


def _message(*blocks, stop="end_turn"):
    return {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "model": "claude-opus-5-5",
        "content": list(blocks),
        "stop_reason": stop,
        "stop_sequence": None,
        "usage": {"input_tokens": 12, "output_tokens": 5},
    }


@pytest.fixture
def anthropic_api(monkeypatch):
    s = get_settings()
    for k, v in {"llm_providers": "claude", "claude_api_key": "sk-test", "ai_cache": False}.items():
        monkeypatch.setattr(s, k, v)
    replies: list = []
    seen: list[dict] = []

    def handler(request):
        seen.append(json.loads(request.content))
        r = replies.pop(0)
        return r if isinstance(r, httpx2.Response) else httpx2.Response(200, json=r)

    monkeypatch.setattr(claude, "_transport", httpx2.MockTransport(handler))
    return replies, seen


def test_agent_loop_runs_on_claude_and_replays_its_blocks(as_user, anthropic_api):
    replies, seen = anthropic_api
    thinking = {"type": "thinking", "thinking": "", "signature": "sig-1"}
    replies.extend(
        [
            _message(
                thinking,
                {
                    "type": "tool_use",
                    "id": "toolu_1",
                    "name": "find_claims",
                    "input": {"query": "riz"},
                },
                stop="tool_use",
            ),
            _message({"type": "text", "text": "Rien sur le riz pour l'instant."}),
        ]
    )
    alice = as_user("alice")
    ws = _workspace(alice)
    events = _events(
        alice.post(f"/api/v1/workspaces/{ws}/agent", json={"question": "Le riz ?"}).text
    )
    assert [e for e, _ in events] == ["step", "answer", "done"]
    assert events[1][1]["text"] == "Rien sur le riz pour l'instant."
    assert events[2][1]["provider"] == "claude"

    first, second = seen
    assert first["system"].startswith("Tu es l'agent") and "temperature" not in first
    assert first["fallbacks"] == "default" and first["max_tokens"] >= 4096
    assert first["tools"][0]["name"] == "search_sources" and "input_schema" in first["tools"][0]
    # the second turn carries Claude's blocks back unchanged, then the tool result
    assert second["messages"][1] == {"role": "assistant", "content": [thinking, first_call(second)]}
    result = second["messages"][2]["content"][0]
    assert result["type"] == "tool_result" and result["tool_use_id"] == "toolu_1"


def first_call(body):
    return next(b for b in body["messages"][1]["content"] if b["type"] == "tool_use")


def test_foreign_tool_calls_and_json_mode_are_translated():
    msgs = [
        {"role": "system", "content": "Consigne."},
        {"role": "user", "content": "Question"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"id": "call 7!", "type": "function", "function": {"name": "f", "arguments": "{}"}}
            ],
        },
        {"role": "tool", "tool_call_id": "call 7!", "content": "résultat"},
    ]
    args = claude.request(
        "claude-haiku-5-5", msgs, None, {"response_format": {"type": "json_object"}}
    )
    assert args["system"].endswith(claude.JSON_ONLY) and "fallbacks" not in args
    call = args["messages"][1]["content"][0]
    assert (
        call["type"] == "tool_use"
        and call["id"] == args["messages"][2]["content"][0]["tool_use_id"]
    )


def test_a_refusal_or_an_overload_falls_back(anthropic_api, monkeypatch):
    replies, _ = anthropic_api
    replies.append(_message({"type": "text", "text": ""}, stop="refusal"))
    with pytest.raises(ai.AiUnavailable, match="Refused"):
        asyncio.run(ai.complete([{"role": "user", "content": "x"}]))
    monkeypatch.setattr(get_settings(), "ai_attempts", 1)
    replies.append(
        httpx2.Response(
            529, json={"type": "error", "error": {"type": "overloaded_error", "message": "busy"}}
        )
    )
    with pytest.raises(ai.AiUnavailable, match="_Retryable"):
        asyncio.run(ai.complete([{"role": "user", "content": "x"}]))


def test_claude_streams_text(anthropic_api):
    replies, _ = anthropic_api
    events = [
        ("message_start", {"type": "message_start", "message": {**_message(), "content": []}}),
        (
            "content_block_start",
            {
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "text", "text": ""},
            },
        ),
        (
            "content_block_delta",
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "text_delta", "text": "Bon"},
            },
        ),
        (
            "content_block_delta",
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "text_delta", "text": "jour"},
            },
        ),
        ("content_block_stop", {"type": "content_block_stop", "index": 0}),
        (
            "message_delta",
            {
                "type": "message_delta",
                "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                "usage": {"output_tokens": 2},
            },
        ),
        ("message_stop", {"type": "message_stop"}),
    ]
    sse = "".join(f"event: {e}\ndata: {json.dumps(d)}\n\n" for e, d in events)
    replies.append(
        httpx2.Response(200, content=sse.encode(), headers={"content-type": "text/event-stream"})
    )

    async def run():
        stream = ai.complete([{"role": "user", "content": "Salut"}], stream=True)
        parts = [t async for t in stream]
        return parts, stream.completion

    parts, done = asyncio.run(run())
    assert "".join(parts) == "Bonjour" and done.provider == "claude" and done.content == "Bonjour"
