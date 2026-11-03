"""Reverse image search run by Checky: where else a picture was published, and the earliest page.

The links to Google Lens, TinEye and Yandex (`linkcheck.reverse_search`) stay: they cost nothing and
the journalist can open them. When `SERPAPI_API_KEY` is set (a comma list works, see `keys.py`),
Checky also asks Google Lens through SerpApi for the pages showing the same picture, reads each
page's own publication date (Open Graph, JSON-LD: `ingest.page_date`, never a guess), and reports the
earliest dated one: « déjà en ligne le 14 mars 2023 (tvm.mg) ». A page without a date is counted but
never dated. The picture sent is the one the desk already allows out (faces blurred, or a public page's
own image). Without a key, or on any failure, the answer is None: the links remain.
"""

import asyncio
import logging
import time
from datetime import date
from typing import Any
from urllib.parse import urlsplit

import httpx

from app.core import dates, keys
from app.core.config import get_settings
from app.workers import ingest

log = logging.getLogger("checky.reverse_search")
SERPAPI = "https://serpapi.com/search.json"
SERVICE = "serpapi"
MAX_PAGES = 8  # candidate pages whose date is read
FIRST_YEAR = 1995
CACHE_SECONDS = 6 * 3600
# Separate daily budgets: anonymous checks must not spend what the newsrooms rely on.
DAILY_CAP = {"desk": 60, "public": 8}
_transport: httpx.AsyncBaseTransport | None = None  # tests mock the provider here
_cache: dict[str, tuple[float, dict[str, Any] | None]] = {}
_spent: dict[tuple[str, str], int] = {}


def configured() -> bool:
    return bool(keys.split(get_settings().serpapi_api_key))


def _cache_key(image_url: str) -> str:
    """Our own storage signs its URLs anew at every call: there the picture is its host and path. Any
    other URL (a page's image) can serve different pictures under one path, so it keys on the whole."""
    parts = urlsplit(image_url)
    ours = urlsplit(get_settings().storage_endpoint or "").netloc
    if ours and parts.netloc == ours:
        return f"{parts.netloc}{parts.path}"
    return image_url


def _host(url: str) -> str:
    return (urlsplit(url).hostname or "").removeprefix("www.")


def _usable(day: date | None) -> date | None:
    return day if day and FIRST_YEAR <= day.year and day <= dates.today() else None


async def _matches(image_url: str) -> list[dict[str, Any]]:
    """The pages Google Lens lists for this picture: [{url, title, source}]."""
    all_keys = keys.rotation(SERVICE, keys.split(get_settings().serpapi_api_key))
    async with httpx.AsyncClient(transport=_transport, timeout=25) as http:
        for key in all_keys:
            response = await http.get(
                SERPAPI, params={"engine": "google_lens", "url": image_url, "api_key": key}
            )
            if response.status_code in (401, 402, 403, 429):
                keys.set_aside(SERVICE, key, 3600)  # bad key or quota used up: the next one
                continue
            response.raise_for_status()
            found = response.json().get("visual_matches") or []
            return [
                {"url": m["link"], "title": m.get("title") or "", "source": m.get("source") or ""}
                for m in found
                if isinstance(m, dict)
                and str(m.get("link", "")).startswith(("http://", "https://"))
            ]
    return []


async def _dated(page: dict[str, Any], gate: asyncio.Semaphore) -> dict[str, Any] | None:
    async with gate:
        try:
            async with asyncio.timeout(10):
                final, content_type, body, encoding = await ingest.fetch_raw(page["url"])
        except Exception as exc:  # noqa: BLE001 - a page that does not answer is simply not dated
            log.debug("reverse-search page unreadable: %s", type(exc).__name__)
            return None
    if "html" not in content_type.lower():
        return None
    html = body[:600_000].decode(encoding or "utf-8", errors="replace")
    day = _usable(dates.parse(ingest.page_date(html, None)))
    if not day:
        return None
    return {
        "date": day.isoformat(),
        "host": _host(final),
        "url": final,
        "title": page["title"][:200],
    }


async def earliest(image_url: str, scope: str = "desk") -> dict[str, Any] | None:
    """{first, pages, corroborated, matches, dated} or None (not configured, over the scope's daily
    cap, provider down). `first` is the earliest dated page {date, host, url, title}; `pages` every
    dated host (earliest first, five at most). The dates are the pages' own word: `corroborated` is
    true only when two different sites date the picture older than STALE_DAYS, and only then may the
    date drive anything beyond being shown."""
    if not configured():
        return None
    key = _cache_key(image_url)
    if (hit := _cache.get(key)) and time.monotonic() - hit[0] < CACHE_SECONDS:
        return hit[1]
    day = (scope, dates.today().isoformat())
    if _spent.get(day, 0) >= DAILY_CAP.get(scope, DAILY_CAP["public"]):
        return None
    _spent[day] = _spent.get(day, 0) + 1
    try:
        pages = await _matches(image_url)
    except (httpx.HTTPError, ValueError) as exc:
        log.warning(
            "reverse search failed: %s", type(exc).__name__
        )  # never the URL: it carries a key
        return None
    seen: set[str] = set()
    candidates = []
    for page in pages:
        if _host(page["url"]) not in seen:  # one page per site: the picture's story, not a site's
            seen.add(_host(page["url"]))
            candidates.append(page)
    gate = asyncio.Semaphore(4)
    read = [
        r for r in await asyncio.gather(*(_dated(p, gate) for p in candidates[:MAX_PAGES])) if r
    ]
    read.sort(key=lambda r: r["date"])
    old = [r for r in read if (dates.today() - dates.parse(r["date"])).days > dates.STALE_DAYS]
    result = {
        "first": read[0] if read else None,
        "pages": read[:5],
        "corroborated": len({r["host"] for r in old}) >= 2,
        "matches": len(pages),
        "dated": len(read),
    }
    if len(_cache) > 256:
        _cache.clear()
    _cache[key] = (time.monotonic(), result)
    return result
