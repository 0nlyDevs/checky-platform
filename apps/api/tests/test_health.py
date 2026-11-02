import httpx
import pytest

from app.core import ai, storage
from app.core.config import get_settings
from app.modules import health


@pytest.fixture(autouse=True)
def _setup(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(health, "_cache", None)
    monkeypatch.setattr(s, "llm_providers", "groq,gemini,nvidia")
    for name in ("groq", "gemini", "nvidia"):
        monkeypatch.setattr(s, f"{name}_api_key", "")
    monkeypatch.setattr(s, "storage_endpoint", "")
    monkeypatch.setattr(s, "storage_access_key_id", "")
    monkeypatch.setattr(s, "storage_secret_access_key", "")


def _route(monkeypatch, module, handler):
    monkeypatch.setattr(module, "_transport", httpx.MockTransport(handler))


def test_nothing_configured_is_ok_with_database_up(client):
    body = client.get("/api/v1/health").json()
    assert body["ok"] is True
    assert body["checks"]["database"]["status"] == "up"
    assert body["checks"]["storage"]["status"] == "not_configured"
    assert {k: v["status"] for k, v in body["ai"].items()} == {
        "groq": "not_configured",
        "gemini": "not_configured",
        "nvidia": "not_configured",
    }


def test_providers_are_checked_without_spending_tokens(client, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "groq_api_key", "g")
    monkeypatch.setattr(s, "gemini_api_key", "m")
    seen = []

    def handler(request):
        seen.append((request.method, request.url.path))
        if "groq" in request.url.host:
            return httpx.Response(401)
        return httpx.Response(200, json={"data": []})

    _route(monkeypatch, ai, handler)
    body = client.get("/api/v1/health").json()
    assert body["ai"]["groq"] == {
        "status": "down",
        "latency_ms": body["ai"]["groq"]["latency_ms"],
        "detail": "HTTP 401",
        "model": "openai/gpt-oss-120b",
    }
    assert body["ai"]["gemini"]["status"] == "up"
    assert body["ai"]["nvidia"]["status"] == "not_configured"
    # One provider up is enough to serve AI calls through the fallback.
    assert body["ok"] is True
    assert all(method == "GET" and path.endswith("/models") for method, path in seen)


def test_all_configured_providers_down_is_not_ok(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "groq_api_key", "g")
    _route(monkeypatch, ai, lambda r: httpx.Response(503))
    body = client.get("/api/v1/health").json()
    assert (body["ok"], body["ai"]["groq"]["status"]) == (False, "down")


class _FakeS3:
    def __init__(self, error: Exception | None = None):
        self.error, self.calls = error, []

    def head_bucket(self, Bucket):
        self.calls.append(Bucket)
        if self.error:
            raise self.error
        return {}


def _storage(monkeypatch, fake):
    s = get_settings()
    monkeypatch.setattr(s, "storage_endpoint", "https://br-x.storage.example.neon.tech")
    monkeypatch.setattr(s, "storage_access_key_id", "nak_test")
    monkeypatch.setattr(s, "storage_secret_access_key", "nsk_test")
    monkeypatch.setattr(s, "storage_bucket", "uploads")
    monkeypatch.setattr(storage, "client", lambda: fake)


def test_storage_checks_the_bucket(client, monkeypatch):
    fake = _FakeS3()
    _storage(monkeypatch, fake)
    body = client.get("/api/v1/health").json()
    assert body["checks"]["storage"]["status"] == "up"
    assert fake.calls == ["uploads"]


def test_storage_down_is_not_ok(client, monkeypatch):
    _storage(monkeypatch, _FakeS3(ConnectionError("no route")))
    body = client.get("/api/v1/health").json()
    assert body["checks"]["storage"] == {
        "status": "down",
        "latency_ms": body["checks"]["storage"]["latency_ms"],
        "detail": "ConnectionError",
        "model": None,
    }
    assert body["ok"] is False


def test_results_are_cached(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "groq_api_key", "g")
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(200, json={"data": []})

    _route(monkeypatch, ai, handler)
    client.get("/api/v1/health")
    client.get("/api/v1/health")
    assert len(calls) == 1
