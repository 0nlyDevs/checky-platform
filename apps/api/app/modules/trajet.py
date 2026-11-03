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
from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field, HttpUrl
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import ai, dates, places, seal
from app.core.access import AnyMember, Db
from app.core.activity import broadcast, record
from app.core.config import get_settings
from app.core.errors import ApiError
from app.core.models import Item, Route, Workspace
from app.modules.items import _get_item, _out

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
    "unverifiable": "Tsy voamarina",
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


def _bare(link: str) -> str:
    return re.sub(r"^https?://", "", link)


def templates(item: Item, ws: Workspace, reason: str, link: str, url: str) -> dict[str, Any]:
    """The formats written by code: always available, Mode sans IA included. Each one carries the
    verification number written the same way (« vérification 145 »), which `/v/145` resolves."""
    verdict = item.data["verdict"]
    word = VERDICT_FR[verdict]
    title = item.title.strip().rstrip(".")
    label = seal.check_label((item.data or {}).get("ref"))
    origin = (item.data or {}).get("origin")
    where = {
        "facebook": " sur Facebook",
        "whatsapp": " sur WhatsApp",
        "tiktok": " sur TikTok",
        "radio": " à la radio",
    }.get(origin or "", "")
    on_air = f" C'est la {label}, sur {_bare(link)}." if label else ""
    detail = (
        f"Le détail de la {label} est sur {link}."
        if label
        else f"Le détail de notre vérification est sur {link}."
    )
    flash_words = (
        f"Flash vérification de {ws.name}. Une information circule{where} : « {title} ». "
        f"Nous avons vérifié. Notre conclusion : {word.lower()}. {reason} "
        "Avant de partager un message, demandez-vous d'où il vient et qui l'a publié en premier. "
        f"{detail}"
    ).split()
    sms_tail = f"({label}) {link}" if label else link
    return {
        "radio_line": f"{ws.name} a vérifié l'information selon laquelle « {title} ». "
        f"Conclusion : {word.lower()}. {reason}{on_air}",
        "flash": " ".join(flash_words[:110]),
        "sms": _fit_sms(f"{word.upper()} : {title}.", sms_tail),
        "text": f"{word} · {ws.name}\n« {title} »\n\n{reason}\n\n"
        + (f"{label[0].upper()}{label[1:]} : {url}" if label else url),
        "institution_alert": (
            f"Bonjour, {ws.name} a publié une vérification qui vous concerne : « {title} »"
            + (f" ({label})" if label else "")
            + f". Conclusion : {word.lower()}. {reason} Le détail : {url}. Si vous publiez un "
            "démenti ou une précision, merci de nous l'envoyer : nous l'ajouterons au dossier."
        ),
        "mg": None,
    }


def _clean_model(
    raw: dict, facts: str, link: str, fallback: dict[str, Any], ref: str | None = None
) -> dict[str, Any]:
    """Keep a model field only when it is plausible: no number the facts do not hold, the SMS
    under 160 characters with its link, the flash around 75 words. Otherwise the template. The
    verification number is added by code where the model left it out."""
    known = _numbers(facts)
    out = dict(fallback)

    def ok(text: str) -> bool:
        return bool(text) and _numbers(text) <= known

    def field(key: str, text: str, lang: str = "fr") -> str:
        if not ok(text):
            return ""
        label = seal.check_label(ref, lang)
        has = bool(label) and label.lower() in text.lower()
        if key == "sms":  # the number and the link are added by code, after the check
            for tail in ([] if has or not label else [f"({label}) {link}"]) + [link]:
                if len(text) + len(tail) < 160:
                    return f"{text} {tail}"
            return ""
        if key == "flash" and not 40 <= len(text.split()) <= 110:
            return ""
        if key in ("radio_line", "flash") and label and not has:
            text = f"{text.rstrip()} ({label})"
        return text

    for key in FORMAT_KEYS:
        if text := field(key, _plain(raw.get(key))):
            out[key] = text
    mg = raw.get("mg") if isinstance(raw.get("mg"), dict) else {}
    drafts = {k: text for k in MG_KEYS if (text := field(k, _plain(mg.get(k)), "mg"))}
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
    # The seal's URL when the newsroom can seal (SEAL_SECRET set), else the public page.
    qr_url: str
    short_link: str | None
    number: int | None = None
    check_label: str | None = None
    sealed: bool = False


class VerdictSealOut(BaseModel):
    """The newsroom's signature on the published verdict, as the card's QR carries it."""

    alg: str
    key_id: str
    public_key: str
    payload: dict[str, Any]
    message: str
    signature: str
    url: str
    number: int | None


class ReluOut(BaseModel):
    by: str
    name: str
    at: datetime
    # The fingerprint of the Malagasy strings that were reread (see `mg_hash`).
    mg_hash: str | None = None
    # The tick still covers the verdict and the Malagasy strings as they read now: a new verdict,
    # explanation or any changed Malagasy word unlocks nothing, it needs reading again.
    current: bool


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
    # « vérification 145 »: the same number on every format, resolved by /v/145.
    number: int | None = None
    check_label: str | None = None
    seal: VerdictSealOut | None = None
    # The fingerprint of the Malagasy formats shown here (`mg_hash`), which « Relu en malgache »
    # sends back: the reread vouches for these exact strings, and any change locks them again.
    mg_hash: str | None = None
    # Who ticked « Relu en malgache » for these strings; Malagasy formats stay locked until then.
    relu_mg: ReluOut | None = None
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


async def render(item: Item, ws: Workspace, reason: str) -> tuple[dict[str, Any], str]:
    """Every format of the signed verdict and who wrote it (`ai` or `template`): written once by the
    model (one call, kept in memory until the verdict or its explanation change) or by templates
    when AI is off or busy. The same function feeds the panel, the reread and the sending."""
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
            "numéro de vérification": seal.check_label((item.data or {}).get("ref")),
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
                formats, written_by = (
                    _clean_model(raw, facts, link, base, (item.data or {}).get("ref")),
                    "ai",
                )
                if len(_WRITTEN) >= 256:
                    _WRITTEN.pop(next(iter(_WRITTEN)))
                _WRITTEN[key] = {k: formats.get(k) for k in (*FORMAT_KEYS, "mg")}
        except (ai.AiUnavailable, ValueError):
            pass
    return formats, written_by


@router.get("/workspaces/{ws}/items/{item_id}/diffusion")
async def diffusion(item_id: uuid.UUID, member: AnyMember, db: Db) -> FormatsOut:
    """Every format of the signed verdict (see `render`), the poster, the seal and the reread."""
    item, ws, reason = await _publishable(db, member, item_id)
    from app.modules.signing import permalink

    url = permalink(item)
    formats, written_by = await render(item, ws, reason)
    mg_now = mg_texts(item, formats)
    word = VERDICT_FR[item.data["verdict"]]
    published = dates.parse(
        (item.data or {}).get("published_at") or (item.data or {}).get("signed_at")
    )
    trajet_now = await read_trajet(db, item)
    sealed = await verdict_seal(db, item, ws)
    if sealed:
        await db.commit()  # the newsroom's key, created on first use
    ref = (item.data or {}).get("ref")
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
            qr_url=sealed["url"] if sealed else url,
            short_link=short_link(item),
            number=seal.check_number(ref),
            check_label=seal.check_label(ref),
            sealed=bool(sealed),
        ),
        mg=formats.get("mg"),
        written_by=written_by,
        gaps=trajet_now.gaps,
        number=seal.check_number(ref),
        check_label=seal.check_label(ref),
        mg_hash=mg_hash(mg_now),
        relu_mg=relu_of(item, mg_now),
        seal=VerdictSealOut(**{k: sealed[k] for k in VerdictSealOut.model_fields})
        if sealed
        else None,
        radio=formats["radio_line"],
        social=formats["text"],
        url=url,
    )


# --- the sealed card: the newsroom signs the published verdict, a phone checks it offline -------


async def verdict_seal(db: AsyncSession, item: Item, ws: Workspace) -> dict[str, Any] | None:
    """The seal of the verdict as it reads now: None without SEAL_SECRET, a published verdict or a
    newsroom that publishes (public and verified by Checky). Flushes the newsroom's key on first
    use: the caller commits."""
    d = item.data or {}
    if (
        not seal.available()
        or not ws.publishes
        or item.status != "published"
        or d.get("verdict") not in VERDICT_FR
    ):
        return None
    from app.modules.signing import digest

    signed = (
        dates.parse_moment(d.get("signed_at"))
        or dates.parse_moment(d.get("published_at"))
        or item.updated_at
    )
    return await seal.sign_verdict(
        db,
        ws.id,
        item_id=item.id,
        ref=d.get("ref"),
        verdict=d["verdict"],
        title=item.title,
        signed_at=signed,
        digest=digest(item.title, item.body, d),
    )


@router.get("/workspaces/{ws}/items/{item_id}/seal")
async def item_seal(item_id: uuid.UUID, member: AnyMember, db: Db) -> VerdictSealOut:
    """The QR of the card and the story: the newsroom's signature over the published verdict."""
    item = await _get_item(db, member, item_id)
    if item.status != "published" or (item.data or {}).get("verdict") not in VERDICT_FR:
        raise ApiError(409, "not_published", "Publish a newsroom verdict first")
    ws = await db.get(Workspace, member.workspace_id)
    if not ws.publishes:
        raise ApiError(
            409, "private_workspace", "Only a public, verified newsroom seals its verdict cards"
        )
    sealed = await verdict_seal(db, item, ws)
    if sealed is None:
        raise ApiError(503, "seal_unavailable", "Sealing is not configured on this server")
    await db.commit()
    return VerdictSealOut(**{k: sealed[k] for k in VerdictSealOut.model_fields})


class PublicVerdictSealOut(VerdictSealOut):
    item_id: uuid.UUID
    ref: str | None
    title: str
    verdict: str
    check_label: str | None
    newsroom: dict[str, str]
    published_url: str


class SealCheckIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=10, max_length=2000)
    signature: str = Field(min_length=10, max_length=200)
    key_id: str = Field(min_length=3, max_length=40)


class SealCheckOut(BaseModel):
    valid: bool
    revoked: bool
    # The fragment's version is still the one published (same verdict, same fingerprint).
    current: bool
    newsroom: dict[str, str] | None


_SEAL_CHECKS: dict[str, deque[float]] = defaultdict(deque)
SEAL_LIMIT, SEAL_WINDOW = 60, 600.0


def _seal_rate(request: Request) -> None:
    from app.modules.public import _allow

    addr = request.client.host if request.client else "unknown"
    if not _allow(_SEAL_CHECKS, addr, SEAL_LIMIT, SEAL_WINDOW):
        raise ApiError(429, "too_many_checks", "Too many checks, try again in a few minutes")


async def _public_item(db: AsyncSession, item_id: uuid.UUID) -> tuple[Item, Workspace]:
    from app.modules.public import _published

    row = (await db.execute(_published().where(Item.id == item_id))).first()
    if row is None:
        raise ApiError(404, "not_found", "Verdict not found")
    return row[0], row[1]


@router.get("/public/sceau/v/{item_id}")
async def public_verdict_seal(item_id: uuid.UUID, request: Request, db: Db) -> PublicVerdictSealOut:
    """The seal of a published verdict as it reads now, to compare with a card's QR. Only a public
    newsroom's published verdict; nothing of the dossier beyond what its public page shows."""
    _seal_rate(request)
    item, ws = await _public_item(db, item_id)
    sealed = await verdict_seal(db, item, ws)
    if sealed is None:
        raise ApiError(404, "not_sealed", "This verdict has no seal")
    await db.commit()
    from app.modules.signing import permalink

    d = item.data or {}
    return PublicVerdictSealOut(
        **{k: sealed[k] for k in VerdictSealOut.model_fields},
        item_id=item.id,
        ref=d.get("ref"),
        title=item.title,
        verdict=d["verdict"],
        check_label=seal.check_label(d.get("ref")),
        newsroom={"slug": ws.slug, "name": ws.name},
        published_url=permalink(item),
    )


@router.post("/public/sceau/v/{item_id}/verify")
async def verify_verdict_seal(
    item_id: uuid.UUID, body: SealCheckIn, request: Request, db: Db
) -> SealCheckOut:
    """The server-side check, for browsers without Ed25519 in WebCrypto: the QR's message and
    signature against the key it names, and whether that version is still the published one."""
    from app.core.models import SealKey

    _seal_rate(request)
    row = (
        await db.execute(
            select(SealKey, Workspace)
            .join(Workspace, Workspace.id == SealKey.workspace_id)
            .where(SealKey.key_id == body.key_id, Workspace.publishes)
        )
    ).first()
    if row is None:
        return SealCheckOut(valid=False, revoked=False, current=False, newsroom=None)
    key, ws = row
    valid = seal.verify_message(key.public_key, body.message, body.signature)
    found = seal.read_fragment(f"{seal.b64u(body.message.encode())}.x.y")
    # Only a verdict seal (domain-separated) of this very verdict vouches for this page, and only
    # with the newsroom's verdict key, never an issuer's.
    valid = (
        valid
        and key.issuer == seal.NEWSROOM_ISSUER
        and bool(found)
        and found[0].get("id") == str(item_id)
    )
    current = False
    if valid:
        try:
            item, _ = await _public_item(db, item_id)
            now = await verdict_seal(db, item, ws)
            current = bool(now) and now["message"] == body.message
        except ApiError:
            current = False
    return SealCheckOut(
        valid=valid,
        revoked=key.revoked_at is not None,
        current=current,
        newsroom={"slug": ws.slug, "name": ws.name},
    )


MG_FORMATS = {"card_mg", "radio_line_mg", "sms_mg", "text_mg"}


# --- « Relu en malgache »: a speaker reread these exact Malagasy strings; logged with who and when
#
# The reread is bound to the text: the journalist sends back the `mg_hash` of the formats they
# read, the attestation keeps those strings and their hash, and every later use renders the formats
# again and compares. Only the attested strings go out; any changed character locks them again.


def _version(item: Item) -> str:
    from app.modules.signing import digest

    return digest(item.title, item.body, item.data or {})


def mg_texts(item: Item, formats: dict[str, Any]) -> dict[str, str]:
    """The Malagasy formats exactly as the panel shows them, by format id (`sms_mg`, `card_mg`…)."""
    mg = formats.get("mg") if isinstance(formats.get("mg"), dict) else {}
    out = {f"{k}_mg": mg[k] for k in MG_KEYS if isinstance(mg.get(k), str) and mg[k]}
    card = _posts(item).get("mg")
    if isinstance(card, str) and card:
        out["card_mg"] = card
    return out


def mg_hash(texts: dict[str, str] | None) -> str | None:
    """SHA-256 of the canonical serialisation (sorted keys, no spaces, UTF-8 kept as is) of the
    exact strings. Nothing is normalised: a changed letter, accent or space is another hash."""
    if not texts:
        return None
    return hashlib.sha256(seal.canonical(texts).encode()).hexdigest()


def _attested(item: Item) -> dict[str, Any] | None:
    r = (item.data or {}).get("relu_mg")
    return r if isinstance(r, dict) and r.get("by") else None


def _still_covers(r: dict[str, Any], item: Item, texts: dict[str, str] | None) -> bool:
    """The reread covers this verdict version and these strings, character for character."""
    kept = r.get("texts")
    if r.get("digest") != _version(item) or not texts or not isinstance(kept, dict):
        return False
    return r.get("mg_hash") == mg_hash(kept) == mg_hash(texts)


def relu_of(item: Item, texts: dict[str, str] | None) -> ReluOut | None:
    """The reread on record. `texts` are the Malagasy formats as rendered now (None when they cannot
    be rendered): `current` only when the attestation still covers them exactly."""
    r = _attested(item)
    if r is None:
        return None
    return ReluOut(
        by=r["by"],
        name=r.get("name") or "",
        at=r["at"],
        mg_hash=r.get("mg_hash"),
        current=_still_covers(r, item, texts),
    )


def attested_texts(item: Item, texts: dict[str, str] | None) -> dict[str, str]:
    """The strings the reread vouches for, when it still covers `texts`; otherwise nothing."""
    r = _attested(item)
    return dict(r["texts"]) if r and _still_covers(r, item, texts) else {}


async def _mark_relu(db: AsyncSession, member, item: Item, texts: dict[str, str]) -> None:
    from app.modules.signing import names

    name = (await names(db, [member.user.id])).get(member.user.id) or member.user.email or ""
    at = datetime.now(UTC).isoformat()
    h = mg_hash(texts)
    item.data = {
        **(item.data or {}),
        "relu_mg": {
            "by": member.user.id,
            "name": name,
            "at": at,
            "digest": _version(item),
            "mg_hash": h,
            "texts": dict(texts),
        },
    }
    await record(
        db,
        member.workspace_id,
        member.user.id,
        "item",
        item.id,
        "relu_mg",
        {
            "carnet": "Formats en malgache relus par un locuteur",
            "at": at,
            "formats": sorted(texts),
            "mg_hash": h,
        },
    )


class ReluState(BaseModel):
    relu_mg: ReluOut | None


class ReluIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # The `mg_hash` of the diffusion that was read: the reread vouches for those strings only.
    mg_hash: str = Field(min_length=64, max_length=64)


async def _mg_now(db: AsyncSession, member, item_id: uuid.UUID) -> tuple[Item, dict[str, str]]:
    """The dossier and its Malagasy formats rendered now, as the panel would show them."""
    item, ws, reason = await _publishable(db, member, item_id)
    formats, _ = await render(item, ws, reason)
    return item, mg_texts(item, formats)


@router.get("/workspaces/{ws}/items/{item_id}/relu-mg")
async def relu_state(item_id: uuid.UUID, member: AnyMember, db: Db) -> ReluState:
    try:
        item, texts = await _mg_now(db, member, item_id)
    except ApiError:
        item, texts = await _get_item(db, member, item_id), None
    return ReluState(relu_mg=relu_of(item, texts))


@router.post("/workspaces/{ws}/items/{item_id}/relu-mg")
async def mark_relu(item_id: uuid.UUID, body: ReluIn, member: AnyMember, db: Db) -> ReluState:
    """« Relu en malgache »: the journalist read the Malagasy formats (lines, SMS, post, card) and
    vouches for these exact strings (`mg_hash`). Until then they cannot be copied or sent, and any
    change to them afterwards locks them again."""
    item, texts = await _mg_now(db, member, item_id)
    if not texts:
        raise ApiError(409, "no_mg_formats", "There is no Malagasy format to reread")
    if body.mg_hash != mg_hash(texts):
        raise ApiError(
            409, "mg_changed", "The Malagasy formats changed since they were read: read them again"
        )
    if not attested_texts(item, texts):
        await _mark_relu(db, member, item, texts)
        await db.commit()
        await db.refresh(item)
        await broadcast(member.workspace_id, "item.updated", _out(item))
    return ReluState(relu_mg=relu_of(item, texts))


async def _verdict_item(db: AsyncSession, member, item_id: uuid.UUID) -> Item:
    item = await _get_item(db, member, item_id)
    if (item.data or {}).get("verdict") not in VERDICT_FR:
        raise ApiError(409, "no_verdict", "Confirm a verdict before rereading its formats")
    return item


@router.delete("/workspaces/{ws}/items/{item_id}/relu-mg")
async def clear_relu(item_id: uuid.UUID, member: AnyMember, db: Db) -> ReluState:
    item = await _verdict_item(db, member, item_id)
    if (item.data or {}).get("relu_mg"):
        item.data = {k: v for k, v in (item.data or {}).items() if k != "relu_mg"}
        await record(
            db,
            member.workspace_id,
            member.user.id,
            "item",
            item.id,
            "relu_mg_undo",
            {"carnet": "Relecture en malgache retirée : les formats malgaches sont verrouillés"},
        )
        await db.commit()
        await db.refresh(item)
        await broadcast(member.workspace_id, "item.updated", _out(item))
    return ReluState(relu_mg=None)


class DiffuseRoute(BaseModel):
    model_config = ConfigDict(extra="forbid")
    channel: Channel
    place: str = Field(min_length=1, max_length=300)
    location: dict[str, Any] | None = None


class DiffuseIn(BaseModel):
    routes: list[DiffuseRoute] = Field(min_length=1, max_length=20)
    formats: list[str] = Field(default_factory=list, max_length=12)
    # Ticking « Relu en malgache » in the same gesture: it counts only with the `mg_hash` of the
    # strings that were read, and only while they are still the ones rendered.
    relu_mg: bool = False
    mg_hash: str | None = Field(default=None, max_length=64)


class DiffuseOut(BaseModel):
    trajet: TrajetOut
    formats: list[str]
    dropped: list[str]
    # The Malagasy strings that went out: exactly the reread ones, and their fingerprint.
    mg: dict[str, str] = Field(default_factory=dict)
    mg_hash: str | None = None


@router.post("/workspaces/{ws}/items/{item_id}/diffuse")
async def diffuse(item_id: uuid.UUID, body: DiffuseIn, member: AnyMember, db: Db) -> DiffuseOut:
    """The journalist sent the formats down these routes (from their own phone, radio or print
    shop): each becomes a truth stop `sent`. Malagasy formats go only as a speaker reread them:
    rendered again here, they must match the attested strings exactly, or they stay locked."""
    item, ws, reason = await _publishable(db, member, item_id)
    rendered, _ = await render(item, ws, reason)
    texts = mg_texts(item, rendered)
    if (
        body.relu_mg
        and not attested_texts(item, texts)
        and texts
        and body.mg_hash == mg_hash(texts)
    ):
        await _mark_relu(db, member, item, texts)
    attested = attested_texts(item, texts)
    wanted = list(dict.fromkeys(body.formats))
    # The journalist's voice note goes out only when the dossier has one.
    has_voice = bool((item.data or {}).get("voice_note"))
    kept = [
        f
        for f in wanted
        if (f not in MG_FORMATS or f in attested) and (f != "voice_note" or has_voice)
    ]
    dropped = [f for f in wanted if f not in kept]
    sent_mg = {f: attested[f] for f in kept if f in MG_FORMATS}
    sent_hash = mg_hash(attested) if sent_mg else None
    for r in body.routes:
        await add_stop(
            db,
            ws.id,
            item.id,
            side="truth",
            channel=r.channel,
            place=r.place,
            location=r.location,
            proof={
                "formats": kept,
                "relu_mg": bool(attested),
                "mg_hash": sent_hash,
                "method": "diffuser",
            },
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
        {
            "routes": [r.model_dump(mode="json") for r in body.routes],
            "formats": kept,
            "mg_hash": sent_hash,
        },
    )
    await db.commit()
    out = await read_trajet(db, item)
    await broadcast(ws.id, "route.added", {"item_id": str(item.id)})
    return DiffuseOut(trajet=out, formats=kept, dropped=dropped, mg=sent_mg, mg_hash=sent_hash)


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
