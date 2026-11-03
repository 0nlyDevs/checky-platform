"""Searching outside the newsroom's own files: the web, Wikipedia and published fact-checks.

The web uses Tavily's dedicated API when configured, otherwise best-effort DuckDuckGo HTML.
Tavily requests are restricted to the free plan without pay-as-you-go and basic search only.
Wikipedia uses its public API. Results are kept 10 minutes in memory. Reading a found page is
the agent's `fetch_url` (SSRF-guarded).
"""

import asyncio
import html
import json
import os
import re
import time
from html.parser import HTMLParser
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import httpx

from app.core import keys
from app.core.config import get_settings

# Wikimedia asks every client for a User-Agent with a way to reach its maintainers.
WIKI_UA = "Checky/0.1 (https://github.com/0nlyDevs/checky-platform; newsroom fact-checking tool)"
BROWSER_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/141.0 Safari/537.36"
)
# Fact-checkers that publish in French or about Africa and Madagascar, then worldwide.
FACT_CHECKERS = [
    "factuel.afp.com",
    "africacheck.org",
    "observers.france24.com",
    "lemonde.fr/les-decodeurs",
    "francetvinfo.fr/vrai-ou-fake",
    "liberation.fr/checknews",
    "rfi.fr/fr/podcasts/les-dessous-de-l-infox",
    # Worldwide signatories of the IFCN code of principles (a rumour often travels from abroad).
    "factcheck.afp.com",
    "20minutes.fr/societe/desintox",
    "snopes.com",
    "politifact.com",
    "factcheck.org",
    "fullfact.org",
    "leadstories.com",
    "maldita.es",
    "newtral.es",
    "chequeado.com",
    "aosfatos.org",
    "correctiv.org/faktencheck",
    "boomlive.in",
    "altnews.in",
    "dubawa.org",
    "pesacheck.org",
    "reuters.com/fact-check",
    "apnews.com/hub/ap-fact-check",
]
CACHE_SECONDS, CACHE_MAX = 600.0, 200

# Tests swap this for an httpx.MockTransport.
_transport: httpx.AsyncBaseTransport | None = None
_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}


class SearchUnavailable(Exception):
    def __init__(self, message: str, *, reason: str = "unavailable"):
        super().__init__(message)
        self.reason = reason


class _KeyRefused(SearchUnavailable):
    """This key cannot search right now (quota, plan, rate limit, bad key); the next one may."""


# Tavily statuses that refuse a key before any credit is spent: bad key, rate limit, plan limit,
# pay-as-you-go limit.
TAVILY_REFUSED = {401, 403, 429, 432, 433}


def _text(fragment: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", fragment)).strip()


def _client(headers: dict[str, str]) -> httpx.AsyncClient:
    transport = _transport
    # Some hosting networks have unreliable IPv6 egress. Bind direct searches to IPv4,
    # without disabling TLS verification or bypassing an operator-configured proxy.
    proxy_configured = any(
        os.environ.get(name)
        for name in (
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "ALL_PROXY",
            "http_proxy",
            "https_proxy",
            "all_proxy",
        )
    )
    if transport is None and get_settings().search_ipv4_only and not proxy_configured:
        transport = httpx.AsyncHTTPTransport(local_address="0.0.0.0")
    return httpx.AsyncClient(
        transport=transport, timeout=15, headers=headers, follow_redirects=True
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
    if parsed.hostname == "duckduckgo.com" or (parsed.hostname or "").endswith(".duckduckgo.com"):
        if parsed.path.startswith("/y.js"):  # an advert
            return None
        target = parse_qs(parsed.query).get("uddg")
        return unquote(target[0]) if target else None
    return href if parsed.scheme in ("http", "https") else None


# DuckDuckGo's HTML page, then its "lite" page: after a burst of queries the first one answers
# 202 (a "slow down" page) for a few minutes while the lite one usually still answers.
DDG_PAGES = (
    "https://html.duckduckgo.com/html/",
    "https://lite.duckduckgo.com/lite/",
)


async def _duckduckgo(query: str, k: int) -> list[dict[str, Any]]:
    failure = SearchUnavailable("DuckDuckGo did not return a recognizable result page")
    try:
        async with asyncio.timeout(12):
            async with _client(
                {"User-Agent": BROWSER_UA, "Accept-Language": "fr-FR,fr;q=0.9"}
            ) as http:
                for url in DDG_PAGES:
                    for method in ("POST", "GET"):
                        try:
                            r = await http.request(
                                method,
                                url,
                                **(
                                    {"data": {"q": query, "kl": "fr-fr"}}
                                    if method == "POST"
                                    else {"params": {"q": query, "kl": "fr-fr"}}
                                ),
                                timeout=4,
                            )
                        except httpx.HTTPError as exc:
                            failure = SearchUnavailable(
                                type(exc).__name__,
                                reason="timeout"
                                if isinstance(exc, httpx.TimeoutException)
                                else "unavailable",
                            )
                            continue
                        if r.status_code == 200:
                            parsed = _DDGParser()
                            parsed.feed(r.text)
                            if parsed.results:
                                return parsed.results[:k]
                            if parsed.empty and not parsed.blocked:
                                return []
                            failure = SearchUnavailable(
                                "DuckDuckGo challenge or unknown markup",
                                reason="blocked" if parsed.blocked else "unavailable",
                            )
                        else:
                            failure = SearchUnavailable(
                                f"DuckDuckGo HTTP {r.status_code}",
                                reason="blocked"
                                if r.status_code in (202, 403, 429)
                                else "unavailable",
                            )
                        # Try the other endpoint before GET if POST was explicitly throttled.
                        if r.status_code in (202, 429):
                            break
    except TimeoutError as exc:
        raise SearchUnavailable("DuckDuckGo timed out", reason="timeout") from exc
    raise failure


class _DDGParser(HTMLParser):
    """Attribute order and quote style vary between the HTML and lite search pages."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.results = []
        self.current = None
        self.capture = None
        self.buffer = []
        self.empty = False
        self.blocked = False

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        classes = (values.get("class") or "").split()
        self.empty |= any(c.startswith("no-results") for c in classes)
        self.blocked |= values.get("id") in ("challenge-form", "anomaly-form") or any(
            "anomaly" in c for c in classes
        )
        if tag == "a" and any(c in ("result__a", "result-link") for c in classes):
            url = _ddg_url(values.get("href") or "")
            self.current = None
            if url and url not in {r["url"] for r in self.results}:
                self.current = {"title": "", "url": url, "snippet": ""}
                self.results.append(self.current)
                self.capture, self.buffer = (tag, "title"), []
        elif self.current is not None and any(
            c in ("result__snippet", "result-snippet") for c in classes
        ):
            self.capture, self.buffer = (tag, "snippet"), []
        elif self.capture and tag == "br":
            self.buffer.append(" ")

    def handle_data(self, data):
        if self.capture:
            self.buffer.append(data)

    def handle_endtag(self, tag):
        if self.capture and tag == self.capture[0]:
            if self.current is not None:
                self.current[self.capture[1]] = re.sub(r"\s+", " ", "".join(self.buffer)).strip()
            self.capture = None


LOCAL = ("madagascar", "madagasikara", "malagasy", "gasy")


def localised(query: str) -> str:
    """The query with "Madagascar" when it names no country: the rumours checked here are mostly
    Malagasy, and a French-language search otherwise answers about France (measured on « pont
    Mangasoavina fermé »: 2 results of 6 about Madagascar without it, 6 of 6 with it)."""
    q = query.strip()
    return q if any(w in q.lower() for w in LOCAL) else f"{q} Madagascar"


def provider() -> str:
    settings = get_settings()
    if settings.web_search_provider == "auto":
        return "tavily" if settings.tavily_api_key.strip() else "duckduckgo"
    return settings.web_search_provider


async def _tavily_json(http: httpx.AsyncClient, method: str, path: str, **kwargs) -> dict:
    """Fixed API origin, no redirects/retries, bounded JSON, and no credential in errors."""
    async with http.stream(
        method, f"https://api.tavily.com/{path}", follow_redirects=False, **kwargs
    ) as response:
        if response.status_code != 200:
            error = _KeyRefused if response.status_code in TAVILY_REFUSED else SearchUnavailable
            raise error(
                f"Tavily {path} HTTP {response.status_code}",
                reason="blocked" if response.status_code == 429 else "unavailable",
            )
        raw = bytearray()
        async for chunk in response.aiter_bytes():
            raw.extend(chunk)
            if len(raw) > 1_000_000:
                raise SearchUnavailable("Tavily response too large")
    try:
        value = json.loads(raw)
    except (ValueError, UnicodeError) as exc:
        raise SearchUnavailable("Tavily returned invalid JSON") from exc
    if not isinstance(value, dict):
        raise SearchUnavailable("Tavily returned an invalid object")
    return value


def _free_tavily_budget(usage: dict) -> None:
    """Fail closed: do not issue a credit-consuming search for paid/overage-enabled accounts."""
    try:
        account = usage["account"]
        key = usage["key"]
        free = str(account["current_plan"]).casefold() in ("researcher", "free")
        plan_limit, plan_usage = int(account["plan_limit"]), int(account["plan_usage"])
        no_overage = int(account["paygo_limit"] or 0) == 0 and int(account["paygo_usage"] or 0) == 0
        key_limit = int(key.get("limit") or plan_limit)
        key_usage = int(key["usage"])
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise SearchUnavailable("Tavily free usage could not be verified") from exc
    if not free or not no_overage or not 0 < plan_limit <= 1000:
        raise _KeyRefused("Tavily requires a free plan with pay-as-you-go disabled")
    if plan_usage < 0 or key_usage < 0 or plan_usage >= plan_limit or key_usage >= key_limit:
        raise _KeyRefused("Tavily free quota is exhausted")


async def _tavily_search(key: str, query: str, k: int, domains: list[str] | None) -> dict:
    """One key: check its free usage, then search. No retry of the POST with the same key."""
    try:
        async with _client(
            {"Authorization": f"Bearer {key}", "Accept": "application/json"}
        ) as http:
            usage = await _tavily_json(http, "GET", "usage", timeout=3)
            _free_tavily_budget(usage)
            data = await _tavily_json(
                http,
                "POST",
                "search",
                timeout=7,
                json={
                    "query": query,
                    "search_depth": "basic",
                    "auto_parameters": False,
                    "topic": "general",
                    "max_results": min(max(k, 1), 20),
                    "include_answer": False,
                    "include_raw_content": False,
                    "include_images": False,
                    "include_domains": domains or [],
                },
            )
    except httpx.HTTPError as exc:
        raise SearchUnavailable(
            "Tavily request failed",
            reason="timeout" if isinstance(exc, httpx.TimeoutException) else "unavailable",
        ) from exc
    return data


async def _tavily(query: str, k: int, domains: list[str] | None = None) -> list[dict[str, Any]]:
    tavily_keys = keys.split(get_settings().tavily_api_key)
    if not tavily_keys:
        raise SearchUnavailable("Tavily API key is not configured")
    refused: SearchUnavailable | None = None
    for key in keys.rotation("tavily", tavily_keys):
        try:
            data = await _tavily_search(key, query, k, domains)
        except _KeyRefused as exc:
            # Refused before any credit was spent: set this key aside, the next one may answer.
            keys.set_aside("tavily", key, 30.0 if exc.reason == "blocked" else 3600.0)
            refused = exc
            continue
        return _tavily_results(data, k)
    raise SearchUnavailable(
        "Every Tavily key is exhausted or refused",
        reason=refused.reason if refused else "unavailable",
    ) from refused


def _tavily_results(data: dict, k: int) -> list[dict[str, Any]]:
    if not isinstance(data.get("results"), list):
        raise SearchUnavailable("Tavily returned no results field")
    out, seen = [], set()
    for item in data["results"]:
        if not isinstance(item, dict):
            continue
        url = item.get("url")
        if not isinstance(url, str) or len(url) > 2000:
            continue
        try:
            parsed = urlparse(url)
        except ValueError:
            continue
        if (
            parsed.scheme not in ("https", "http")
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or url in seen
        ):
            continue
        seen.add(url)
        out.append(
            {
                "url": url,
                "title": _text(str(item.get("title") or ""))[:500],
                "snippet": _text(str(item.get("content") or ""))[:1200],
            }
        )
        if len(out) >= k:
            break
    if data["results"] and not out:
        raise SearchUnavailable("Tavily returned unusable results")
    return out


async def web(query: str, k: int = 6) -> list[dict[str, Any]]:
    """Web results [{title, url, snippet}], best first."""
    query = query.strip()[:1000]  # retain fact-check site filters appended to a short query
    backend = provider()

    async def fetch():
        try:
            return await _tavily(query, k) if backend == "tavily" else await _duckduckgo(query, k)
        except httpx.HTTPError as e:
            raise SearchUnavailable(type(e).__name__) from e

    return await _cached(f"web|{backend}|{k}|{query}", fetch)


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
                        "date": review.get("reviewDate"),
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
    try:
        if provider() == "tavily":
            domains = sorted({domain.split("/")[0] for domain in FACT_CHECKERS})
            found = await _cached(
                f"fact-search|tavily|{k}|{query}", lambda: _tavily(query, k + 4, domains)
            )
        else:
            sites = " OR ".join(sorted({f"site:{d.split('/')[0]}" for d in FACT_CHECKERS}))
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
        if _fact_checker_url(r["url"]) and r["url"] not in known
    ]
    return (reviews + on_sites)[:k]


def _fact_checker_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
    except ValueError:
        return False
    for entry in FACT_CHECKERS:
        domain, _, section = entry.partition("/")
        if host != domain and not host.endswith("." + domain):
            continue
        prefix = "/" + section.rstrip("/")
        if not section or parsed.path == prefix or parsed.path.startswith(prefix + "/"):
            return True
    return False


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
