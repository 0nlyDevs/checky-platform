import json

import httpx
import pytest

from app.core import ai
from app.core.config import get_settings
from tests.test_workspaces import _workspace


@pytest.fixture
def model(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "llm_providers", "groq")
    monkeypatch.setattr(s, "groq_api_key", "k")
    monkeypatch.setattr(s, "ai_cache", False)
    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        msg = {"role": "assistant", "content": " FAUX : l'INSTAT relève un prix stable. "}
        return httpx.Response(200, json={"model": "m", "choices": [{"message": msg}]})

    monkeypatch.setattr(ai, "_transport", httpx.MockTransport(handler))
    return seen


def test_post_needs_a_confirmed_verdict_and_is_kept(as_user, model):
    alice = as_user("alice")
    ws = _workspace(alice)
    item = alice.post(f"/api/v1/workspaces/{ws}/items", json={"title": "Le riz a doublé"}).json()[
        "id"
    ]
    url = f"/api/v1/workspaces/{ws}/items/{item}/post"
    assert alice.post(url, json={"language": "fr"}).status_code == 409
    alice.patch(f"/api/v1/workspaces/{ws}/items/{item}", json={"data": {"verdict": "false"}})
    alice.post(
        f"/api/v1/workspaces/{ws}/sources",
        json={"text": "Relevé", "title": "Relevé INSTAT", "item_id": item},
    )
    r = alice.post(url, json={"language": "mg"})
    assert r.status_code == 200
    assert r.json() == {"language": "mg", "text": "FAUX : l'INSTAT relève un prix stable."}
    facts = model[0]["messages"][1]["content"]
    assert "DISO" in facts and "Relevé INSTAT" in facts and "malgache" in facts
    data = alice.get(f"/api/v1/workspaces/{ws}/items/{item}").json()["data"]
    assert data["posts"]["mg"].startswith("FAUX")
    assert alice.post(url, json={"language": "en"}).status_code == 422
