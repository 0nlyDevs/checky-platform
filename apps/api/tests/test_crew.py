import json
from types import SimpleNamespace

import pytest

from app.core import ai, evidence_search
from app.modules import linkcheck
from tests.test_agent import _events
from tests.test_workspaces import _workspace


@pytest.fixture
def research(monkeypatch):
    async def search(plan, skip=None):
        return evidence_search.SearchReport(
            status="ok",
            attempts=[],
            sources=[
                evidence_search.ResearchSource(
                    n=1,
                    kind="web",
                    title="Annonce du port",
                    url="https://example.org/port",
                    snippet="Le port de Rio est ouvert.",
                    date="2026-01-01",
                )
            ],
        )

    async def read(sources, plan, text):
        for s in sources:
            s.read_status = "read"
            s.passages = ["Le port de Rio est ouvert."]

    monkeypatch.setattr(evidence_search, "search", search)
    monkeypatch.setattr(evidence_search, "read_sources", read)
    linkcheck._CHECKS.clear()


def test_no_ai_runs_research_and_private_archives_but_never_synthesises(
    as_user, monkeypatch, research
):
    async def forbidden(*args, **kwargs):
        raise AssertionError("No model call allowed")

    monkeypatch.setattr(ai, "complete", forbidden)
    alice, bob = as_user("alice"), as_user("bob")
    ws, other = _workspace(alice), _workspace(bob)
    for c, w, title in [(alice, ws, "Our archive"), (bob, other, "Secret archive")]:
        c.post(
            f"/api/v1/workspaces/{w}/sources",
            json={"title": title, "text": "Le port de Rio est ouvert selon le service maritime."},
        )
    events = _events(
        alice.post(
            f"/api/v1/workspaces/{ws}/crew",
            json={"text": "Le port de Rio est fermé.", "ai_enabled": False},
        ).text
    )
    assert events[-1][0] == "done"
    result = next(d for e, d in events if e == "result")
    assert "analysis" not in result
    assert result["results"] and result["audit"]["score"] > 0
    assert [r["title"] for r in result["archives"]] == ["Our archive"]
    assert all(a["status"] == "no_ai" for a in result["trace"] if a["llm"])
    assert bob.post(f"/api/v1/workspaces/{ws}/crew", json={"text": "hello"}).status_code == 404


def test_model_failure_keeps_retrieval_visible(as_user, monkeypatch, research):
    async def unavailable(*args, **kwargs):
        raise ai.AiUnavailable("Offline")

    monkeypatch.setattr(ai, "complete", unavailable)
    alice = as_user("alice")
    ws = _workspace(alice)
    result = next(
        d
        for e, d in _events(
            alice.post(
                f"/api/v1/workspaces/{ws}/crew", json={"text": "Le port de Rio est fermé."}
            ).text
        )
        if e == "result"
    )
    assert result["results"][0]["read_status"] == "read"
    assert result["audit"]["score"] > 0 and "analysis" not in result
    assert any(a["status"] == "failed" for a in result["trace"])


def test_synthesis_citations_and_critic_are_bound_to_read_passages(as_user, monkeypatch, research):
    async def complete(messages, **kwargs):
        system = messages[0]["content"]
        if system.startswith("Tu prépares"):
            data = {
                "summary": "Le port de Rio est fermé.",
                "claims": ["Le port de Rio est fermé."],
                "entities": ["Rio"],
                "queries": ["port Rio fermé"],
            }
        elif system.startswith("Analyse le cadrage"):
            data = {"signals": []}
        elif system.startswith("Tu proposes"):
            data = {
                "verdict": "false",
                "reason": "Le port est annoncé ouvert.",
                "evidence": [
                    {"result": 1, "stance": "contradicts", "quote": "Le port de Rio est ouvert."},
                    {"result": 99, "stance": "supports", "quote": "Invented"},
                ],
                "missing": "Date de la fermeture alléguée.",
            }
        else:
            data = {"concerns": [{"result": 1, "quote": "Invented concern", "why": "fabricated"}]}
        return SimpleNamespace(content=json.dumps(data), model="test-model")

    monkeypatch.setattr(ai, "complete", complete)
    alice = as_user("alice")
    ws = _workspace(alice)
    result = next(
        d
        for e, d in _events(
            alice.post(
                f"/api/v1/workspaces/{ws}/crew", json={"text": "Le port de Rio est fermé."}
            ).text
        )
        if e == "result"
    )
    assert result["analysis"]["verdict"] == "false"
    assert len(result["analysis"]["evidence"]) == 1
    assert result["critique"] == []
    assert alice.get(f"/api/v1/workspaces/{ws}/items").json()["total"] == 0
