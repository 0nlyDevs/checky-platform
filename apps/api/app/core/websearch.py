"""Searching outside the newsroom's own files: the web, Wikipedia and published fact-checks.

No key needed: the web goes through DuckDuckGo's HTML page and Wikipedia through its public API
(paid search APIs such as Brave's were left out on purpose). Results are kept 10 minutes in memory, so an agent
asking twice costs one request. Reading a found page is the agent's `fetch_url` (SSRF-guarded).
"""

import html
import re
import time
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import httpx

from app.core import keys
from app.core.config import get_settings

# Wikimedia asks every client for a User-Agent with a way to reach its maintainers.
WIKI_UA = "FANILO/0.1 (https://github.com/0nlyDevs/fanilo-base; newsroom fact-checking tool)"
BROWSER_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/141.0 Safari/537.36"
)
# Fact-checkers that publish in French or about Africa and Madagascar.
FACT_CHECKERS = [
    "factuel.afp.com",
    "africacheck.org",
    "observers.france24.com",
    "lemonde.fr/les-decodeurs",
    "francetvinfo.fr/vrai-ou-fake",
    "liberation.fr/checknews",
    "rfi.fr/fr/podcasts/les-dessous-de-l-infox",
]
CACHE_SECONDS, CACHE_MAX = 600.0, 200

# Tests swap this for an httpx.MockTransport.
_transport: httpx.AsyncBaseTransport | None = None
_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}


class SearchUnavailable(Exception):
    pass


def _text(fragment: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", fragment)).strip()


def _client(headers: dict[str, str]) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=_transport, timeout=15, headers=headers, follow_redirects=True
    )


async def _cached(key: str, fetch) -> list[dict[str, Any]]:
    now = time.monotonic()
    if (hit := _cache.get(key)) and now - hit[0] < CACHE_SECONDS:
        return hit[1]
    results = await fetch()
    if len(_cache) >= CACHE_MAX:
        _cache.pop(next(iter(_cache)))
    _cache[key] = (now, results)
    return results


def _ddg_url(href: str) -> str | None:
    href = html.unescape(href)
    if href.startswith("//"):
        href = "https:" + href
    parsed = urlparse(href)
    if parsed.netloc.endswith("duckduckgo.com"):
        if parsed.path.startswith("/y.js"):  # an advert
            return None
        target = parse_qs(parsed.query).get("uddg")
        return unquote(target[0]) if target else None
    return href if parsed.scheme in ("http", "https") else None


async def _duckduckgo(query: str, k: int) -> list[dict[str, Any]]:
    async with _client({"User-Agent": BROWSER_UA, "Accept-Language": "fr-FR,fr;q=0.9"}) as http:
        r = await http.post("https://html.duckduckgo.com/html/", data={"q": query, "kl": "fr-fr"})
    if r.status_code != 200:
        raise SearchUnavailable(f"DuckDuckGo HTTP {r.status_code}")
    out = []
    pattern = (
        r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>'
        r'(?:.*?class="result__snippet"[^>]*>(.*?)</a>)?'
    )
    for href, title, snippet in re.findall(pattern, r.text, re.DOTALL):
        if (url := _ddg_url(href)) and url not in {o["url"] for o in out}:
            out.append({"title": _text(title), "url": url, "snippet": _text(snippet or "")})
        if len(out) >= k:
            break
    return out


async def web(query: str, k: int = 6) -> list[dict[str, Any]]:
    """Web results [{title, url, snippet}], best first."""
    query = query.strip()[:300]

    async def fetch():
        try:
            return await _duckduckgo(query, k)
        except httpx.HTTPError as e:
            raise SearchUnavailable(type(e).__name__) from e

    return await _cached(f"web|{k}|{query}", fetch)


async def _claim_reviews(query: str, k: int) -> list[dict[str, Any]]:
    """Google Fact Check Tools: published claim reviews (ClaimReview) matching the words."""
    s = get_settings()
    for api_key in keys.rotation("factcheck", keys.split(s.google_factcheck_api_key)):
        async with _client({"Accept": "application/json"}) as http:
            r = await http.get(
                "https://factchecktools.googleapis.com/v1alpha1/claims:search",
                params={"query": query, "languageCode": "fr", "pageSize": k, "key": api_key},
            )
        if r.status_code in (403, 429):
            keys.set_aside("factcheck", api_key, keys.retry_after(r.headers, s.ai_cooldown))
            continue
        if r.status_code != 200:
            return []
        out = []
        for claim in r.json().get("claims", []):
            for review in claim.get("claimReview", [])[:1]:
                if not review.get("url"):
                    continue
                who = (review.get("publisher") or {}).get("name") or "Fact-checkeur"
                rating = review.get("textualRating") or "?"
                out.append(
                    {
                        "title": review.get("title") or claim.get("text", "")[:120],
                        "url": review["url"],
                        "snippet": f"{who} : « {rating} ». Affirmation : {claim.get('text', '')}",
                    }
                )
        return out[:k]
    return []


async def fact_checks(query: str, k: int = 6) -> list[dict[str, Any]]:
    """Articles by fact-checkers about the subject: Google's claim reviews when a key is set,
    then known fact-checkers' sites through the web search."""
    query = query.strip()[:300]
    reviews: list[dict[str, Any]] = []
    if keys.split(get_settings().google_factcheck_api_key):
        try:
            reviews = await _cached(f"claims|{k}|{query}", lambda: _claim_reviews(query, k))
        except httpx.HTTPError:
            reviews = []
    sites = " OR ".join(sorted({f"site:{d.split('/')[0]}" for d in FACT_CHECKERS}))
    try:
        found = await web(f"{query} ({sites})", k + 4)
    except SearchUnavailable:
        if reviews:
            return reviews
        raise
    known = {r["url"] for r in reviews}
    on_sites = [
        r
        for r in found
        # the fact-checking section itself, not the rest of a newspaper's site
        if any(f"//{d}" in r["url"] or f".{d}" in r["url"] for d in FACT_CHECKERS)
        and r["url"] not in known
    ]
    return (reviews + on_sites)[:k]


async def wikipedia(query: str, lang: str = "fr", k: int = 3) -> list[dict[str, Any]]:
    """Wikipedia articles [{title, url, snippet}] with each article's opening summary."""
    lang = lang if lang in ("fr", "mg", "en") else "fr"
    query = query.strip()[:300]

    async def fetch():
        base = f"https://{lang}.wikipedia.org"
        async with _client({"User-Agent": WIKI_UA}) as http:
            r = await http.get(
                f"{base}/w/api.php",
                params={
                    "action": "query",
                    "list": "search",
                    "srsearch": query,
                    "srlimit": k,
                    "format": "json",
                },
            )
            if r.status_code != 200:
                raise SearchUnavailable(f"Wikipedia HTTP {r.status_code}")
            out = []
            for hit in r.json().get("query", {}).get("search", []):
                title = hit["title"]
                summary = await http.get(
                    f"{base}/api/rest_v1/page/summary/{title.replace(' ', '_')}"
                )
                extract = summary.json().get("extract", "") if summary.status_code == 200 else ""
                out.append(
                    {
                        "title": f"Wikipedia · {title}",
                        "url": f"{base}/wiki/{title.replace(' ', '_')}",
                        "snippet": extract or _text(hit.get("snippet", "")),
                    }
                )
            return out

    try:
        return await _cached(f"wiki|{lang}|{k}|{query}", fetch)
    except httpx.HTTPError as e:
        raise SearchUnavailable(type(e).__name__) from e
