"""« Avant l'antenne »: during a call-in show, the radio journalist repeats the caller's claim in one
sentence (or pastes the post) and knows in seconds whether it was already checked.

`POST /workspaces/{ws}/avant-antenne` answers from the database only, so it comes back at once:
the signed verdicts of every newsroom that publishes (and this desk's own), each with its « Ligne
radio », two sentences written by code from the signed verdict (never a model, so never a figure
the verdict does not hold), in French, and in Malagasy only when a speaker ticked « Relu en
malgache » for that exact verdict; whether this desk or another newsroom already follows the
rumour; and, with no signed verdict, a careful line that says so without any verdict word.
`POST …/avant-antenne/fact-checks` brings the fact-checkers' reviews, relayed as theirs, a few
seconds later. Nothing is written: « Suivre dans le desk » goes through `copilot/act`.
"""

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Literal

import httpx
from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core import websearch
from app.core.access import AnyMember, Db
from app.core.models import Item, Workspace
from app.core.seal import check_label
from app.core.words import words
from app.modules import public, trajet
from app.modules.verify_public import MATCH, ReviewOut, _query, followed, review

log = logging.getLogger("checky.onair")
router = APIRouter(tags=["onair"])

CAREFUL = {
    "new": "À ce stade, aucune rédaction n'a publié de vérification sur cette information. "
    "Avant de la répéter ou de la partager, attendons d'en savoir plus.",
    "followed": "Une rédaction vérifie cette information en ce moment. Avant de la répéter ou de "
    "la partager, attendons sa conclusion.",
}


class OnAirIn(BaseModel):
    text: str = Field(min_length=3, max_length=2000)


class OnAirVerdict(BaseModel):
    id: uuid.UUID
    ref: str | None
    title: str
    verdict: str
    newsroom: str
    own: bool  # signed by this desk
    published_at: datetime
    signed_at: str | None
    check_label: str | None  # « vérification 145 », said on air
    link: str  # the short link, or the verdict page
    radio_line: str
    # Only the Malagasy line a speaker reread for this exact verdict; otherwise None and
    # `mg_status` says why.
    radio_line_mg: str | None
    mg_status: Literal["relu", "not_reread"]
    score: float


class OwnClaim(BaseModel):
    item_id: uuid.UUID
    ref: str | None
    title: str
    status: str


class OnAirOut(BaseModel):
    status: Literal["signed", "followed", "new"]
    signed: list[OnAirVerdict]
    own: OwnClaim | None = None  # this desk already follows it (not signed yet)
    followed_by: str | None = None  # another newsroom follows it
    careful_line: str | None = None  # with no signed verdict: no verdict word in it


class ReviewsOut(BaseModel):
    status: Literal["done", "unavailable"]
    reviews: list[ReviewOut]


def radio_lines(item: Item, ws: Workspace) -> tuple[str, str | None]:
    """The French line from the signed verdict, and the Malagasy line a speaker reread for this
    very version of it (`trajet` keeps the reread strings with the version they vouch for)."""
    from app.modules.signing import permalink

    d = item.data or {}
    reason = " ".join(str(d.get("reason") or "").split())
    url = permalink(item)
    fr = trajet.templates(item, ws, reason, trajet.short_link(item) or url, url)["radio_line"]
    fr = " ".join(fr.split())
    r = trajet._attested(item)
    kept = r.get("texts") if r else None
    mg = None
    if (
        isinstance(kept, dict)
        and r.get("digest") == trajet._version(item)
        and r.get("mg_hash") == trajet.mg_hash(kept)
    ):
        mg = kept.get("radio_line_mg") or None
    return fr, mg


def _score(asked: set[str], item: Item) -> float:
    return max((public.overlap(asked, known) for known in public._claim_words(item)), default=0.0)


@router.post("/workspaces/{ws}/avant-antenne")
async def before_air(body: OnAirIn, member: AnyMember, db: Db) -> OnAirOut:
    asked = words(body.text)
    rows: list[tuple[float, Item, Workspace]] = []
    if len(asked) >= 2:
        own_ws = await db.get(Workspace, member.workspace_id)
        # every newsroom that publishes, and this desk's own signed verdicts even when it does not
        query = public._published().order_by(Item.updated_at.desc()).limit(500)
        found = list((await db.execute(query)).all())
        if own_ws is not None and not own_ws.publishes:
            mine = await db.scalars(
                select(Item)
                .where(
                    Item.workspace_id == own_ws.id,
                    Item.type == "claim",
                    Item.status == "published",
                    Item.data["verdict"].astext.in_(list(trajet.VERDICT_FR)),
                )
                .order_by(Item.updated_at.desc())
                .limit(200)
            )
            found += [(item, own_ws) for item in mine]
        for item, ws in found:
            score = _score(asked, item)
            if score >= MATCH:
                rows.append((score, item, ws))
        # the best first; among equals, this desk's own verdict
        rows.sort(key=lambda r: (-round(r[0], 1), r[2].id != member.workspace_id))
    signed = []
    for score, item, ws in public._distinct(rows)[:3]:
        d = item.data or {}
        fr, mg = radio_lines(item, ws)
        from app.modules.signing import permalink

        signed.append(
            OnAirVerdict(
                id=item.id,
                ref=d.get("ref"),
                title=item.title,
                verdict=d["verdict"],
                newsroom=ws.name,
                own=ws.id == member.workspace_id,
                published_at=item.updated_at,
                signed_at=d.get("signed_at") if isinstance(d.get("signed_at"), str) else None,
                check_label=check_label(d.get("ref")),
                link=trajet.short_link(item) or permalink(item),
                radio_line=fr,
                radio_line_mg=mg,
                mg_status="relu" if mg else "not_reread",
                score=round(score, 2),
            )
        )
    own = None
    if len(asked) >= 2:
        best = 0.0
        for item in await db.scalars(
            select(Item)
            .where(
                Item.workspace_id == member.workspace_id,
                Item.type == "claim",
                Item.status != "published",
            )
            .order_by(Item.created_at.desc())
            .limit(300)
        ):
            score = _score(asked, item)
            if score >= MATCH and score > best:
                best = score
                own = OwnClaim(
                    item_id=item.id,
                    ref=(item.data or {}).get("ref"),
                    title=item.title,
                    status=item.status,
                )
    other = await followed(db, body.text)
    followed_by = other[1].name if other and other[1].id != member.workspace_id else None
    if signed:
        return OnAirOut(status="signed", signed=signed, own=own, followed_by=followed_by)
    status = "followed" if own or followed_by else "new"
    return OnAirOut(
        status=status,
        signed=[],
        own=own,
        followed_by=followed_by,
        careful_line=CAREFUL[status],
    )


@router.post("/workspaces/{ws}/avant-antenne/fact-checks")
async def fact_checks(body: OnAirIn, member: AnyMember) -> ReviewsOut:
    """The fact-checkers' reviews of this claim, in their own words (never mapped onto ours)."""
    try:
        async with asyncio.timeout(15):
            raw = await websearch.fact_checks(_query(body.text), k=6)
    except (TimeoutError, websearch.SearchUnavailable, httpx.HTTPError) as exc:
        log.info("avant l'antenne: fact-checkers unavailable (%s)", type(exc).__name__)
        return ReviewsOut(status="unavailable", reviews=[])
    asked = words(body.text)
    reviews = [r for r in (review(x, asked) for x in raw) if r]
    return ReviewsOut(status="done", reviews=reviews[:4])
