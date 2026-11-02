import asyncio
import json

import httpx
import pytest

from app.core import ai
from app.core.config import get_settings
from app.modules.quotes import locate
from app.workers import queue
from tests.test_sources import (  # noqa: F401 - fixture
    _upload,
    fake_storage,
    whisper,
)
from tests.test_workspaces import _workspace

SEGMENTS = [
    {"start": 0.0, "end": 3.0, "text": "Bonjour, je suis maire de la commune."},
    {"start": 3.0, "end": 8.5, "text": "Nous avons construit trois écoles cette année,"},
    {"start": 8.5, "end": 12.0, "text": "et le budget a doublé depuis 2024."},
]


def test_locate_finds_the_starting_segment():
    assert locate("trois écoles cette année, et le budget", SEGMENTS) == 3.0
    assert locate("Le budget a DOUBLÉ depuis 2024", SEGMENTS) == 8.5
    assert locate("une phrase jamais dite", SEGMENTS) is None


@pytest.fixture
def model(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "llm_providers", "groq")
    monkeypatch.setattr(s, "ai_cache", False)
    answer = {}

    def handler(request):
        if request.url.path.endswith("/audio/transcriptions"):
            body = {
                "text": " ".join(g["text"] for g in SEGMENTS),
                "language": "french",
                "duration": 12.0,
                "segments": SEGMENTS,
            }
            return httpx.Response(200, json=body)
        msg = {"role": "assistant", "content": json.dumps(answer["json"])}
        return httpx.Response(200, json={"model": "m", "choices": [{"message": msg}]})

    from app.core import stt

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(ai, "_transport", transport)
    monkeypatch.setattr(stt, "_transport", transport)
    return answer


def test_quotes_are_checked_against_the_transcript(as_user, whisper, model):  # noqa: F811
    model["json"] = {
        "quotes": [
            {"text": "« le budget a doublé depuis 2024 »"},
            {"text": "Nous avons tout réussi."},
        ],
        "claims": [
            {
                "text": "Trois écoles ont été construites en 2026.",
                "from": "Nous avons construit trois écoles",
            }
        ],
    }
    alice = as_user("alice")
    ws = _workspace(alice)
    src = _upload(alice, ws, "maire.m4a", "audio/mp4", b"fake").json()
    asyncio.run(queue.run_once())
    r = alice.post(f"/api/v1/workspaces/{ws}/sources/{src['id']}/quotes")
    assert r.status_code == 202
    asyncio.run(queue.run_once())
    h = alice.get(f"/api/v1/workspaces/{ws}/sources/{src['id']}/transcript").json()["highlights"]
    assert h["quotes"] == [{"text": "le budget a doublé depuis 2024", "start": 8.5}]
    assert h["dropped_quotes"] == 1
    assert h["claims"] == [{"text": "Trois écoles ont été construites en 2026.", "start": 3.0}]


def test_quotes_need_a_transcript(as_user):
    alice = as_user("alice")
    ws = _workspace(alice)
    src = alice.post(f"/api/v1/workspaces/{ws}/sources", json={"text": "x"}).json()
    assert alice.post(f"/api/v1/workspaces/{ws}/sources/{src['id']}/quotes").status_code == 409
