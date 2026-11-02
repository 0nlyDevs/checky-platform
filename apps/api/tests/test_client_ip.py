"""Rate limits key on an address the caller cannot choose (X-Forwarded-For spoofing, 2 Nov)."""

import pytest

from app.core.config import get_settings
from app.modules import public

ASK = "/api/v1/public/ask"
QUESTION = {"question": "zzqx aucune correspondance 7781"}


def _ask(client, **headers):
    return client.post(ASK, json=QUESTION, headers=headers).status_code


@pytest.fixture
def behind_cloudflare(monkeypatch):
    monkeypatch.setattr(get_settings(), "client_ip_header", "cf-connecting-ip")


def test_a_forged_forwarded_for_does_not_reset_the_limit(client, behind_cloudflare):
    for _ in range(public.ASK_LIMIT):
        assert _ask(client, **{"cf-connecting-ip": "198.51.100.1"}) == 200
    for fake in ("203.0.113.7", "203.0.113.8"):
        assert _ask(client, **{"cf-connecting-ip": "198.51.100.1", "x-forwarded-for": fake}) == 429


def test_each_visitor_keeps_their_own_budget(client, behind_cloudflare):
    for _ in range(public.ASK_LIMIT):
        _ask(client, **{"cf-connecting-ip": "198.51.100.1"})
    assert _ask(client, **{"cf-connecting-ip": "198.51.100.1"}) == 429
    assert _ask(client, **{"cf-connecting-ip": "198.51.100.2"}) == 200


def test_without_the_header_the_last_forwarded_entry_counts_never_the_first(
    client, behind_cloudflare
):
    real = "192.0.2.10"
    for i in range(public.ASK_LIMIT):
        assert _ask(client, **{"x-forwarded-for": f"203.0.113.{i}, {real}"}) == 200
    assert _ask(client, **{"x-forwarded-for": f"203.0.113.99, {real}"}) == 429
    # A garbage header value is ignored rather than becoming a fresh bucket.
    assert _ask(client, **{"cf-connecting-ip": "not-an-ip", "x-forwarded-for": real}) == 429


def test_render_uses_cloudflare_header_by_default(client, monkeypatch):
    monkeypatch.setenv("RENDER", "true")
    for _ in range(public.ASK_LIMIT):
        _ask(client, **{"cf-connecting-ip": "198.51.100.3"})
    assert _ask(client, **{"cf-connecting-ip": "198.51.100.3", "x-forwarded-for": "1.2.3.4"}) == 429


def test_locally_headers_are_ignored(client, monkeypatch):
    monkeypatch.delenv("RENDER", raising=False)
    for _ in range(public.ASK_LIMIT):
        _ask(client, **{"cf-connecting-ip": "198.51.100.4"})
    # No trusted header configured: a caller-supplied header cannot open a new bucket.
    assert _ask(client, **{"cf-connecting-ip": "198.51.100.5"}) == 429
