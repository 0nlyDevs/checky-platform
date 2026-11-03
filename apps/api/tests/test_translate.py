import json

import httpx
import pytest

from app.core import ai
from app.core.config import get_settings
from app.modules import translate
from tests.test_workspaces import _workspace


@pytest.fixture
def model(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "llm_providers", "groq")
    monkeypatch.setattr(s, "groq_api_key", "k")
    monkeypatch.setattr(s, "ai_cache", False)
    monkeypatch.setattr(translate, "_CALLS", translate.defaultdict(translate.deque))
    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        msg = {"role": "assistant", "content": " « Tsy marina io vaovao io. » "}
        return httpx.Response(200, json={"model": "m", "choices": [{"message": msg}]})

    monkeypatch.setattr(ai, "_transport", httpx.MockTransport(handler))
    return seen


def test_translates_to_malagasy_and_asks_for_a_reread(as_user, model):
    alice = as_user("alice")
    ws = _workspace(alice)
    r = alice.post(
        f"/api/v1/workspaces/{ws}/translate",
        json={"text": "Cette nouvelle est fausse.", "to": "mg"},
    )
    assert r.status_code == 200
    assert r.json() == {"text": "Tsy marina io vaovao io.", "to": "mg", "reread_needed": True}
    sent = model[0]["messages"]
    assert "malgache" in sent[0]["content"]
    assert sent[1] == {"role": "user", "content": "Cette nouvelle est fausse."}


def test_french_needs_no_reread(as_user, model):
    alice = as_user("alice")
    ws = _workspace(alice)
    r = alice.post(f"/api/v1/workspaces/{ws}/translate", json={"text": "Tsy marina", "to": "fr"})
    assert r.json()["reread_needed"] is False
    assert "français" in model[0]["messages"][0]["content"]


def test_rejects_outsiders_bad_languages_and_floods(as_user, model, monkeypatch):
    alice, bob = as_user("alice"), as_user("bob")
    ws = _workspace(alice)
    url = f"/api/v1/workspaces/{ws}/translate"
    assert bob.post(url, json={"text": "Bonjour", "to": "mg"}).status_code == 404
    assert alice.post(url, json={"text": "Bonjour", "to": "en"}).status_code == 422
    assert alice.post(url, json={"text": "   ", "to": "mg"}).status_code == 422
    monkeypatch.setattr(translate, "LIMIT", 2)
    monkeypatch.setattr(translate, "_CALLS", translate.defaultdict(translate.deque))
    assert alice.post(url, json={"text": "Bonjour", "to": "mg"}).status_code == 200
    assert alice.post(url, json={"text": "Bonjour", "to": "mg"}).status_code == 200
    r = alice.post(url, json={"text": "Bonjour", "to": "mg"})
    assert r.status_code == 429
    assert r.json()["error"]["code"] == "too_many_translations"


def test_ai_down_is_a_503(as_user, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "llm_providers", "groq")
    monkeypatch.setattr(s, "groq_api_key", "k")
    monkeypatch.setattr(s, "ai_cache", False)
    monkeypatch.setattr(
        ai, "_transport", httpx.MockTransport(lambda r: httpx.Response(401, json={}))
    )
    alice = as_user("alice")
    ws = _workspace(alice)
    r = alice.post(f"/api/v1/workspaces/{ws}/translate", json={"text": "Bonjour", "to": "mg"})
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "ai_unavailable"
