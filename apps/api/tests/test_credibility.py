"""« Fiabilité de la source »: signals found, missing or unknown, never a score."""

from datetime import timedelta

import httpx
import pytest

from app.core import credibility, dates
from app.workers import ingest

PAGE = """<html><head>
<meta name="author" content="Rédaction Démo">
<script type="application/ld+json">{"@type": "NewsArticle", "datePublished": "2026-10-30"}</script>
</head><body>
<a href="/qui-sommes-nous">Qui sommes-nous</a> <a href="mailto:redaction@example.mg">Écrire</a>
<a href="/mentions-legales">Mentions légales</a>
<p>Article.</p></body></html>"""


@pytest.fixture
def rdap(monkeypatch):
    calls = []
    registered = (dates.today() - timedelta(days=40)).isoformat()

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if "young.example" in str(request.url):
            events = [{"eventAction": "registration", "eventDate": f"{registered}T00:00:00Z"}]
            return httpx.Response(200, json={"events": events})
        if "old.example" in str(request.url):
            events = [{"eventAction": "registration", "eventDate": "2009-03-12T00:00:00Z"}]
            return httpx.Response(200, json={"events": events})
        return httpx.Response(404)

    monkeypatch.setattr(credibility, "_transport", httpx.MockTransport(handler))
    credibility._rdap_cache.clear()
    return calls


def _by_key(out):
    return {s["key"]: s for s in out["signals"]}


async def test_a_transparent_press_page(rdap):
    out = await credibility.rate(
        "https://www.old.example/article",
        {"kind": "page", "final_url": "https://www.old.example/article", "site": "Old News"},
        html=PAGE,
    )
    signals = _by_key(out)
    assert out["domain"] == "old.example" and out["known"] == "press"
    assert signals["author"] == {"key": "author", "status": "found", "detail": "Rédaction Démo"}
    assert signals["date"]["status"] == "found" and signals["date"]["detail"] == "30 octobre 2026"
    assert signals["about"]["status"] == signals["contact"]["status"] == "found"
    assert signals["legal"]["status"] == "found"
    assert signals["corrections"]["status"] == "missing"  # « non trouvé », not a fault
    assert signals["https"]["status"] == "found"
    assert signals["domain_age"]["detail"].startswith("Domaine enregistré le 12 mars 2009")
    assert "score" not in out


async def test_young_domain_is_said_and_rdap_is_cached(rdap):
    for _ in range(2):
        out = await credibility.rate("http://young.example/x", html="<p>rien</p>")
    signals = _by_key(out)
    assert "domaine récent" in signals["domain_age"]["detail"]
    assert signals["https"]["status"] == "missing"
    assert signals["author"]["status"] == "missing" and out["known"] is None
    assert len(rdap) == 1  # the second check was answered from memory


async def test_unreadable_page_leaves_signals_unknown(rdap, monkeypatch):
    async def down(url):
        raise ValueError("The page answered HTTP 403")

    monkeypatch.setattr(ingest, "fetch_raw", down)
    out = await credibility.rate("https://nowhere.example/a", {"kind": "page"})
    signals = _by_key(out)
    assert signals["author"]["status"] == signals["about"]["status"] == "unknown"
    assert signals["domain_age"]["status"] == "unknown"  # RDAP answered 404


async def test_fact_checker_official_page_and_platform(rdap):
    checker = await credibility.rate("https://factuel.afp.com/doc.afp.com.123", html="")
    assert checker["known"] == "fact_checker" and checker["name"] == "AFP Factuel"
    official = await credibility.rate(
        "https://www.jirama.mg/communiques", html="", official_hosts={"jirama.mg"}
    )
    assert official["known"] == "official"
    assert _by_key(official)["official"]["status"] == "found"
    post = await credibility.rate("https://www.facebook.com/page/posts/1", {"author": "Page démo"})
    assert post["platform"] == "facebook.com" and post["known"] is None
    assert {s["key"] for s in post["signals"]} == {"https", "author"}


def test_registrable_domains_and_fact_checker_names():
    assert credibility.registrable("actu.lexpress.mg") == "lexpress.mg"
    assert credibility.registrable("news.bbc.co.uk") == "bbc.co.uk"
    assert credibility.registrable("sante.gov.mg") == "sante.gov.mg"
    assert credibility.fact_checker_name("https://www.snopes.com/fact-check/x/") == "Snopes"
    assert credibility.fact_checker_name("https://www.lemonde.fr/politique/x") is None
    assert (
        credibility.fact_checker_name("https://www.lemonde.fr/les-decodeurs/article/x")
        == "Les Décodeurs (Le Monde)"
    )
