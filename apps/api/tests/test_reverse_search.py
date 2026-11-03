"""The reverse image search Checky runs itself: the earliest dated page showing a picture."""

import asyncio
import json

import httpx

from app.core import reverse_search
from app.core.config import get_settings
from app.modules import crew
from app.workers import ingest

PAGES = {
    "https://tvm.test/video": '<meta property="article:published_time" content="2023-03-14T08:00:00Z">',
    "https://blog.test/post": '<script type="application/ld+json">{"datePublished":"2024-06-02"}</script>',
    "https://undated.test/p": "<p>pas de date</p>",
}


def _provider(monkeypatch, sent):
    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(dict(request.url.params))
        return httpx.Response(
            200,
            json={
                "visual_matches": [
                    {"link": url, "title": f"Page {i}"} for i, url in enumerate(PAGES)
                ]
                + [{"link": "ftp://nope"}, {"title": "no link"}]
            },
        )

    async def fetch_raw(url):
        return url, "text/html; charset=utf-8", PAGES[url].encode(), "utf-8"

    monkeypatch.setattr(reverse_search, "_transport", httpx.MockTransport(handler))
    monkeypatch.setattr(ingest, "fetch_raw", fetch_raw)
    monkeypatch.setattr(get_settings(), "serpapi_api_key", "k1,k2")
    reverse_search._cache.clear()
    reverse_search._spent.clear()


def test_the_earliest_dated_page_is_found_and_cached(monkeypatch):
    sent: list[dict] = []
    _provider(monkeypatch, sent)
    found = asyncio.run(reverse_search.earliest("https://s3.test/b/blurred.jpg?X-Sig=1"))
    assert found["first"] == {
        "date": "2023-03-14",
        "host": "tvm.test",
        "url": "https://tvm.test/video",
        "title": "Page 0",
    }
    assert found["matches"] == 3 and found["dated"] == 2
    assert sent[0]["engine"] == "google_lens" and sent[0]["api_key"] in ("k1", "k2")
    # Same picture, new signature in the URL: answered from memory.
    asyncio.run(reverse_search.earliest("https://s3.test/b/blurred.jpg?X-Sig=2"))
    assert len(sent) == 1


def test_without_a_key_nothing_is_asked(monkeypatch):
    sent: list[dict] = []
    _provider(monkeypatch, sent)
    monkeypatch.setattr(get_settings(), "serpapi_api_key", "")
    assert asyncio.run(reverse_search.earliest("https://s3.test/a.jpg")) is None and not sent


def test_a_refused_key_moves_to_the_next_and_a_dead_provider_gives_nothing(monkeypatch):
    sent: list[dict] = []
    _provider(monkeypatch, sent)
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.params["api_key"])
        if len(seen) == 1:
            return httpx.Response(429)
        return httpx.Response(200, json={"visual_matches": []})

    monkeypatch.setattr(reverse_search, "_transport", httpx.MockTransport(handler))
    found = asyncio.run(reverse_search.earliest("https://s3.test/c.jpg"))
    assert (
        len(seen) == 2 and seen[0] != seen[1] and found == {"first": None, "matches": 0, "dated": 0}
    )
    monkeypatch.setattr(
        reverse_search, "_transport", httpx.MockTransport(lambda r: httpx.Response(500))
    )
    assert asyncio.run(reverse_search.earliest("https://s3.test/d.jpg")) is None


def test_provenance_uses_the_earliest_page_for_the_old_picture_flag(monkeypatch):
    _provider(monkeypatch, [])
    page = {
        "kind": "image",
        "final_url": "https://s3.test/e.jpg",
        "image_url": "https://s3.test/e.jpg",
        "image": {"ai_markers": []},
    }
    found = asyncio.run(crew.provenance_of(page, "Ce soir tout Tana est dans le noir"))
    assert found["first_seen"] == "2023-03-14" and found["first_seen_basis"] == "reverse"
    assert found["first_page"]["host"] == "tvm.test"
    assert found["verdict_hint"] == "old_media_new_caption"
    json.dumps(found)
