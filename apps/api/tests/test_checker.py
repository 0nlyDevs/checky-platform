import asyncio
import json

import httpx
import pytest

from app.core import ai
from app.core.config import get_settings
from app.workers import queue
from tests.test_workspaces import _workspace

ARTICLE = (
    "Selon le dernier relevé de l'INSTAT, le prix du riz local est resté stable à Antananarivo "
    "entre septembre et octobre, autour de 3 200 ariary le kilo."
)


@pytest.fixture
def model(monkeypatch):
    """The AI answers with whatever JSON the test puts in `answer`."""
    s = get_settings()
    monkeypatch.setattr(s, "llm_providers", "groq")
    monkeypatch.setattr(s, "groq_api_key", "k")
    monkeypatch.setattr(s, "ai_cache", False)
    answer: dict = {}
    seen: list[dict] = []

    def handler(request):
        seen.append(json.loads(request.content))
        msg = {"role": "assistant", "content": "```json\n" + json.dumps(answer["json"]) + "\n```"}
        return httpx.Response(200, json={"model": "m", "choices": [{"message": msg}]})

    monkeypatch.setattr(ai, "_transport", httpx.MockTransport(handler))
    return answer, seen


def _claim_with_source(alice, ws):
    item = alice.post(
        f"/api/v1/workspaces/{ws}/items",
        json={"title": "Le prix du riz a doublé à Antananarivo depuis septembre"},
    ).json()["id"]
    alice.post(
        f"/api/v1/workspaces/{ws}/sources",
        json={"text": ARTICLE, "title": "Relevé INSTAT", "item_id": item},
    )
    return item


def test_analysis_keeps_verbatim_quotes_and_suggests(as_user, model):
    answer, seen = model
    answer["json"] = {
        "claims": [{"text": "Le prix du riz a doublé", "what": "prix du riz", "figure": "x2"}],
        "evidence": [
            {
                "source": 1,
                "stance": "contradicts",
                "quote": "le prix du riz local est resté stable à Antananarivo",
                "explanation": "L'INSTAT relève un prix stable.",
            },
            {"source": 1, "stance": "supports", "quote": "le prix a doublé selon l'INSTAT"},
            {"source": 7, "stance": "supports", "quote": "inventé"},
        ],
        "verdict": "false",
        "reason": "L'INSTAT relève un prix stable, pas un doublement.",
        "missing": "",
    }
    alice = as_user("alice")
    ws = _workspace(alice)
    item = _claim_with_source(alice, ws)
    job = alice.post(f"/api/v1/workspaces/{ws}/items/{item}/analyze")
    assert job.status_code == 202
    assert asyncio.run(queue.run_once()) is True

    data = alice.get(f"/api/v1/workspaces/{ws}/items/{item}").json()["data"]
    assert data["verdict_suggested"] == "false"
    a = data["analysis"]
    assert [e["quote"] for e in a["evidence"]] == [
        "le prix du riz local est resté stable à Antananarivo"
    ]
    assert (a["evidence"][0]["stance"], a["evidence"][0]["source_title"]) == (
        "contradicts",
        "Relevé INSTAT",
    )
    assert a["dropped_quotes"] == 2
    assert a["sources_used"] == 1 and a["claims"][0]["figure"] == "x2"
    # The source text reached the model, and JSON mode was asked for.
    assert "3 200 ariary" in seen[0]["messages"][1]["content"]
    assert seen[0]["response_format"] == {"type": "json_object"}
    history = alice.get(f"/api/v1/workspaces/{ws}/activity?entity_id={item}").json()
    assert history[0]["action"] == "analysis"
    # The journalist's confirmed verdict is untouched.
    assert data.get("verdict") is None


def test_no_backed_evidence_means_unverifiable(as_user, model):
    answer, _ = model
    answer["json"] = {"evidence": [], "verdict": "true", "reason": "Plausible."}
    alice = as_user("alice")
    ws = _workspace(alice)
    item = alice.post(f"/api/v1/workspaces/{ws}/items", json={"title": "Une rumeur"}).json()["id"]
    alice.post(f"/api/v1/workspaces/{ws}/items/{item}/analyze")
    asyncio.run(queue.run_once())
    data = alice.get(f"/api/v1/workspaces/{ws}/items/{item}").json()["data"]
    assert data["verdict_suggested"] == "unverifiable"
    assert data["analysis"]["sources_used"] == 0


def test_analysis_fails_cleanly_when_ai_is_down(as_user, monkeypatch):
    monkeypatch.setattr(get_settings(), "llm_providers", "groq")
    monkeypatch.setattr(get_settings(), "groq_api_key", "")
    alice = as_user("alice")
    ws = _workspace(alice)
    item = alice.post(f"/api/v1/workspaces/{ws}/items", json={"title": "x"}).json()["id"]
    job = alice.post(f"/api/v1/workspaces/{ws}/items/{item}/analyze").json()
    asyncio.run(queue.run_once())
    assert alice.get(f"/api/v1/workspaces/{ws}/jobs/{job['id']}").json()["status"] == "failed"
    assert (
        "verdict_suggested" not in alice.get(f"/api/v1/workspaces/{ws}/items/{item}").json()["data"]
    )


def test_outsiders_cannot_analyze(as_user, model):
    ws = _workspace(as_user("alice"))
    item = as_user("alice").post(f"/api/v1/workspaces/{ws}/items", json={"title": "x"}).json()["id"]
    ws_m = _workspace(as_user("mallory"), "Other")
    assert (
        as_user("mallory").post(f"/api/v1/workspaces/{ws_m}/items/{item}/analyze").status_code
        == 404
    )
