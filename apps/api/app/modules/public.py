"""Public features, no account: the archive of published verdicts, "is it already checked?", tips and
their follow-up. Only newsrooms that opted in (`workspace.is_public`) are visible, and only claims a
journalist confirmed and moved to `published` leave the newsroom."""

import re
import secrets
import time
import unicodedata
import uuid
from collections import defaultdict, deque
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy import func, select

from app.core.access import Db
from app.core.activity import broadcast, record
from app.core.errors import ApiError
from app.core.models import Item, Source, Workspace

router = APIRouter(prefix="/public", tags=["public"])

PUBLIC_AUTHOR = "public"  # author_id of a tip; not a Better Auth user
Origin = Literal["facebook", "whatsapp", "tiktok", "radio", "press", "other"]


class NewsroomOut(BaseModel):
    slug: str
    name: str


class VerdictOut(BaseModel):
    id: uuid.UUID
    ref: str | None
    title: str
    verdict: str
    reason: str | None
    post: str | None
    sources: list[str]
    origin: str | None
    first_seen_at: str | None
    published_at: datetime
    newsroom: NewsroomOut


class VerdictPage(BaseModel):
    items: list[VerdictOut]
    total: int


class MatchIn(BaseModel):
    text: str = Field(min_length=3, max_length=4000)


class MatchOut(BaseModel):
    score: float
    verdict: VerdictOut


class TipIn(BaseModel):
    newsroom: str = Field(min_length=1, max_length=140)
    text: str = Field(min_length=5, max_length=4000)
    url: HttpUrl | None = None
    origin: Origin = "other"


class TipOut(BaseModel):
    token: str
    ref: str


class TipStatusOut(BaseModel):
    ref: str | None
    title: str
    status: str
    received_at: datetime
    newsroom: NewsroomOut
    verdict: VerdictOut | None


# --- a small per-address limit on tips, enough for a public form without accounts
_TIPS: dict[str, deque[float]] = defaultdict(deque)
TIP_LIMIT, TIP_WINDOW = 5, 600.0


def _allow_tip(addr: str) -> bool:
    now, q = time.monotonic(), _TIPS[addr]
    while q and now - q[0] > TIP_WINDOW:
        q.popleft()
    if len(q) >= TIP_LIMIT:
        return False
    q.append(now)
    return True


def _published():
    return (
        select(Item, Workspace)
        .join(Workspace, Workspace.id == Item.workspace_id)
        .where(
            Workspace.is_public.is_(True),
            Item.type == "claim",
            Item.status == "published",
            Item.data["verdict"].astext.in_(["true", "misleading", "false", "unverifiable"]),
        )
    )


async def _verdict(db: Db, item: Item, ws: Workspace) -> VerdictOut:
    d = item.data or {}
    titles = (await db.scalars(select(Source.title).where(Source.item_id == item.id))).all()
    posts = d.get("posts") or {}
    post = posts.get("fr") if isinstance(posts, dict) else None
    analysis = d.get("analysis") if isinstance(d.get("analysis"), dict) else {}
    return VerdictOut(
        id=item.id,
        ref=d.get("ref"),
        title=item.title,
        verdict=d["verdict"],
        reason=d.get("reason") or analysis.get("reason"),
        post=post.get("text") if isinstance(post, dict) else post,
        sources=[t for t in titles if t],
        origin=d.get("origin"),
        first_seen_at=d.get("first_seen_at"),
        published_at=item.updated_at,
        newsroom=NewsroomOut(slug=ws.slug, name=ws.name),
    )


# --- "is it already checked?": word overlap on accent-free text (no AI verdict is ever made here)
STOP = {
    *[
        "les",
        "des",
        "une",
        "un",
        "le",
        "la",
        "de",
        "du",
        "et",
        "en",
        "au",
        "aux",
        "pour",
        "par",
        "sur",
        "dans",
        "que",
        "qui",
        "est",
        "sont",
        "ce",
    ],
    *[
        "cette",
        "ces",
        "avec",
        "plus",
        "pas",
        "ont",
        "été",
        "the",
        "and",
        "ny",
        "sy",
        "amin",
        "ary",
        "izay",
        "dia",
        "fa",
    ],
}


def _words(text: str) -> set[str]:
    flat = unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode()
    return {w for w in re.findall(r"[a-z0-9]+", flat) if len(w) >= 3 and w not in STOP}


@router.get("/newsrooms")
async def newsrooms(db: Db) -> list[NewsroomOut]:
    rows = await db.scalars(
        select(Workspace).where(Workspace.is_public.is_(True)).order_by(Workspace.name)
    )
    return [NewsroomOut(slug=w.slug, name=w.name) for w in rows]


@router.get("/verdicts")
async def list_verdicts(
    db: Db, q: str | None = None, newsroom: str | None = None, limit: int = 20, offset: int = 0
) -> VerdictPage:
    query = _published()
    if newsroom:
        query = query.where(Workspace.slug == newsroom)
    if q:
        like = f"%{q.strip()}%"
        query = query.where(Item.title.ilike(like) | Item.body.ilike(like))
    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    rows = (
        await db.execute(
            query.order_by(Item.updated_at.desc()).limit(min(limit, 50)).offset(offset)
        )
    ).all()
    return VerdictPage(items=[await _verdict(db, i, w) for i, w in rows], total=total or 0)


@router.get("/verdicts/{item_id}")
async def get_verdict(item_id: uuid.UUID, db: Db) -> VerdictOut:
    row = (await db.execute(_published().where(Item.id == item_id))).first()
    if row is None:
        raise ApiError(404, "not_found", "Verdict not found")
    return await _verdict(db, *row)


@router.post("/match")
async def match(body: MatchIn, db: Db) -> list[MatchOut]:
    asked = _words(body.text)
    if not asked:
        return []
    scored = []
    for item, ws in (await db.execute(_published().limit(500))).all():
        known = _words(f"{item.title} {item.body}")
        if not known:
            continue
        score = len(asked & known) / min(len(asked), len(known))
        if score >= 0.4:
            scored.append((score, item, ws))
    scored.sort(key=lambda r: r[0], reverse=True)
    return [MatchOut(score=round(s, 2), verdict=await _verdict(db, i, w)) for s, i, w in scored[:3]]


async def _next_ref(db: Db, ws: uuid.UUID) -> str:
    refs = await db.scalars(select(Item.data["ref"].astext).where(Item.workspace_id == ws))
    nums = [int(m.group(1)) for r in refs if r and (m := re.match(r"FAN-(\d+)$", r))]
    return f"FAN-{(max(nums) + 1) if nums else 1:04d}"


@router.post("/tips", status_code=201)
async def create_tip(body: TipIn, request: Request, db: Db) -> TipOut:
    if not _allow_tip(request.client.host if request.client else "unknown"):
        raise ApiError(429, "too_many_tips", "Too many tips, try again in a few minutes")
    ws = await db.scalar(
        select(Workspace).where(Workspace.slug == body.newsroom, Workspace.is_public.is_(True))
    )
    if ws is None:
        raise ApiError(404, "not_found", "Newsroom not found")
    text = body.text.strip()
    token = secrets.token_urlsafe(18)
    ref = await _next_ref(db, ws.id)
    item = Item(
        workspace_id=ws.id,
        author_id=PUBLIC_AUTHOR,
        type="claim",
        title=text.splitlines()[0][:300],
        body="\n\n".join(p for p in [text, str(body.url) if body.url else ""] if p),
        status="to_check",
        tags=["signalement"],
        data={
            "ref": ref,
            "first_seen_at": datetime.now().astimezone().isoformat(),
            "origin": body.origin,
            "source_count": 0,
            "public_tip": True,
            "tip_token": token,
            "tip_url": str(body.url) if body.url else None,
        },
    )
    db.add(item)
    await db.flush()
    await record(db, ws.id, PUBLIC_AUTHOR, "item", item.id, "create")
    await db.commit()
    await db.refresh(item)
    from app.modules.items import _out  # the desk's live grid shows the tip at once

    await broadcast(ws.id, "item.created", _out(item))
    return TipOut(token=token, ref=ref)


@router.get("/tips/{token}")
async def tip_status(token: str, db: Db) -> TipStatusOut:
    row = (
        await db.execute(
            select(Item, Workspace)
            .join(Workspace, Workspace.id == Item.workspace_id)
            .where(Item.data["tip_token"].astext == token, Workspace.is_public.is_(True))
        )
    ).first()
    if row is None:
        raise ApiError(404, "not_found", "Tip not found")
    item, ws = row
    published = item.status == "published" and (item.data or {}).get("verdict")
    return TipStatusOut(
        ref=(item.data or {}).get("ref"),
        title=item.title,
        status=item.status,
        received_at=item.created_at,
        newsroom=NewsroomOut(slug=ws.slug, name=ws.name),
        verdict=await _verdict(db, item, ws) if published else None,
    )
