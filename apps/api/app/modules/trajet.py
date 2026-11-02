"""« Le trajet »: where a rumour was seen (side `rumour`) and where the correction went (side `truth`).

Stops are added by code on every gesture (a tip arrives, a verdict is signed, a radio marks a flash
« Diffusé », a diffusion is sent) through `add_stop`, or by hand with their proof. A stop records
what was documented; it never infers reach from a click or a download.

`GET …/items/{id}/trajet` reads the two lines side by side and names the gaps: rumour routes no
truth stop has taken back yet (same channel, same region), each one a place to « Diffuser ici ».
"""

import hashlib
import json
import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field, HttpUrl
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import ai, dates, places
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
        # Punctuation stripped, so « Radio RDJ, Antananarivo » still finds its region.
        location = places.gazetteer(re.sub(r"[^\w'’-]+", " ", place)) or {}
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


# --- « Diffuser » --------------------------------------------------------------------------

VERDICT_FR = {
    "true": "Vrai",
    "misleading": "Trompeur",
    "false": "Faux",
    "unverifiable": "Invérifiable",
}
VERDICT_MG = {
    "true": "Marina",
    "misleading": "Mamitaka",
    "false": "Diso",
    "unverifiable": "Tsy hay antoka",
}
FORMAT_KEYS = ("radio_line", "flash", "sms", "text", "institution_alert")
MG_KEYS = ("radio_line", "sms", "text")
DIFFUSE_SYSTEM = (
    "Tu prépares la diffusion d'une vérification qu'une rédaction de Madagascar a déjà signée. "
    "Tu n'ajoutes aucun fait, aucun chiffre, aucun nom, aucune date absents des éléments fournis. "
    "Ton calme et factuel, sans emoji ni hashtag. Réponds en JSON : "
    '{"radio_line": "une ou deux phrases à lire à l\'antenne", '
    '"flash": "un flash radio d\'environ 75 mots, qui nomme la rédaction et le verdict", '
    '"sms": "un SMS de 110 caractères au plus, sans lien", '
    '"text": "un message de 3 ou 4 phrases pour WhatsApp et Facebook, sans lien", '
    '"institution_alert": "un message poli à l\'institution concernée par la rumeur", '
    '"mg": {"radio_line": "…", "sms": "…", "text": "…"}}. '
    "Les champs de « mg » sont en malgache (teny malagasy) ; un locuteur les relira avant envoi."
)


def _plain(value: Any) -> str:
    return " ".join(str(value or "").split()) if isinstance(value, str) else ""


def _numbers(text: str) -> set[str]:
    return set(re.findall(r"\d+(?:[.,]\d+)?", text or ""))


def short_link(item: Item) -> str | None:
    """`<public site>/v/145` for FAN-0145 (the newest public verdict with that number)."""
    m = re.search(r"(\d+)$", str((item.data or {}).get("ref") or ""))
    return f"{get_settings().public_web_url.rstrip('/')}/v/{int(m[1])}" if m else None


def _fit_sms(head: str, link: str) -> str:
    room = 160 - len(link) - 1
    head = head if len(head) <= room else head[: max(room - 1, 0)].rstrip() + "…"
    return f"{head} {link}"


def templates(item: Item, ws: Workspace, reason: str, link: str, url: str) -> dict[str, Any]:
    """The formats written by code: always available, Mode sans IA included."""
    verdict = item.data["verdict"]
    word = VERDICT_FR[verdict]
    title = item.title.strip().rstrip(".")
    origin = (item.data or {}).get("origin")
    where = {
        "facebook": " sur Facebook",
        "whatsapp": " sur WhatsApp",
        "tiktok": " sur TikTok",
        "radio": " à la radio",
    }.get(origin or "", "")
    flash_words = (
        f"Flash vérification de {ws.name}. Une information circule{where} : « {title} ». "
        f"Nous avons vérifié. Notre conclusion : {word.lower()}. {reason} "
        "Avant de partager un message, demandez-vous d'où il vient et qui l'a publié en premier. "
        f"Le détail de notre vérification est sur {link}."
    ).split()
    return {
        "radio_line": f"{ws.name} a vérifié l'information selon laquelle « {title} ». "
        f"Conclusion : {word.lower()}. {reason}",
        "flash": " ".join(flash_words[:110]),
        "sms": _fit_sms(f"{word.upper()} : {title}.", link),
        "text": f"{word} · {ws.name}\n« {title} »\n\n{reason}\n\n{url}",
        "institution_alert": (
            f"Bonjour, {ws.name} a publié une vérification qui vous concerne : « {title} ». "
            f"Conclusion : {word.lower()}. {reason} Le détail : {url}. Si vous publiez un "
            "démenti ou une précision, merci de nous l'envoyer : nous l'ajouterons au dossier."
        ),
        "mg": None,
    }


def _clean_model(raw: dict, facts: str, link: str, fallback: dict[str, Any]) -> dict[str, Any]:
    """Keep a model field only when it is plausible: no number the facts do not hold, the SMS
    under 160 characters with its link, the flash around 75 words. Otherwise the template."""
    known = _numbers(facts)
    out = dict(fallback)

    def ok(text: str) -> bool:
        return bool(text) and _numbers(text) <= known

    def field(key: str, text: str) -> str:
        if not ok(text):
            return ""
        if key == "sms":  # the link is added by code, after the check
            return f"{text} {link}" if len(text) + len(link) < 160 else ""
        if key == "flash" and not 40 <= len(text.split()) <= 110:
            return ""
        return text

    for key in FORMAT_KEYS:
        if text := field(key, _plain(raw.get(key))):
            out[key] = text
    mg = raw.get("mg") if isinstance(raw.get("mg"), dict) else {}
    drafts = {k: text for k in MG_KEYS if (text := field(k, _plain(mg.get(k))))}
    out["mg"] = drafts or None
    return out


# Formats the model wrote, per verdict version (a new verdict or explanation is a new key), so
# opening the panel again costs no second call. Kept in memory: a GET writes nothing to the item.
_WRITTEN: dict[str, dict[str, Any]] = {}


class PosterOut(BaseModel):
    title: str
    verdict: str
    verdict_word: str
    verdict_word_mg: str
    reason: str
    newsroom: str
    ref: str | None
    date: str | None
    qr_url: str
    short_link: str | None


class FormatsOut(BaseModel):
    card: dict[str, str | None]
    radio_line: str
    flash: str
    sms: str
    text: str
    institution_alert: str
    permalink: str
    short_link: str | None
    poster: PosterOut
    # Malagasy drafts by the model: never sent before a speaker ticks « Relu en malgache ».
    mg: dict[str, str] | None
    written_by: Literal["ai", "template"]
    gaps: list[GapOut]
    # Kept for the earlier panel.
    radio: str
    social: str
    url: str
    delivery: Literal["draft_only"] = "draft_only"


async def _publishable(db: AsyncSession, member, item_id: uuid.UUID) -> tuple[Item, Workspace, str]:
    item = await _get_item(db, member, item_id)
    if item.status != "published" or item.data.get("verdict") not in VERDICT_FR:
        raise ApiError(409, "not_published", "Publish a newsroom verdict first")
    ws = await db.get(Workspace, member.workspace_id)
    if ws.verification != "approved":
        raise ApiError(409, "not_verified", "Checky has not verified this newsroom yet")
    if not ws.is_public:
        raise ApiError(
            409, "private_workspace", "Enable public verdicts before preparing public links"
        )
    reason = str(item.data.get("reason") or "").strip()
    if not reason:
        raise ApiError(409, "missing_reason", "Write a public explanation first")
    return item, ws, reason


def _posts(item: Item) -> dict[str, str | None]:
    posts = (item.data or {}).get("posts") or {}
    out: dict[str, str | None] = {}
    for lang in ("fr", "mg"):
        post = posts.get(lang) if isinstance(posts, dict) else None
        out[lang] = post.get("text") if isinstance(post, dict) else post
    return out


@router.get("/workspaces/{ws}/items/{item_id}/diffusion")
async def diffusion(item_id: uuid.UUID, member: AnyMember, db: Db) -> FormatsOut:
    """Every format of the signed verdict, written once by the model (one call, kept in memory
    until the verdict or its explanation change) or by templates when AI is off or busy."""
    item, ws, reason = await _publishable(db, member, item_id)
    from app.modules.signing import permalink

    url = permalink(item)
    link = short_link(item) or url
    base = templates(item, ws, reason, link, url)
    facts = json.dumps(
        {
            "affirmation": item.title,
            "verdict": VERDICT_FR[item.data["verdict"]],
            "raison": reason,
            "rédaction": ws.name,
            "référence": (item.data or {}).get("ref"),
            "origine": (item.data or {}).get("origin"),
        },
        ensure_ascii=False,
    )
    key = hashlib.sha256(f"{item.id}|{facts}|{link}".encode()).hexdigest()
    formats, written_by = base, "template"
    ai_on = (ws.settings or {}).get("ai_enabled", True)
    if ai_on and key in _WRITTEN:
        formats, written_by = {**base, **_WRITTEN[key]}, "ai"
    elif ai_on:
        try:
            reply = await ai.complete(
                [
                    {"role": "system", "content": DIFFUSE_SYSTEM + " " + dates.today_line()},
                    {"role": "user", "content": facts},
                ],
                workspace_id=ws.id,
                temperature=0.3,
                max_tokens=1200,
                response_format={"type": "json_object"},
            )
            raw = json.loads(reply.content or "{}")
            if isinstance(raw, dict):
                formats, written_by = _clean_model(raw, facts, link, base), "ai"
                if len(_WRITTEN) >= 256:
                    _WRITTEN.pop(next(iter(_WRITTEN)))
                _WRITTEN[key] = {k: formats.get(k) for k in (*FORMAT_KEYS, "mg")}
        except (ai.AiUnavailable, ValueError):
            pass
    word = VERDICT_FR[item.data["verdict"]]
    published = dates.parse(
        (item.data or {}).get("published_at") or (item.data or {}).get("signed_at")
    )
    trajet_now = await read_trajet(db, item)
    return FormatsOut(
        card=_posts(item),
        radio_line=formats["radio_line"],
        flash=formats["flash"],
        sms=formats["sms"],
        text=formats["text"],
        institution_alert=formats["institution_alert"],
        permalink=url,
        short_link=short_link(item),
        poster=PosterOut(
            title=item.title,
            verdict=item.data["verdict"],
            verdict_word=word,
            verdict_word_mg=VERDICT_MG[item.data["verdict"]],
            reason=reason,
            newsroom=ws.name,
            ref=(item.data or {}).get("ref"),
            date=dates.fr(published) if published else None,
            qr_url=url,
            short_link=short_link(item),
        ),
        mg=formats.get("mg"),
        written_by=written_by,
        gaps=trajet_now.gaps,
        radio=formats["radio_line"],
        social=formats["text"],
        url=url,
    )


MG_FORMATS = {"card_mg", "radio_line_mg", "sms_mg", "text_mg"}


class DiffuseRoute(BaseModel):
    model_config = ConfigDict(extra="forbid")
    channel: Channel
    place: str = Field(min_length=1, max_length=300)
    location: dict[str, Any] | None = None


class DiffuseIn(BaseModel):
    routes: list[DiffuseRoute] = Field(min_length=1, max_length=20)
    formats: list[str] = Field(default_factory=list, max_length=12)
    relu_mg: bool = False


class DiffuseOut(BaseModel):
    trajet: TrajetOut
    formats: list[str]
    dropped: list[str]


@router.post("/workspaces/{ws}/items/{item_id}/diffuse")
async def diffuse(item_id: uuid.UUID, body: DiffuseIn, member: AnyMember, db: Db) -> DiffuseOut:
    """The journalist sent the formats down these routes (from their own phone, radio or print
    shop): each becomes a truth stop `sent`. Malagasy formats go only once a speaker reread them."""
    item, ws, _ = await _publishable(db, member, item_id)
    kept = [f for f in dict.fromkeys(body.formats) if body.relu_mg or f not in MG_FORMATS]
    dropped = [f for f in dict.fromkeys(body.formats) if f not in kept]
    for r in body.routes:
        await add_stop(
            db,
            ws.id,
            item.id,
            side="truth",
            channel=r.channel,
            place=r.place,
            location=r.location,
            proof={"formats": kept, "relu_mg": body.relu_mg, "method": "diffuser"},
            status="sent",
            added_by=member.user.id,
            auto=False,
        )
    await record(
        db,
        ws.id,
        member.user.id,
        "item",
        item.id,
        "diffuse",
        {"routes": [r.model_dump(mode="json") for r in body.routes], "formats": kept},
    )
    await db.commit()
    out = await read_trajet(db, item)
    await broadcast(ws.id, "route.added", {"item_id": str(item.id)})
    return DiffuseOut(trajet=out, formats=kept, dropped=dropped)


class RadioDiffuseIn(BaseModel):
    item_id: uuid.UUID


class RadioDiffuseOut(BaseModel):
    status: str
    station: str
    at: datetime


@router.post("/public/radios/{token}/diffuse")
async def radio_diffused(token: str, body: RadioDiffuseIn, db: Db) -> RadioDiffuseOut:
    """A partner radio marks a flash « Diffusé » from its token link (no account): the truth
    stop for that station becomes `broadcast`."""
    from app.core.models import RadioPartner

    partner = await db.scalar(
        select(RadioPartner).where(RadioPartner.token == token, RadioPartner.approved.is_(True))
    )
    if partner is None:
        raise ApiError(404, "not_found", "Radio not found")
    item = await db.get(Item, body.item_id)
    if (
        item is None
        or item.workspace_id != partner.workspace_id
        or item.status != "published"
        or (item.data or {}).get("verdict") not in VERDICT_FR
    ):
        raise ApiError(404, "not_found", "Verdict not found")
    station = f"{partner.name} {partner.frequency or ''}".strip()
    actor = f"radio:{partner.id}"
    now = datetime.now(UTC)
    stop = await db.scalar(
        select(Route).where(
            Route.item_id == item.id,
            Route.side == "truth",
            Route.channel == "radio",
            Route.place == station,
        )
    )
    if stop is not None:
        stop.status = "broadcast"
        stop.proof = {**(stop.proof or {}), "broadcast_at": now.isoformat()}
    else:
        stop = await add_stop(
            db,
            partner.workspace_id,
            item.id,
            side="truth",
            channel="radio",
            place=station,
            location=partner.location or {},
            proof={"broadcast_at": now.isoformat(), "partner_id": str(partner.id)},
            status="broadcast",
            added_by=actor,
        )
    await record(
        db, partner.workspace_id, actor, "item", item.id, "broadcast", {"station": station}
    )
    await db.commit()
    await broadcast(partner.workspace_id, "route.added", {"item_id": str(item.id)})
    return RadioDiffuseOut(status="broadcast", station=station, at=now)
