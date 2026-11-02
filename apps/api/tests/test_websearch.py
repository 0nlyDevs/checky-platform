"""Searching outside the newsroom: web (keyless DuckDuckGo), Wikipedia, fact-checkers,
and the traces AI generators leave in image files."""

import asyncio
import io
from urllib.parse import parse_qs

import httpx
import pytest

from app.core import websearch
from app.core.config import get_settings
from app.workers.ingest import ai_signals, image_meta

DDG = """
<a rel="nofollow" class="result__a" href="https://duckduckgo.com/y.js?ad_domain=x.com&amp;ad=1">Pub</a>
<a class="result__snippet" href="#">Achetez</a>
<a rel="nofollow" class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Ffactuel.afp.com%2Fnon-oms&amp;rut=1">Non, Madagascar &amp; l'OMS</a>
<a class="result__snippet" href="#">Rien ne permet <b>d'affirmer</b></a>
<a rel="nofollow" class="result__a" href="https://www.lexpress.mg/article">L'Express</a>
<a class="result__snippet" href="#">Inondations</a>
"""


@pytest.fixture
def web(monkeypatch):
    websearch._cache.clear()
    seen = []

    def handler(request):
        seen.append(request)
        host = request.url.host
        if host == "html.duckduckgo.com":
            return httpx.Response(200, text=DDG)
        if host == "fr.wikipedia.org" and request.url.path == "/w/api.php":
            assert "FANILO" in request.headers["user-agent"]
            return httpx.Response(200, json={"query": {"search": [{"title": "Analakely"}]}})
        if host == "fr.wikipedia.org":
            return httpx.Response(200, json={"extract": "Analakely est le quartier central."})
        if host == "factchecktools.googleapis.com":
            review = {
                "publisher": {"name": "AFP"},
                "url": "https://factuel.afp.com/g",
                "textualRating": "Faux",
                "title": "Faux",
            }
            return httpx.Response(
                200, json={"claims": [{"text": "Madagascar quitte l'OMS", "claimReview": [review]}]}
            )
        return httpx.Response(404)

    monkeypatch.setattr(websearch, "_transport", httpx.MockTransport(handler))
    return seen


def test_keyless_web_search_skips_adverts_and_decodes_links(web):
    found = asyncio.run(websearch.web("Madagascar OMS"))
    assert [r["url"] for r in found] == [
        "https://factuel.afp.com/non-oms",
        "https://www.lexpress.mg/article",
    ]
    assert (
        found[0]["title"] == "Non, Madagascar & l'OMS"
        and found[0]["snippet"] == "Rien ne permet d'affirmer"
    )
    asyncio.run(websearch.web("Madagascar OMS"))
    assert len(web) == 1  # the second identical search came from the cache


def test_wikipedia_gives_summaries(web):
    wiki = asyncio.run(websearch.wikipedia("Analakely"))
    assert wiki[0]["url"] == "https://fr.wikipedia.org/wiki/Analakely"
    assert wiki[0]["snippet"] == "Analakely est le quartier central."


def test_fact_checks_put_claim_reviews_first(web, monkeypatch):
    found = asyncio.run(websearch.fact_checks("OMS"))
    assert [r["url"] for r in found] == ["https://factuel.afp.com/non-oms"]  # only fact-checkers
    websearch._cache.clear()
    monkeypatch.setattr(get_settings(), "google_factcheck_api_key", "AIza-test")
    found = asyncio.run(websearch.fact_checks("OMS"))
    assert found[0]["url"] == "https://factuel.afp.com/g" and "« Faux »" in found[0]["snippet"]
    query = parse_qs(next(r for r in web if r.url.host.startswith("factcheck")).url.query.decode())
    assert query["languageCode"] == ["fr"]


def test_generator_traces_in_images():
    from PIL import Image, PngImagePlugin

    info = PngImagePlugin.PngInfo()
    info.add_text("parameters", "a market, Steps: 20, Model: Stable Diffusion XL")
    buf = io.BytesIO()
    Image.new("RGB", (4, 4)).save(buf, "PNG", pnginfo=info)
    assert image_meta(buf.getvalue())["ai_markers"] == ["Stable Diffusion"]
    xmp = b"<x:xmpmeta><Iptc4xmpExt:DigitalSourceType>http://cv.iptc.org/newscodes/digitalsourcetype/trainedAlgorithmicMedia</Iptc4xmpExt:DigitalSourceType>"
    assert ai_signals(xmp + b"c2pa", [])["ai_markers"] == ["IPTC : média généré par IA"]
    assert ai_signals(xmp + b"c2pa", [])["content_credentials"]
    # an ordinary word in the file's bytes is not a generator ("imagen" is Spanish for image)
    assert ai_signals(b"... imagen de la plaza ...", [])["ai_markers"] == []
    assert ai_signals(b"", ["Software: Imagen 4"])["ai_markers"] == ["Google Imagen"]


def test_a_query_without_a_country_is_searched_in_madagascar():
    assert websearch.localised("pont Mangasoavina fermé") == "pont Mangasoavina fermé Madagascar"
    assert websearch.localised("Madagascar quitte l'OMS") == "Madagascar quitte l'OMS"
    assert websearch.localised("vary gasy lafo") == "vary gasy lafo"


DDG_LITE = """<tr><td><a rel="nofollow" href="https://www.genzmada.org/jirama" class='result-link'>Jirama délestage</a></td></tr>
<tr><td class='result-snippet'>La crise de la <b>Jirama</b> s&#x27;aggrave.</td></tr>"""


def test_a_throttled_search_falls_back_to_the_lite_page(monkeypatch):
    websearch._cache.clear()
    asked = []

    def handler(request):
        asked.append(request.url.host)
        if request.url.host == "html.duckduckgo.com":
            return httpx.Response(202, text="slow down")
        return httpx.Response(200, text=DDG_LITE)

    monkeypatch.setattr(websearch, "_transport", httpx.MockTransport(handler))
    found = asyncio.run(websearch.web("Jirama Toamasina"))
    assert asked == ["html.duckduckgo.com", "lite.duckduckgo.com"]
    assert found == [
        {
            "title": "Jirama délestage",
            "url": "https://www.genzmada.org/jirama",
            "snippet": "La crise de la Jirama s'aggrave.",
        }
    ]
