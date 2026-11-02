import asyncio
import json

import httpx
import pytest
from sqlalchemy import select

from app.core import ai
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.models import AiCall
from tests.test_workspaces import _workspace

MSGS = [{"role": "user", "content": "Bonjour"}]


def _reply(text: str, model: str = "m") -> dict:
    return {
        "model": model,
        "choices": [{"message": {"role": "assistant", "content": text}}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 2},
    }


def _sse(*chunks: dict) -> bytes:
    lines = [f"data: {json.dumps(c)}\n\n" for c in chunks] + ["data: [DONE]\n\n"]
    return "".join(lines).encode()


@pytest.fixture
def fake(monkeypatch):
    """Route provider calls to per-host handlers; returns (routes, calls)."""
    s = get_settings()
    for name in ("groq", "gemini", "nvidia"):
        monkeypatch.setattr(s, f"{name}_api_key", f"key-{name}")
    monkeypatch.setattr(s, "llm_providers", "groq,gemini,nvidia")
    monkeypatch.setattr(s, "ai_cache", False)
    monkeypatch.setattr(s, "ai_attempts", 2)

    async def no_sleep(_):
        pass

    monkeypatch.setattr(ai, "_sleep", no_sleep)
    routes: dict[str, object] = {}
    calls: list[str] = []

    def dispatch(request: httpx.Request) -> httpx.Response:
        name = next(n for n, (url, _) in ai.PROVIDERS.items() if request.url.host in url)
        calls.append(name)
        handler = routes.get(name)
        if handler is None:
            return httpx.Response(500, text="no route")
        if isinstance(handler, Exception):
            raise handler
        return handler(request) if callable(handler) else handler

    monkeypatch.setattr(ai, "_transport", httpx.MockTransport(dispatch))
    return routes, calls


def _logged() -> list[AiCall]:
    async def go():
        async with SessionLocal() as db:
            return list(await db.scalars(select(AiCall).order_by(AiCall.created_at)))

    return asyncio.run(go())


def test_primary_answers(fake):
    routes, calls = fake
    routes["groq"] = httpx.Response(200, json=_reply("Salut", "llama"))
    reply = asyncio.run(ai.complete(MSGS))
    assert (reply.content, reply.provider, reply.model) == ("Salut", "groq", "llama")
    assert (reply.tokens_in, reply.tokens_out) == (5, 2)
    assert calls == ["groq"]
    [row] = _logged()
    assert (row.provider, row.ok, row.tokens_in) == ("groq", True, 5)


def test_rate_limited_primary_falls_back_at_once_and_is_set_aside(fake):
    routes, calls = fake
    routes["groq"] = httpx.Response(429, text="rate limited", headers={"retry-after": "20"})
    routes["gemini"] = httpx.Response(200, json=_reply("Depuis Gemini"))
    reply = asyncio.run(ai.complete(MSGS))
    assert reply.provider == "gemini"
    # No retry on a 429: waiting would only make the journalist wait.
    assert calls == ["groq", "gemini"]
    assert [(r.provider, r.ok) for r in _logged()] == [("groq", False), ("gemini", True)]
    # While Groq cools down, the next call goes straight to Gemini.
    calls.clear()
    asyncio.run(ai.complete(MSGS))
    assert calls == ["gemini"]


def test_server_errors_are_retried_then_set_aside(fake):
    routes, calls = fake
    routes["groq"] = httpx.Response(503)
    routes["gemini"] = httpx.Response(200, json=_reply("ok"))
    asyncio.run(ai.complete(MSGS))
    assert calls == ["groq", "groq", "gemini"]
    calls.clear()
    asyncio.run(ai.complete(MSGS))
    assert calls == ["gemini"]


def test_several_keys_take_turns_and_a_limited_key_is_skipped(fake, monkeypatch):
    routes, calls = fake
    monkeypatch.setattr(get_settings(), "groq_api_key", "mock-key-a, mock-key-b")
    used = []

    def handler(request):
        used.append(request.headers["authorization"].removeprefix("Bearer "))
        if used[-1] == "mock-key-a" and len(used) > 2:
            return httpx.Response(429)
        return httpx.Response(200, json=_reply("ok"))

    routes["groq"] = handler
    for _ in range(3):
        asyncio.run(ai.complete(MSGS))
    # a, b, then a is limited so b takes over within the same call.
    assert used == ["mock-key-a", "mock-key-b", "mock-key-a", "mock-key-b"]
    assert calls == ["groq"] * 4


def test_oversized_prompt_skips_a_small_quota_provider(fake, monkeypatch):
    routes, calls = fake
    monkeypatch.setattr(get_settings(), "llm_max_prompt_tokens_groq", 100)
    routes["gemini"] = httpx.Response(200, json=_reply("long"))
    big = [{"role": "user", "content": "mot " * 500}]
    assert asyncio.run(ai.complete(big)).provider == "gemini"
    assert calls == ["gemini"]
    routes["groq"] = httpx.Response(200, json=_reply("court"))
    calls.clear()
    assert asyncio.run(ai.complete(MSGS)).provider == "groq"


def test_timeout_is_retried_then_falls_back(fake):
    routes, calls = fake
    routes["groq"] = httpx.ReadTimeout("slow")
    routes["gemini"] = httpx.Response(503)
    routes["nvidia"] = httpx.Response(200, json=_reply("ok"))
    assert asyncio.run(ai.complete(MSGS)).provider == "nvidia"
    assert calls == ["groq", "groq", "gemini", "gemini", "nvidia"]


def test_client_error_skips_retry(fake):
    routes, calls = fake
    routes["groq"] = httpx.Response(401, text="bad key")
    routes["gemini"] = httpx.Response(200, json=_reply("ok"))
    assert asyncio.run(ai.complete(MSGS)).provider == "gemini"
    assert calls == ["groq", "gemini"]


def test_missing_key_skips_provider(fake, monkeypatch):
    routes, calls = fake
    monkeypatch.setattr(get_settings(), "groq_api_key", "")
    routes["gemini"] = httpx.Response(200, json=_reply("ok"))
    assert asyncio.run(ai.complete(MSGS)).provider == "gemini"
    assert calls == ["gemini"]


def test_all_failing_raises(fake):
    _, calls = fake
    with pytest.raises(ai.AiUnavailable) as e:
        asyncio.run(ai.complete(MSGS))
    assert len(calls) == 6
    assert "nvidia" in str(e.value)


def test_request_carries_model_tools_and_params(fake, monkeypatch):
    routes, _ = fake
    monkeypatch.setattr(get_settings(), "llm_model_groq", "custom-model")
    seen = {}

    def capture(request):
        seen.update(json.loads(request.content), auth=request.headers["authorization"])
        msg = {"role": "assistant", "content": None, "tool_calls": [{"id": "t1"}]}
        return httpx.Response(200, json={"choices": [{"message": msg}]})

    routes["groq"] = capture
    tools = [{"type": "function", "function": {"name": "search", "parameters": {}}}]
    reply = asyncio.run(ai.complete(MSGS, tools, temperature=0.2))
    assert (seen["model"], seen["temperature"], seen["tools"]) == ("custom-model", 0.2, tools)
    assert seen["auth"] == "Bearer key-groq"
    assert reply.tool_calls == [{"id": "t1"}]
    assert reply.message == {"role": "assistant", "content": "", "tool_calls": [{"id": "t1"}]}


def test_cache_answers_repeat_requests(fake, monkeypatch):
    routes, calls = fake
    monkeypatch.setattr(get_settings(), "ai_cache", True)
    routes["groq"] = httpx.Response(200, json=_reply("une fois"))
    first = asyncio.run(ai.complete(MSGS))
    second = asyncio.run(ai.complete(MSGS))
    assert (first.cached, second.cached, second.content) == (False, True, "une fois")
    assert calls == ["groq"]


def _collect(stream: ai.Stream) -> list[str]:
    async def go():
        return [t async for t in stream]

    return asyncio.run(go())


def test_stream_yields_deltas_and_assembles_completion(fake):
    routes, _ = fake
    routes["groq"] = httpx.Response(
        200,
        content=_sse(
            {"model": "llama", "choices": [{"delta": {"content": "Bon"}}]},
            {"choices": [{"delta": {"content": "jour"}}]},
            {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "id": "c1",
                                    "function": {"name": "se", "arguments": "{"},
                                }
                            ]
                        }
                    }
                ]
            },
            {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {"index": 0, "function": {"name": "arch", "arguments": "}"}}
                            ]
                        }
                    }
                ]
            },
            {"choices": [], "usage": {"prompt_tokens": 7, "completion_tokens": 3}},
        ),
        headers={"content-type": "text/event-stream"},
    )
    s = ai.complete(MSGS, stream=True)
    assert _collect(s) == ["Bon", "jour"]
    c = s.completion
    assert (c.content, c.provider, c.model, c.tokens_in) == ("Bonjour", "groq", "llama", 7)
    assert c.tool_calls[0]["function"] == {"name": "search", "arguments": "{}"}
    [row] = _logged()
    assert (row.ok, row.tokens_out) == (True, 3)


def test_stream_falls_back_before_first_chunk(fake):
    routes, calls = fake
    routes["groq"] = httpx.Response(500)
    routes["gemini"] = httpx.Response(
        200, content=_sse({"choices": [{"delta": {"content": "ok"}}]})
    )
    s = ai.complete(MSGS, stream=True)
    assert _collect(s) == ["ok"]
    assert s.completion.provider == "gemini"
    assert calls == ["groq", "groq", "gemini"]


def test_complete_endpoint(fake, as_user):
    routes, _ = fake
    routes["groq"] = httpx.Response(200, json=_reply("Salut"))
    alice = as_user("alice")
    ws = _workspace(alice)
    r = alice.post(f"/api/v1/workspaces/{ws}/ai/complete", json={"messages": MSGS})
    assert r.status_code == 200
    assert (r.json()["content"], r.json()["provider"]) == ("Salut", "groq")
    assert _logged()[0].workspace_id is not None


def test_complete_endpoint_reports_unavailable(fake, as_user):
    alice = as_user("alice")
    ws = _workspace(alice)
    r = alice.post(f"/api/v1/workspaces/{ws}/ai/complete", json={"messages": MSGS})
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "ai_unavailable"


def test_stream_endpoint_sends_sse(fake, as_user):
    routes, _ = fake
    routes["groq"] = httpx.Response(
        200,
        content=_sse(
            {"choices": [{"delta": {"content": "A"}}]}, {"choices": [{"delta": {"content": "B"}}]}
        ),
    )
    alice = as_user("alice")
    ws = _workspace(alice)
    r = alice.post(f"/api/v1/workspaces/{ws}/ai/stream", json={"messages": MSGS})
    assert r.headers["content-type"].startswith("text/event-stream")
    events = [line for line in r.text.splitlines() if line.startswith("event:")]
    assert events == ["event: delta", "event: delta", "event: done"]
    assert '"content":"AB"' in r.text.replace(" ", "")


def test_outsiders_cannot_use_a_workspace_ai(fake, as_user):
    ws = _workspace(as_user("alice"))
    r = as_user("mallory").post(f"/api/v1/workspaces/{ws}/ai/complete", json={"messages": MSGS})
    assert r.status_code == 404


def test_tool_calls_are_replayed_in_each_providers_dialect():
    call = {"id": "c1", "type": "function", "function": {"name": "f", "arguments": "{}"}}
    signed = {**call, "extra_content": {"google": {"thought_signature": "sig"}}}
    msgs = [{"role": "assistant", "content": None, "tool_calls": [call, signed]}]
    gemini = ai.Provider("gemini", "", "k", "m")
    groq = ai.Provider("groq", "", "k", "m")
    to_gemini = ai._replay(gemini, msgs)[0]["tool_calls"]
    assert to_gemini[0]["extra_content"]["google"]["thought_signature"] == ai.GEMINI_UNSIGNED
    assert to_gemini[1]["extra_content"]["google"]["thought_signature"] == "sig"
    assert all("extra_content" not in c for c in ai._replay(groq, msgs)[0]["tool_calls"])
