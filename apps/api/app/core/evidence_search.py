"""Bounded, observable evidence search and literal source excerpts. No truth classification."""

import asyncio
import re
import time
from typing import Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx
from pydantic import BaseModel, Field

from app.core import dates, websearch
from app.core.query_plan import Preparation, tokens
from app.core.words import STOP
from app.workers import ingest

SearchState = Literal["ok", "empty", "blocked", "unavailable", "timeout"]


class SearchAttempt(BaseModel):
    kind: Literal["web", "fact-check", "wikipedia"]
    query: str
    status: SearchState
    count: int = 0
    duration_ms: int = 0


class ResearchSource(BaseModel):
    n: int
    kind: str
    title: str
    url: str
    snippet: str
    date: str | None = None
    read_status: Literal["not_read", "read", "blocked", "unavailable", "unsupported"] = "not_read"
    passages: list[str] = Field(default_factory=list)
    wording_overlap: bool = False
    similar_to: list[int] = Field(default_factory=list)
    older_than_claim: bool = False


class SearchReport(BaseModel):
    status: Literal["ok", "partial", "unavailable", "empty"]
    attempts: list[SearchAttempt]
    sources: list[ResearchSource]


def canonical(raw: str) -> str | None:
    try:
        url = urlsplit(raw)
        if url.scheme not in ("http", "https") or not url.hostname or url.username or url.password:
            return None
        query = [
            (k, v)
            for k, v in parse_qsl(url.query, keep_blank_values=True)
            if not k.lower().startswith("utm_") and k.lower() not in ("fbclid", "gclid")
        ]
        return (
            urlunsplit((url.scheme, url.netloc.lower(), url.path or "/", urlencode(query), ""))
            if len(raw) <= 2000
            else None
        )
    except ValueError:
        return None


def relevant(source: ResearchSource, plan: Preparation) -> bool:
    available = set(tokens(source.title + " " + source.snippet))
    groups = [
        set(tokens(entity)) - STOP - {word for word in tokens(entity) if word.isdigit()}
        for entity in plan.entities
    ]
    phrases = [group for group in groups if len(group) >= 2]
    if any(
        len(group & available) >= 2 and len(group & available) / len(group) >= 0.5
        for group in phrases
    ):
        return True
    names = {
        word
        for group in groups
        if len(group) == 1
        for word in group
        if len(word) >= 5
        and (not phrases or word not in {"madagascar", "senegal", "dakar", "france"})
    }
    return bool(names & available) if names or phrases else True


async def search(plan: Preparation, skip: str | None = None) -> SearchReport:
    queries = plan.queries[:3]
    if not queries:
        return SearchReport(status="empty", attempts=[], sources=[])
    specs = [("web", queries[0], websearch.web)]
    # Give an independent service a slot before spending the whole budget on one blocked engine.
    specs += [
        ("wikipedia", " ".join(plan.entities[:3])[:160] or queries[0], websearch.wikipedia),
    ]
    specs += [("web", q, websearch.web) for q in queries[1:]]
    specs += [
        ("fact-check", queries[0], websearch.fact_checks),
    ]
    semaphore = asyncio.Semaphore(2)

    async def attempt(kind, query, fn):
        started = time.monotonic()
        try:
            async with semaphore, asyncio.timeout(12):
                found = await fn(query)
            state = "ok" if found else "empty"
        except websearch.SearchUnavailable as exc:
            state = exc.reason if exc.reason in ("blocked", "timeout") else "unavailable"
            found = []
        except (TimeoutError, httpx.TimeoutException):
            state, found = "timeout", []
        except (httpx.HTTPError, ValueError, KeyError):
            state, found = "unavailable", []
        return SearchAttempt(
            kind=kind,
            query=query,
            status=state,
            count=len(found),
            duration_ms=int((time.monotonic() - started) * 1000),
        ), found

    tasks = [asyncio.create_task(attempt(*spec)) for spec in specs]
    try:
        await asyncio.wait(tasks, timeout=24)
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    attempts, collected = [], {}
    skipped = canonical(skip) if skip else None
    for spec, task in zip(specs, tasks, strict=True):
        if task.cancelled():
            attempts.append(
                SearchAttempt(kind=spec[0], query=spec[1], status="timeout", duration_ms=24000)
            )
            continue
        info, found = task.result()
        attempts.append(info)
        for source in found:
            url = canonical(source.get("url") or "")
            if not url or url == skipped:
                continue
            if url not in collected:
                collected[url] = ResearchSource(
                    n=0,
                    kind=info.kind,
                    title=str(source.get("title") or "")[:500],
                    url=url,
                    snippet=str(source.get("snippet") or "")[:700],
                    date=source.get("date"),
                )
            elif info.kind == "fact-check":
                collected[url].kind = "fact-check"

    def rank(source):
        content = " ".join(tokens(source.title + " " + source.snippet))
        return sum(
            len(tokens(entity)) + 1
            for entity in plan.entities
            if " ".join(tokens(entity)) in content
        ) + (2 if source.kind == "fact-check" else 0)

    sources = sorted(
        (source for source in collected.values() if relevant(source, plan)), key=rank, reverse=True
    )[:10]
    for n, source in enumerate(sources, 1):
        source.n = n
    failures = any(item.status not in ("ok", "empty") for item in attempts)
    web_worked = any(item.kind == "web" and item.status in ("ok", "empty") for item in attempts)
    status = (
        "partial"
        if failures and (sources or web_worked)
        else "unavailable"
        if failures
        else "ok"
        if sources
        else "empty"
    )
    return SearchReport(status=status, attempts=attempts, sources=sources)


def _shingles(text: str) -> set[tuple[str, ...]]:
    words = tokens(text)
    return {tuple(words[i : i + 5]) for i in range(max(0, len(words) - 4))}


def close_wording(left: str, right: str) -> bool:
    a, b = _shingles(left), _shingles(right)
    common = len(a & b)
    return common >= 8 and common / max(1, min(len(a), len(b))) >= 0.65


def passages(text: str, plan: Preparation) -> list[str]:
    asked = set(tokens(" ".join([*plan.claims, *plan.entities])))
    pieces = [
        part.strip()[:650]
        for part in re.split(r"\n+|(?<=[.!?])\s+", text)
        if len(part.strip()) >= 20
    ]
    ranked = sorted(
        enumerate(pieces), key=lambda pair: len(asked & set(tokens(pair[1]))), reverse=True
    )
    chosen = sorted(ranked[:2])
    return [part for _, part in chosen]


async def read_sources(sources: list[ResearchSource], plan: Preparation, original: str) -> None:
    semaphore = asyncio.Semaphore(2)

    async def read(source):
        try:
            async with semaphore, asyncio.timeout(7):
                final, mime, body, encoding = await ingest.fetch_raw(source.url)
                if mime not in ("text/html", "application/xhtml+xml", "text/plain"):
                    source.read_status = "unsupported"
                    return ""
                html = body[:750_000].decode(encoding or "utf-8", errors="replace")
                page = (
                    await asyncio.to_thread(ingest.extract_page, html, final)
                    if mime != "text/plain"
                    else {"text": html, "published_at": None}
                )
            text = str(page.get("text") or "")[:16_000]
            if len(text.strip()) < 20:
                source.read_status = "unavailable"
                return ""
            source.read_status, source.passages = "read", passages(text, plan)
            if published := dates.parse(page.get("published_at")):
                source.date = published.isoformat()
                years = [
                    int(y)
                    for y in re.findall(r"\b20\d{2}\b", " ".join([*plan.entities, *plan.claims]))
                ]
                source.older_than_claim = bool(years and published.year < min(years))
            source.wording_overlap = close_wording(text, original)
            return text
        except (ValueError, OSError, httpx.HTTPError, TimeoutError) as exc:
            source.read_status = (
                "blocked" if "HTTP 403" in str(exc) or "HTTP 429" in str(exc) else "unavailable"
            )
            return ""

    # Prefer accessible articles/documentation over login-heavy social pages after discovery.
    def friction(source):
        host = urlsplit(source.url).hostname or ""
        return any(
            host == site or host.endswith("." + site)
            for site in ("facebook.com", "instagram.com", "tiktok.com")
        )

    chosen = sorted(sources, key=friction)[:3]
    tasks = [asyncio.create_task(read(source)) for source in chosen]
    try:
        if tasks:
            await asyncio.wait(tasks, timeout=10)
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    texts = [task.result() if not task.cancelled() else "" for task in tasks]
    for index, left in enumerate(texts):
        for other in range(index + 1, len(texts)):
            if close_wording(left, texts[other]):
                chosen[index].similar_to.append(chosen[other].n)
                chosen[other].similar_to.append(chosen[index].n)
