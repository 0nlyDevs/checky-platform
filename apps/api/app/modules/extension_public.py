"""Anonymous extension checks: public evidence and published verdicts, never private drafts.

AI prepares grounded searches, never a truth verdict. A similar published claim is a candidate
to read, not an automatic verdict on the submitted passage. Nothing is written to a newsroom.
"""

import asyncio
from collections.abc import AsyncIterable

import httpx
from fastapi import APIRouter, Depends
from fastapi.sse import EventSourceResponse, ServerSentEvent
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core import dates, evidence_search, query_plan
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


class PublicSource(evidence_search.ResearchSource):
    pass


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
    preparation: query_plan.Preparation | None = None
    search_status: str = "empty"
    searches: list[evidence_search.SearchAttempt] = Field(default_factory=list)


@router.post("/check")
async def check(body: PublicCheckIn, db: Db) -> PublicCheckOut:
    try:
        async with asyncio.timeout(60):
            async for event, data in _pipeline(body, db):
                if event == "result":
                    return data
    except TimeoutError as exc:
        raise ApiError(503, "public_check_unavailable", "Public evidence search timed out") from exc
    raise ApiError(503, "public_check_incomplete", "Public evidence search did not finish")


@router.post("/check/stream", response_class=EventSourceResponse)
async def check_stream(body: PublicCheckIn, db: Db) -> AsyncIterable[ServerSentEvent]:
    try:
        async with asyncio.timeout(60):
            async for event, data in _pipeline(body, db):
                yield ServerSentEvent(event=event, data=data)
    except TimeoutError:
        yield ServerSentEvent(event="error", data={"code": "public_check_unavailable"})
    except ApiError as exc:
        yield ServerSentEvent(event="error", data={"code": exc.code})
    except (httpx.HTTPError, ValueError, TypeError):
        yield ServerSentEvent(event="error", data={"code": "public_check_failed"})


def _step(key, status, **extra):
    return "step", {"key": key, "status": status, "summary": "", **extra}


async def _pipeline(body: PublicCheckIn, db: Db):
    yield _step("read", "running")
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
    text = query_plan.clean_text(text)
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
    yield _step("read", "done")
    if not text:
        yield "result", out
        yield "done", {}
        return
    out.published = await public.find_published(db, text[:4000], k=3)
    yield _step("claims", "running")
    out.preparation = await query_plan.prepare(text)
    yield "preparation", out.preparation
    yield _step("claims", "done", method=out.preparation.method, count=len(out.preparation.queries))
    yield _step("search", "running")
    report = await evidence_search.search(out.preparation, final)
    out.search_status, out.searches = report.status, report.attempts
    yield _step(
        "search",
        "failed" if report.status == "unavailable" else "done",
        search_status=report.status,
        count=len(report.sources),
    )
    if report.sources:
        yield _step("verdict", "running")
        await evidence_search.read_sources(report.sources, out.preparation, text)
        yield _step(
            "verdict", "done", count=sum(source.read_status == "read" for source in report.sources)
        )
    out.results = [PublicSource(**source.model_dump()) for source in report.sources]
    yield "result", out
    yield "done", {}


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
