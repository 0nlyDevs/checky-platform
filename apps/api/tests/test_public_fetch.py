import asyncio
from contextlib import asynccontextmanager

import httpx
import pytest

from app.workers import ingest


def test_real_transport_pins_the_checked_ip_and_preserves_host_and_tls_name(monkeypatch):
    seen, resolutions = [], []

    def resolve(host):
        resolutions.append(host)
        return ["93.184.216.34"] if len(resolutions) == 1 else ["127.0.0.1"]

    class Client:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        @asynccontextmanager
        async def stream(self, method, url, **kwargs):
            seen.append((url, kwargs))
            yield httpx.Response(200, text="public page", request=httpx.Request(method, url))

    monkeypatch.setattr(ingest, "_transport", None)
    monkeypatch.setattr(ingest, "_resolve", resolve)
    monkeypatch.setattr(ingest.httpx, "AsyncClient", Client)
    final, _, raw, _ = asyncio.run(ingest.fetch_raw("https://news.example:8443/story"))
    assert resolutions == ["news.example"]
    assert seen[0][0].host == "93.184.216.34" and seen[0][0].port == 8443
    assert seen[0][1]["headers"]["Host"] == "news.example:8443"
    assert seen[0][1]["extensions"]["sni_hostname"] == "news.example"
    assert final == "https://news.example:8443/story" and raw == b"public page"


@pytest.mark.parametrize("addresses", [[], ["127.0.0.1"], ["93.184.216.34", "10.0.0.1"]])
def test_empty_private_and_mixed_dns_answers_are_rejected(monkeypatch, addresses):
    monkeypatch.setattr(ingest, "_resolve", lambda _: addresses)
    with pytest.raises(ValueError):
        asyncio.run(ingest.check_public_url("https://news.example/a"))
