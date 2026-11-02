import asyncio
import hashlib
import json
import math
import re

import httpx
import pytest

from app.core import ai, embed
from app.core.config import get_settings
from app.modules.rag import split_segments, split_text
from app.workers import queue
from tests.test_workspaces import _workspace

DIM = 768


def fake_vector(text: str) -> list[float]:
    """Bag of words hashed into DIM buckets: texts sharing words are close."""
    v = [0.0] * DIM
    for w in re.findall(r"\w{3,}", text.lower()):
        v[int(hashlib.md5(w.encode()).hexdigest(), 16) % DIM] += 1.0
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


@pytest.fixture
def providers(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "embed_provider", "gemini")
    monkeypatch.setattr(s, "embed_model", "fake-embed")
    monkeypatch.setattr(s, "embed_dim", DIM)
    monkeypatch.setattr(s, "gemini_api_key", "k")
    monkeypatch.setattr(s, "llm_providers", "gemini")
    monkeypatch.setattr(s, "ai_cache", False)
    asks = []

    def embed_handler(request):
        body = json.loads(request.content)
        # Like Gemini: no `index` field, results in input order.
        data = [{"embedding": fake_vector(t)} for t in body["input"]]
        return httpx.Response(200, json={"data": data})

    def chat_handler(request):
        asks.append(json.loads(request.content))
        chunks = [
            {"choices": [{"delta": {"content": c}}]} for c in ["Le prix est stable [1].", " Fin."]
        ]
        body = "".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n"
        return httpx.Response(200, content=body.encode())

    monkeypatch.setattr(embed, "_transport", httpx.MockTransport(embed_handler))
    monkeypatch.setattr(ai, "_transport", httpx.MockTransport(chat_handler))
    return asks


def _drain():
    while asyncio.run(queue.run_once()):
        pass


DOCS = {
    "Relevé INSTAT": "Le prix du riz local est resté stable à Antananarivo en octobre, autour de 3 200 ariary le kilo.",
    "Météo": "Le cyclone tropical devrait toucher la côte est près de Toamasina jeudi soir.",
    "JIRAMA": "La JIRAMA annonce des délestages de quatre heures par jour dans la capitale.",
}


def _seed(alice, ws):
    for title, text in DOCS.items():
        alice.post(f"/api/v1/workspaces/{ws}/sources", json={"title": title, "text": text})
    _drain()


def test_text_sources_are_indexed_and_searchable(as_user, providers):
    alice = as_user("alice")
    ws = _workspace(alice)
    _seed(alice, ws)
    r = alice.post(
        f"/api/v1/workspaces/{ws}/search", json={"query": "prix du riz à Antananarivo", "k": 2}
    )
    assert r.status_code == 200, r.text
    hits = r.json()
    assert hits[0]["title"] == "Relevé INSTAT"
    assert hits[0]["score"] > hits[1]["score"]
    assert [h["n"] for h in hits] == [1, 2]


def test_search_is_workspace_scoped(as_user, providers):
    alice, mallory = as_user("alice"), as_user("mallory")
    ws = _workspace(alice)
    _seed(alice, ws)
    ws_m = _workspace(mallory, "Other")
    assert (
        mallory.post(f"/api/v1/workspaces/{ws_m}/search", json={"query": "prix du riz"}).json()
        == []
    )
    assert (
        mallory.post(f"/api/v1/workspaces/{ws}/search", json={"query": "prix du riz"}).status_code
        == 404
    )


def test_ask_streams_citations_then_answer(as_user, providers):
    asks = providers
    alice = as_user("alice")
    ws = _workspace(alice)
    _seed(alice, ws)
    r = alice.post(
        f"/api/v1/workspaces/{ws}/ask", json={"question": "Le prix du riz a-t-il doublé ?", "k": 2}
    )
    assert r.headers["content-type"].startswith("text/event-stream")
    events = [
        line.removeprefix("event: ") for line in r.text.splitlines() if line.startswith("event:")
    ]
    assert events == ["citations", "delta", "delta", "done"]
    citations = json.loads(
        next(line for line in r.text.splitlines() if line.startswith("data: [")).removeprefix(
            "data: "
        )
    )
    assert citations[0]["title"] == "Relevé INSTAT"
    # The model only saw the numbered passages.
    assert "[1] Relevé INSTAT" in asks[0]["messages"][1]["content"]


def test_without_embedding_key_search_says_so(as_user, monkeypatch):
    monkeypatch.setattr(get_settings(), "embed_provider", "gemini")
    monkeypatch.setattr(get_settings(), "gemini_api_key", "")
    alice = as_user("alice")
    ws = _workspace(alice)
    r = alice.post(f"/api/v1/workspaces/{ws}/search", json={"query": "riz"})
    assert (r.status_code, r.json()["error"]["code"]) == (503, "embeddings_unavailable")


def test_deleting_a_source_removes_its_passages(as_user, providers):
    alice = as_user("alice")
    ws = _workspace(alice)
    _seed(alice, ws)
    src = alice.get(f"/api/v1/workspaces/{ws}/sources").json()
    for s in src:
        alice.delete(f"/api/v1/workspaces/{ws}/sources/{s['id']}")
    assert alice.post(f"/api/v1/workspaces/{ws}/search", json={"query": "prix du riz"}).json() == []


def test_split_text_keeps_chunks_bounded_and_overlapping():
    text = "\n\n".join(f"Paragraphe {i}. " + "mot " * 150 for i in range(20))
    chunks = split_text(text)
    assert len(chunks) > 3
    assert all(len(c) <= 2400 + 400 for c in chunks)
    long_one = "Phrase. " * 1000
    assert all(len(c) <= 2400 for c in split_text(long_one))


def test_split_segments_keeps_times():
    segs = [{"start": i * 2.0, "end": i * 2.0 + 2, "text": "mot " * 100} for i in range(20)]
    parts = split_segments(segs)
    assert parts[0][1] == 0.0 and parts[-1][2] == 40.0
    assert all(len(t) <= 2400 for t, _, _ in parts)
