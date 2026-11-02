"""« Le trajet »: where a rumour was seen (side `rumour`) and where the correction went (side `truth`).

Stops are added by code on every gesture (a tip arrives, a verdict is signed, a radio marks a flash
« Diffusé », a diffusion is sent) through `add_stop`, or by hand with their proof. A stop records
what was documented; it never infers reach from a click or a download.

`GET …/items/{id}/trajet` reads the two lines side by side and names the gaps: rumour routes no
truth stop has taken back yet (same channel, same region), each one a place to « Diffuser ici ».
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field, HttpUrl
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import dates, places
from app.core.access import AnyMember, Db
from app.core.activity import broadcast, record
from app.core.config import get_settings
from app.core.errors import ApiError
from app.core.models import Item, Route, Workspace
from app.modules.items import _get_item

router = APIRouter(tags=["trajet"])

Channel = Literal[
    "facebook",
    "whatsapp",
    "tiktok",
    "radio",
    "sms",
    "press",
    "web",
    "poster",
    "institution",
    "voice",
    "other",
]
CHANNELS = set(Channel.__args__)
SIDES = ("rumour", "truth")
# A truth stop is sent, then received or broadcast; a rumour stop is seen.
DEFAULT_STATUS = {"rumour": "seen", "truth": "sent"}


async def add_stop(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    item_id: uuid.UUID,
    *,
    side: str,
    channel: str,
    place: str,
    location: dict[str, Any] | None = None,
    proof: dict[str, Any] | None = None,
    status: str | None = None,
    added_by: str = "system",
    at: datetime | None = None,
    auto: bool = True,
) -> Route:
    """One stop on the road (flushed, committed by the caller). Other modules call it lazily:

        from app.modules import trajet
        await trajet.add_stop(db, ws, item.id, side="rumour", channel="sms", place="SMS")

    An automatic stop that repeats one already on the line (same side, channel, place and region)
    is counted on it (`proof.count`) instead of drawn twice: three SMS from one region are one stop
    « × 3 », and signing a verdict again does not add a second « Page publique »."""
    if side not in SIDES:
        raise ValueError(f"Unknown side: {side}")
    channel = channel if channel in CHANNELS else "other"
    place = (place or "").strip()[:300]
    if location is None and place:
        location = places.gazetteer(place) or {}
    location = location or {}
    if auto:
        for existing in await db.scalars(
            select(Route).where(
                Route.item_id == item_id,
                Route.side == side,
                Route.channel == channel,
                Route.place == place,
            )
        ):
            if places.region_of(existing.location) == places.region_of(location):
                existing.proof = {
                    **(existing.proof or {}),
                    **(proof or {}),
                    "count": int((existing.proof or {}).get("count") or 1) + 1,
                }
                if status:
                    existing.status = status
                await db.flush()
                return existing
    route = Route(
        workspace_id=workspace_id,
        item_id=item_id,
        added_by=added_by,
        side=side,
        channel=channel,
        place=place,
        location=location,
        at=at or datetime.now(UTC),
        proof=proof or {},
        status=status or DEFAULT_STATUS[side],
        auto=auto,
    )
    db.add(route)
    await db.flush()
    await record(
        db,
        workspace_id,
        added_by,
        "item",
        item_id,
        "route",
        {"route_id": str(route.id), "side": side, "channel": channel, "place": place},
    )
    return route


class RouteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    side: Literal["rumour", "truth"]
    channel: Channel
    place: str = Field(min_length=1, max_length=300)
    note: str = Field(min_length=5, max_length=1000)
    url: HttpUrl | None = None
    at: datetime


class RouteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID | None
    side: str
    channel: str
    place: str
    location: dict[str, Any] = Field(default_factory=dict)
    status: str
    proof: dict[str, Any]
    at: datetime
    auto: bool = True
    added_by: str = "system"
    # Not stored: the dossier's own first appearance (origin + first seen), when no stop says it.
    derived: bool = False


@router.get("/workspaces/{ws}/items/{item_id}/routes")
async def routes(item_id: uuid.UUID, member: AnyMember, db: Db) -> list[RouteOut]:
    await _get_item(db, member, item_id)
    return [
        RouteOut.model_validate(r)
        for r in await db.scalars(
            select(Route)
            .where(Route.workspace_id == member.workspace_id, Route.item_id == item_id)
            .order_by(Route.at)
        )
    ]


@router.post("/workspaces/{ws}/items/{item_id}/routes", status_code=201)
async def add_route(item_id: uuid.UUID, body: RouteIn, member: AnyMember, db: Db) -> RouteOut:
    item = await _get_item(db, member, item_id)
    if body.at.tzinfo is None or body.at > datetime.now(UTC):
        raise ApiError(422, "invalid_time", "Use an observed past time with timezone")
    if body.side == "truth" and item.status != "published":
        raise ApiError(409, "not_published", "Publish the newsroom conclusion first")
    route = await add_stop(
        db,
        member.workspace_id,
        item_id,
        side=body.side,
        channel=body.channel,
        place=body.place,
        at=body.at,
        status="reported",
        added_by=member.user.id,
        auto=False,
        proof={
            "note": body.note,
            "url": str(body.url) if body.url else None,
            "method": "member_report",
        },
    )
    await db.commit()
    out = RouteOut.model_validate(route)
    await broadcast(member.workspace_id, "route.added", out.model_dump(mode="json"))
    return out


# --- the two lines side by side -------------------------------------------------------------


class GapOut(BaseModel):
    channel: str
    place: str
    location: dict[str, Any]
    rumour_stop_id: uuid.UUID | None


class TrajetOut(BaseModel):
    rumour: list[RouteOut]
    truth: list[RouteOut]
    gaps: list[GapOut]
    covered: int
    summary: str


def _covers(truth: Route | RouteOut, rumour: Route | RouteOut) -> bool:
    """A correction takes a rumour route back on the same channel, in the same region (a stop
    with no region is national and covers the channel everywhere)."""
    if truth.channel != rumour.channel:
        return False
    a, b = places.region_of(truth.location), places.region_of(rumour.location)
    return not a or not b or places.same_region(truth.location, rumour.location)


def _origin_stop(item: Item) -> RouteOut | None:
    """The dossier's first appearance as the first rumour stop, from what the desk recorded
    (origin and first seen), when no stop on the line says it already."""
    d = item.data or {}
    origin = d.get("origin")
    seen = dates.parse_moment(d.get("first_seen_at"))
    if origin not in CHANNELS - {"web", "poster", "institution"} or seen is None:
        return None
    url = d.get("tip_url")
    return RouteOut(
        id=None,
        side="rumour",
        channel=origin,
        place="Première apparition notée",
        location={},
        status="seen",
        proof={"url": url} if url else {},
        at=seen,
        auto=True,
        derived=True,
    )


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'s' if n > 1 else ''}"


def summary(rumour: int, covered: int) -> str:
    if not rumour:
        return "Aucune étape de la rumeur n'est encore notée."
    if not covered:
        return (
            f"La rumeur est passée par {_plural(rumour, 'route')} ; la vérité n'en a repris aucune."
        )
    return f"La rumeur est passée par {_plural(rumour, 'route')} ; la vérité en a repris {covered}."


async def read_trajet(db: AsyncSession, item: Item) -> TrajetOut:
    rows = list(await db.scalars(select(Route).where(Route.item_id == item.id).order_by(Route.at)))
    rumour = [RouteOut.model_validate(r) for r in rows if r.side == "rumour"]
    truth = [RouteOut.model_validate(r) for r in rows if r.side == "truth"]
    origin = _origin_stop(item)
    if origin and not any(r.channel == origin.channel for r in rumour):
        rumour.insert(0, origin)
    gaps = [
        GapOut(channel=r.channel, place=r.place, location=r.location, rumour_stop_id=r.id)
        for r in rumour
        if not any(_covers(t, r) for t in truth)
    ]
    covered = len(rumour) - len(gaps)
    return TrajetOut(
        rumour=rumour,
        truth=truth,
        gaps=gaps,
        covered=covered,
        summary=summary(len(rumour), covered),
    )


@router.get("/workspaces/{ws}/items/{item_id}/trajet")
async def trajet(item_id: uuid.UUID, member: AnyMember, db: Db) -> TrajetOut:
    return await read_trajet(db, await _get_item(db, member, item_id))


class PublicStopOut(BaseModel):
    channel: str
    place: str
    region: str | None
    status: str
    at: datetime


class PublicTrajetOut(BaseModel):
    truth: list[PublicStopOut]
    rumour_routes: int
    truth_routes: int
    covered: int
    summary: str


@router.get("/public/verdicts/{item_id}/trajet")
async def public_trajet(item_id: uuid.UUID, db: Db) -> PublicTrajetOut:
    """« Où la correction est passée »: the truth side only (no proof, no notes) and the counts.
    Same visibility as `/public/verdicts/{id}`: a public newsroom's published claim with a
    confirmed verdict, nothing else."""
    from app.modules.public import _published

    found = (await db.execute(_published().where(Item.id == item_id))).first()
    if found is None:
        raise ApiError(404, "not_found", "Verdict not found")
    row = found[0]
    full = await read_trajet(db, row)
    return PublicTrajetOut(
        truth=[
            PublicStopOut(
                channel=s.channel,
                place=s.place,
                region=places.region_of(s.location),
                status=s.status,
                at=s.at,
            )
            for s in full.truth
        ],
        rumour_routes=len(full.rumour),
        truth_routes=len(full.truth),
        covered=full.covered,
        summary=full.summary,
    )


# --- demo -----------------------------------------------------------------------------------


def _last_morning(now: datetime) -> datetime:
    """The latest 06:00 (Madagascar time) that leaves room for the SMS that followed it."""
    local = now.astimezone(dates.EAT)
    morning = local.replace(hour=6, minute=0, second=0, microsecond=0)
    if morning + timedelta(hours=1, minutes=30) > local:
        morning -= timedelta(days=1)
    return morning


async def seed_demo(db: AsyncSession, workspace_id, user_id, items: dict[str, Item]) -> None:
    """The road of the pitch rumour (FAN-0145): a Facebook page at 23:47, a WhatsApp group, the
    06:00 radio bulletin, then SMS from Atsimo-Andrefana. All places are fictional (« démo »).
    The claim's first appearance is set to the Facebook post, so the dossier and its road agree."""
    item = items.get("FAN-0145")
    if item is None:
        return
    await db.execute(delete(Route).where(Route.item_id == item.id))
    morning = _last_morning(datetime.now(UTC))
    posted = morning - timedelta(hours=6, minutes=13)  # 23:47 the evening before
    stops = [
        (
            "facebook",
            "Page Facebook « Tana Flash Info » (démo)",
            "Antananarivo",
            posted,
            {"note": "Publication d'origine : la vidéo et le faux communiqué.", "demo": True},
        ),
        (
            "whatsapp",
            "Groupe WhatsApp « Voisins d'Analakely » (démo)",
            "Analakely",
            posted + timedelta(minutes=38),
            {"note": "Transféré avec la vidéo, sans lien d'origine.", "demo": True},
        ),
        (
            "radio",
            "Radio RDJ · journal de 06:00 (démo)",
            "Antananarivo",
            morning,
            {"note": "Reprise à l'antenne sans vérification.", "demo": True},
        ),
        (
            "sms",
            "SMS reçus sur la ligne Checky (démo)",
            "Atsimo-Andrefana",
            morning + timedelta(minutes=72),
            {"note": "Trois personnes demandent si c'est vrai.", "count": 3, "demo": True},
        ),
    ]
    for channel, place, where, at, proof in stops:
        db.add(
            Route(
                workspace_id=workspace_id,
                item_id=item.id,
                added_by=user_id,
                side="rumour",
                channel=channel,
                place=place,
                location=places.gazetteer(where) or {},
                at=at,
                proof=proof,
                status="seen",
                auto=True,
            )
        )
    item.data = {**item.data, "first_seen_at": posted.isoformat()}
    await db.flush()


# --- diffusion ------------------------------------------------------------------------------


class FormatsOut(BaseModel):
    radio: str
    sms: str
    social: str
    url: str
    delivery: Literal["draft_only"] = "draft_only"


@router.get("/workspaces/{ws}/items/{item_id}/diffusion")
async def formats(item_id: uuid.UUID, member: AnyMember, db: Db) -> FormatsOut:

    item = await _get_item(db, member, item_id)
    if item.status != "published" or item.data.get("verdict") not in (
        "true",
        "false",
        "misleading",
        "unverifiable",
    ):
        raise ApiError(409, "not_published", "Publish a newsroom verdict first")
    workspace = await db.get(Workspace, member.workspace_id)
    if not workspace.is_public:
        raise ApiError(
            409, "private_workspace", "Enable public verdicts before preparing public links"
        )
    reason = str(item.data.get("reason") or "").strip()
    if not reason:
        raise ApiError(409, "missing_reason", "Write a public explanation first")
    verdict = {
        "true": "Vrai",
        "false": "Faux",
        "misleading": "Trompeur",
        "unverifiable": "Invérifiable",
    }[item.data["verdict"]]
    url = get_settings().public_web_url.rstrip("/") + "/verifies/" + str(item.id)
    return FormatsOut(
        radio=f"{workspace.name} a vérifié : {item.title}. Conclusion : {verdict}. {reason}",
        sms=f"{verdict} — {item.title[:90]}. {url}",
        social=f"{verdict} · {workspace.name}\n{item.title}\n\n{reason}\n\n{url}",
        url=url,
    )
