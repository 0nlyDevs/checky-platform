"""Anonymous extension checks: public evidence and published verdicts, never private drafts.

No AI call or new truth verdict is produced here. A similar published claim is a candidate to
read, not an automatic verdict on the submitted passage. Nothing is written to a newsroom.
"""

import asyncio
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core import dates
from app.core.access import Db
from app.core.config import get_settings
from app.core.errors import ApiError
from app.core.public_checks import public_check_budget
from app.modules import imagecheck, linkcheck, public

router = APIRouter(
    prefix="/public", tags=["public-checks"], dependencies=[Depends(public_check_budget)]
)


class PublicCheckIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str | None = Field(default=None, max_length=6000)
    url: str | None = Field(default=None, max_length=2000)

    @field_validator("url")
    @classmethod
    def http_url(cls, value: str | None) -> str | None:
        return imagecheck.ImageIn.public_http(value) if value else None

    @model_validator(mode="after")
    def content(self):
        self.text = (self.text or "").strip() or None
        if not self.url and len(self.text or "") < 3:
            raise ValueError("A public link or at least three text characters are needed")
        return self


class PublicSource(BaseModel):
    n: int
    kind: str
    title: str
    url: str
    snippet: str
    date: str | None = None


class PublicCheckOut(BaseModel):
    url: str | None
    kind: str
    title: str
    excerpt: str
    published_at: str | None = None
    days_old: int | None = None
    needs_text: bool = False
    published: list[public.VerdictOut]
    results: list[PublicSource]


@router.post("/check")
async def check(body: PublicCheckIn, db: Db) -> PublicCheckOut:
    try:
        async with asyncio.timeout(45):
            return await _check(body, db)
    except TimeoutError as exc:
        raise ApiError(503, "public_check_unavailable", "Public evidence search timed out") from exc


async def _check(body: PublicCheckIn, db: Db) -> PublicCheckOut:
    text = body.text or ""
    kind, title, final, published_at = "text", "", body.url, None
    if not text and body.url:
        try:
            page = await linkcheck.read_link(body.url)
        except (ValueError, OSError, httpx.HTTPError) as exc:
            raise ApiError(422, "content_unreadable", "The public page could not be read") from exc
        text = str(page.get("text") or "")[:6000]
        kind, title = str(page.get("kind") or "page"), str(page.get("title") or "")[:500]
        final = page.get("final_url") or body.url
        published_at = dates.parse(page.get("published_at"))
    out = PublicCheckOut(
        url=final,
        kind=kind,
        title=title,
        excerpt=text[:600],
        published_at=published_at.isoformat() if published_at else None,
        days_old=max(0, (dates.today() - published_at).days) if published_at else None,
        needs_text=not text and kind != "image",
        published=[],
        results=[],
    )
    if not text:
        return out
    out.published = await public.find_published(db, text[:4000], k=3)
    # The selected passage itself is the query: no model, invented claims or private workspace.
    query = " ".join((title or text).split())[:200]
    found = await linkcheck._search(query, final)
    for source in found:
        parsed = urlparse(source.get("url") or "")
        if (
            parsed.scheme in ("http", "https")
            and parsed.hostname
            and not parsed.username
            and not parsed.password
        ):
            out.results.append(
                PublicSource(
                    n=source["n"],
                    kind=source["kind"],
                    title=source["title"][:500],
                    url=source["url"],
                    snippet=source["snippet"][:700],
                    date=source.get("date"),
                )
            )
    return out


@router.post("/image-check")
async def image_check(body: imagecheck.ImageIn) -> imagecheck.ImageOut:
    try:
        async with asyncio.timeout(35):
            return await imagecheck.inspect_image(
                body, allow_detector=get_settings().public_image_detector_enabled
            )
    except TimeoutError as exc:
        raise ApiError(
            503, "public_image_unavailable", "Public image examination timed out"
        ) from exc
