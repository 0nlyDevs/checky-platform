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


@pytest.fixture
def embeddings(monkeypatch):
    """Embeddings on, answered by the bag-of-words fake: texts sharing words are close."""
    from app.core import embed
    from tests.test_rag import fake_vector

    s = get_settings()
    monkeypatch.setattr(s, "embed_provider", "gemini")
    monkeypatch.setattr(s, "embed_model", "fake-embed")
    monkeypatch.setattr(s, "embed_dim", 768)
    monkeypatch.setattr(s, "gemini_api_key", "k")

    def embed_handler(request):
        body = json.loads(request.content)
        return httpx.Response(
            200, json={"data": [{"embedding": fake_vector(t)} for t in body["input"]]}
        )

    monkeypatch.setattr(embed, "_transport", httpx.MockTransport(embed_handler))


def test_long_sources_send_their_relevant_passage_not_just_the_start(as_user, model, embeddings):
    answer, seen = model
    answer["json"] = {"evidence": [], "verdict": "unverifiable", "reason": "x"}
    alice = as_user("alice")
    ws = _workspace(alice)
    item = alice.post(
        f"/api/v1/workspaces/{ws}/items", json={"title": "Le pont de Mangasoavina est fermé"}
    ).json()["id"]
    filler = "\n\n".join(
        f"Paragraphe {i} sur la météo et les cultures de la région." for i in range(200)
    )
    text = filler + "\n\nLe pont de Mangasoavina reste ouvert aux véhicules légers jusqu'à lundi."
    alice.post(
        f"/api/v1/workspaces/{ws}/sources",
        json={"title": "Bulletin", "text": text, "item_id": item},
    )
    while asyncio.run(queue.run_once()):  # indexing
        pass
    alice.post(f"/api/v1/workspaces/{ws}/items/{item}/analyze")
    asyncio.run(queue.run_once())
    prompt = seen[-1]["messages"][1]["content"]
    assert "reste ouvert aux véhicules légers" in prompt
    assert len(prompt) < 16_000


def test_reads_the_newsrooms_other_sources_about_the_claim(as_user, model, embeddings):
    answer, seen = model
    alice = as_user("alice")
    ws = _workspace(alice)

    def claim(title):
        return alice.post(f"/api/v1/workspaces/{ws}/items", json={"title": title}).json()["id"]

    item, other, unrelated = (
        claim("Le pont de Mangasoavina est fermé"),
        claim("Pont de Mangasoavina : la rumeur de fermeture"),
        claim("Le prix du riz a doublé"),
    )
    quote = "Non, le pont de Mangasoavina reste ouvert."
    alice.post(
        f"/api/v1/workspaces/{ws}/sources",
        json={
            "title": "Communiqué",
            "text": f"Le pont de Mangasoavina est fermé ? {quote}",
            "item_id": other,
        },
    )
    alice.post(
        f"/api/v1/workspaces/{ws}/sources",
        json={"title": "Relevé INSTAT", "text": ARTICLE, "item_id": unrelated},
    )
    while asyncio.run(queue.run_once()):  # indexing
        pass
    answer["json"] = {
        "evidence": [{"source": 1, "stance": "contradicts", "quote": quote}],
        "verdict": "false",
        "reason": "Le communiqué dit que le pont reste ouvert.",
    }
    alice.post(f"/api/v1/workspaces/{ws}/items/{item}/analyze")
    asyncio.run(queue.run_once())

    prompt = seen[-1]["messages"][1]["content"]
    assert "[1] Communiqué · autre dossier de la rédaction" in prompt
    assert "INSTAT" not in prompt
    data = alice.get(f"/api/v1/workspaces/{ws}/items/{item}").json()["data"]
    assert data["verdict_suggested"] == "false"
    [e] = data["analysis"]["evidence"]
    assert (e["attached"], e["item_id"]) == (False, other)
    assert (data["analysis"]["sources_used"], data["analysis"]["related_used"]) == (0, 1)


def _dated_claim(alice, ws, published_at):
    item = alice.post(
        f"/api/v1/workspaces/{ws}/items",
        json={"title": "Le pont de Mangasoavina est fermé ce matin"},
    ).json()["id"]
    alice.post(
        f"/api/v1/workspaces/{ws}/sources",
        json={
            "title": "Bulletin",
            "text": "Le pont de Mangasoavina est fermé pour travaux.",
            "item_id": item,
            "published_at": published_at,
        },
    )
    return item


SUPPORTED = {
    "evidence": [{"source": 1, "stance": "supports", "quote": "Le pont de Mangasoavina est fermé"}],
    "verdict": "true",
    "reason": "Le bulletin dit que le pont est fermé.",
}


def test_the_prompt_carries_today_and_each_sources_age(as_user, model):
    from app.core import dates

    answer, seen = model
    answer["json"] = SUPPORTED
    alice = as_user("alice")
    ws = _workspace(alice)
    item = _dated_claim(alice, ws, "2019-01-14")
    alice.post(f"/api/v1/workspaces/{ws}/items/{item}/analyze")
    asyncio.run(queue.run_once())
    prompt = seen[-1]["messages"][1]["content"]
    assert f"Aujourd'hui : {dates.fr(dates.today())}" in prompt
    assert "Rumeur vue pour la première fois le" in prompt
    assert "[1] Bulletin · publiée le 14 janvier 2019, " in prompt
    assert " ans avant la rumeur" in prompt


def test_an_old_source_cannot_make_a_recent_claim_true(as_user, model):
    answer, _ = model
    answer["json"] = SUPPORTED
    alice = as_user("alice")
    ws = _workspace(alice)
    item = _dated_claim(alice, ws, "2019-01-14")
    alice.post(f"/api/v1/workspaces/{ws}/items/{item}/analyze")
    asyncio.run(queue.run_once())
    data = alice.get(f"/api/v1/workspaces/{ws}/items/{item}").json()["data"]
    assert data["verdict_suggested"] == "unverifiable"
    assert data["analysis"]["date_check"] == "downgraded"
    [e] = data["analysis"]["evidence"]
    assert (e["source_date"], e["date_basis"]) == ("2019-01-14", "published")
    assert e["days_before"] > 2000


def test_a_source_from_the_day_keeps_its_verdict(as_user, model):
    from app.core import dates

    answer, _ = model
    answer["json"] = SUPPORTED
    alice = as_user("alice")
    ws = _workspace(alice)
    item = _dated_claim(alice, ws, dates.today().isoformat())
    alice.post(f"/api/v1/workspaces/{ws}/items/{item}/analyze")
    asyncio.run(queue.run_once())
    data = alice.get(f"/api/v1/workspaces/{ws}/items/{item}").json()["data"]
    assert data["verdict_suggested"] == "true"
    assert data["analysis"]["date_check"] is None
    assert data["analysis"]["evidence"][0]["days_before"] in (0, 1)
