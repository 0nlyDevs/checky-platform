"""Several keys per service: a used-up key gives way to the next one at once, everywhere."""

import asyncio
import json

import httpx
import pytest

from app.core import embed, keys, stt
from app.core.config import get_settings
from app.modules import public
from tests.test_rag import fake_vector


def _by_key(seen, replies):
    """A mock service that answers according to the key it is called with."""

    def handler(request):
        key = request.headers.get("authorization", "").removeprefix(
            "Bearer "
        ) or request.headers.get("xi-api-key")
        seen.append(key)
        return replies[key](request)

    return httpx.MockTransport(handler)


@pytest.fixture(autouse=True)
def _fresh_keys():
    keys._turn.clear()
    keys._cooldown.clear()


def test_rotation_puts_keys_set_aside_last():
    assert keys.split(" a, b ,,c ") == ["a", "b", "c"]
    assert keys.rotation("svc", ["a", "b"]) == ["a", "b"]
    assert keys.rotation("svc", ["a", "b"]) == ["b", "a"]  # in turn
    keys.set_aside("svc", "a", 60)
    assert keys.rotation("svc", ["a", "b"]) == ["b", "a"]
    assert keys.rotation("svc", ["a", "b"]) == ["b", "a"]  # "a" stays last while it cools down


def test_embeddings_move_to_the_next_key_on_a_quota(monkeypatch):
    s = get_settings()
    for k, v in {"embed_provider": "gemini", "embed_model": "e", "embed_dim": 768}.items():
        monkeypatch.setattr(s, k, v)
    monkeypatch.setattr(s, "gemini_api_key", "full,fresh")
    seen = []
    ok = lambda r: httpx.Response(
        200, json={"data": [{"embedding": fake_vector(t)} for t in json.loads(r.content)["input"]]}
    )
    replies = {"full": lambda r: httpx.Response(429), "fresh": ok}
    monkeypatch.setattr(embed, "_transport", _by_key(seen, replies))
    assert len(asyncio.run(embed.embed(["riz", "bac"]))) == 2
    assert seen == ["full", "fresh"]
    asyncio.run(embed.embed(["encore"]))
    assert seen[-1] == "fresh"  # the full key is set aside, not tried again


def test_transcription_moves_to_the_next_key(monkeypatch):
    monkeypatch.setattr(get_settings(), "groq_api_key", "spent,good")
    seen = []
    replies = {
        "spent": lambda r: httpx.Response(429, headers={"retry-after": "40"}),
        "good": lambda r: httpx.Response(200, json={"text": "Bonjour", "segments": []}),
    }
    monkeypatch.setattr(stt, "_transport", _by_key(seen, replies))
    assert asyncio.run(stt.transcribe(b"x", "a.webm", "audio/webm"))["text"] == "Bonjour"
    assert seen == ["spent", "good"]


def test_voice_moves_to_a_key_with_credits(monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import app

    monkeypatch.setattr(get_settings(), "elevenlabs_api_key", "empty,credits")
    seen = []
    replies = {
        "empty": lambda r: httpx.Response(401, json={"detail": {"status": "quota_exceeded"}}),
        "credits": lambda r: httpx.Response(200, content=b"ID3mp3"),
    }
    monkeypatch.setattr(public, "_tts_transport", _by_key(seen, replies))
    r = TestClient(app).post("/api/v1/public/speak", json={"text": "Bonjour"})
    assert r.status_code == 200 and r.content == b"ID3mp3"
    assert seen == ["empty", "credits"]
