import asyncio
import json

import httpx
import pytest

from app.core import ai, embed
from app.core.config import get_settings
from app.workers import queue
from tests.test_rag import fake_vector
from tests.test_workspaces import _workspace


@pytest.fixture
def scripted(monkeypatch):
    """The model plays back `turns` in order; embeddings are the fake bag-of-words ones."""
    s = get_settings()
    for k, v in {
        "embed_provider": "gemini",
        "embed_model": "fake-embed",
        "embed_dim": 768,
        "gemini_api_key": "k",
        "llm_providers": "gemini",
        "ai_cache": False,
    }.items():
        monkeypatch.setattr(s, k, v)
    turns: list[dict] = []
    seen: list[dict] = []

    def embed_handler(request):
        body = json.loads(request.content)
        return httpx.Response(
            200, json={"data": [{"embedding": fake_vector(t)} for t in body["input"]]}
        )

    def chat_handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"model": "m", "choices": [{"message": turns.pop(0)}]})

    monkeypatch.setattr(embed, "_transport", httpx.MockTransport(embed_handler))
    monkeypatch.setattr(ai, "_transport", httpx.MockTransport(chat_handler))
    return turns, seen


def _events(text: str) -> list[tuple[str, dict]]:
    out, ev = [], None
    for line in text.splitlines():
        if line.startswith("event:"):
            ev = line[6:].strip()
        elif line.startswith("data:"):
            out.append((ev, json.loads(line[5:])))
    return out


def _call(name, args, id="c1"):
    return {"id": id, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}


def test_agent_searches_then_answers_with_citations(as_user, scripted):
    turns, seen = scripted
    turns.extend(
        [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [_call("search_sources", {"query": "prix du riz"})],
            },
            {"role": "assistant", "content": "Le prix est resté stable [1]."},
        ]
    )
    alice = as_user("alice")
    ws = _workspace(alice)
    alice.post(
        f"/api/v1/workspaces/{ws}/sources",
        json={"title": "Relevé INSTAT", "text": "Le prix du riz est resté stable à 3 200 ariary."},
    )
    while asyncio.run(queue.run_once()):
        pass
    r = alice.post(f"/api/v1/workspaces/{ws}/agent", json={"question": "Le riz a-t-il doublé ?"})
    events = _events(r.text)
    assert [e for e, _ in events] == ["step", "answer", "done"]
    step = events[0][1]
    assert (step["tool"], step["input"], step["n"]) == (
        "search_sources",
        {"query": "prix du riz"},
        1,
    )
    answer = events[1][1]
    assert answer["text"] == "Le prix est resté stable [1]."
    assert answer["citations"][0]["title"] == "Relevé INSTAT"
    # The tool result went back to the model, tied to its call.
    tool_msg = seen[1]["messages"][-1]
    assert tool_msg["role"] == "tool" and tool_msg["tool_call_id"] == "c1"
    assert "3 200 ariary" in tool_msg["content"]


def test_agent_survives_unknown_tools_and_bad_arguments(as_user, scripted):
    turns, _ = scripted
    turns.extend(
        [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    _call("delete_everything", {}),
                    _call("find_claims", {"nope": 1}, "c2"),
                ],
            },
            {"role": "assistant", "content": "Je ne peux pas conclure."},
        ]
    )
    alice = as_user("alice")
    ws = _workspace(alice)
    events = _events(alice.post(f"/api/v1/workspaces/{ws}/agent", json={"question": "x?"}).text)
    assert [d["summary"] for e, d in events if e == "step"] == [
        "outil inconnu",
        "arguments invalides",
    ]
    assert events[-1][0] == "done"


def test_agent_stops_after_max_steps(as_user, scripted):
    turns, seen = scripted
    from app.modules.agent import MAX_STEPS

    loop = {
        "role": "assistant",
        "content": None,
        "tool_calls": [_call("find_claims", {"query": "riz"})],
    }
    turns.extend([loop] * (MAX_STEPS - 1) + [{"role": "assistant", "content": "Synthèse."}])
    alice = as_user("alice")
    ws = _workspace(alice)
    events = _events(alice.post(f"/api/v1/workspaces/{ws}/agent", json={"question": "x?"}).text)
    assert [e for e, _ in events].count("step") == MAX_STEPS - 1
    assert events[-2] == ("answer", {"text": "Synthèse.", "citations": []})
    # The last turn is asked without tools, so it must answer.
    assert "tools" not in seen[-1]
