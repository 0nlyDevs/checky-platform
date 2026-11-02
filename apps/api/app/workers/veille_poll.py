"""The press reader of Veille: the national press's RSS feeds become `press` items.

`PRESS_FEEDS` is a comma list of feed URLs, each optionally named: "Outlet|https://…/feed".
Every entry not seen before (deduplicated by its link) becomes an `Item(type="press")` with the
outlet, link, publication date and the place it names, then runs past the watched words. The job
is queued by the Veille page (at most every 20 minutes per newsroom) or its « Actualiser ».
"""

import asyncio
import html
import logging
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

import feedparser
import httpx
from sqlalchemy import select

from app.core import dates
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.http import shared as shared_http
from app.core.models import Item
from app.workers.queue import JobContext, handler

log = logging.getLogger("checky.veille_poll")
_transport: httpx.AsyncBaseTransport | None = None  # tests swap in a mock
UA = "Checky/0.1 (newsroom verification tool; press monitoring)"
MAX_ENTRIES = 30  # per feed and per run


@dataclass(frozen=True)
class Feed:
    outlet: str
    url: str


def parse_feeds(raw: str | None) -> list[Feed]:
    """« Outlet|https://… , https://… » → feeds; an unnamed feed is named after its host."""
    feeds = []
    for part in (raw or "").split(","):
        part = part.strip()
        if not part:
            continue
        name, _, url = part.rpartition("|") if "|" in part else ("", "", part)
        url = url.strip()
        if not url.startswith(("http://", "https://")):
            continue
        outlet = name.strip() or (urlparse(url).hostname or url).removeprefix("www.")
        feeds.append(Feed(outlet=outlet[:120], url=url))
    return feeds


def _text(value: str | None) -> str:
    value = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def _published(entry: Any) -> str | None:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if not parsed:
        return None
    try:
        return datetime(*parsed[:6], tzinfo=UTC).astimezone(dates.EAT).isoformat()
    except (TypeError, ValueError):
        return None


def entries(feed: Feed, body: bytes) -> list[dict[str, Any]]:
    """The feed's entries as press items (title, summary, link, date), newest first."""
    parsed = feedparser.parse(body)
    out = []
    for entry in parsed.entries[:MAX_ENTRIES]:
        link = (entry.get("link") or "").strip()
        title = _text(entry.get("title"))
        if not link or not title:
            continue
        out.append(
            {
                "title": title[:300],
                "summary": _text(entry.get("summary") or entry.get("description"))[:2000],
                "link": link[:2000],
                "published_at": _published(entry),
                "outlet": feed.outlet,
            }
        )
    return out


async def fetch(feed: Feed) -> bytes:
    r = await shared_http("press", _transport, 15).get(
        feed.url, headers={"User-Agent": UA}, follow_redirects=True
    )
    r.raise_for_status()
    return r.content


async def store(workspace_id: uuid.UUID, rows: list[dict[str, Any]]) -> list[Item]:
    """Save the entries this newsroom has not seen (by link); returns the new items."""
    from app.modules.veille import region_of_text

    if not rows:
        return []
    async with SessionLocal() as db:
        known = set(
            (
                await db.scalars(
                    select(Item.data["link"].astext).where(
                        Item.workspace_id == workspace_id,
                        Item.type == "press",
                        Item.data["link"].astext.in_([r["link"] for r in rows]),
                    )
                )
            ).all()
        )
        created = []
        for row in rows:
            if row["link"] in known:
                continue
            known.add(row["link"])
            place = region_of_text(row["title"], row["summary"])
            item = Item(
                workspace_id=workspace_id,
                author_id="press",
                type="press",
                title=row["title"],
                body=row["summary"],
                status="to_check",
                tags=[],
                data={
                    "link": row["link"],
                    "outlet": row["outlet"],
                    "published_at": row["published_at"],
                    **({"location": place} if place else {}),
                },
            )
            db.add(item)
            created.append(item)
        await db.commit()
        for item in created:
            await db.refresh(item)
        return created


@handler("veille_poll")
async def veille_poll(ctx: JobContext) -> dict[str, Any]:
    from app.modules.veille import match_signals

    feeds = parse_feeds(get_settings().press_feeds)
    if not feeds:
        return {"skipped": "no_feeds"}
    results = await asyncio.gather(*(fetch(f) for f in feeds), return_exceptions=True)
    rows, failed = [], []
    for feed, result in zip(feeds, results, strict=True):
        if isinstance(result, BaseException):
            log.warning("press feed %s failed: %s", feed.url, result)
            failed.append(feed.outlet)
            continue
        rows.extend(entries(feed, result))
    await ctx.progress(60)
    created = await store(ctx.workspace_id, rows)
    async with SessionLocal() as db:
        for item in created:
            await match_signals(db, ctx.workspace_id, f"{item.title} {item.body}", "press")
    return {"created": len(created), "read": len(rows), "failed": failed}
