"""« Ma rubrique »: a journalist's morning page, plus the carnet's Angles and Documents.

A journalist covers beats (énergie, santé…: the newsroom's own list, `workspace.settings.beats`,
or the defaults) and places. The morning page gathers what circulates on them (tips, SMS
questions, radio clips, press items, the desk's open claims), the dossiers waiting for them or for
a signature, who to call, the latest official figures, three angles and the week's « Météo des
rumeurs ». `…/rubrique/brief` says the same as a short text to paste into WhatsApp or an SMS.

Angles (« Explorer un angle ») are the one model call here: grounded in the newsroom's own facts,
each angle must rest on numbered facts and is shown dashed: the AI suggests, a journalist keeps.
"""

import json
import logging
import re
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import ai, dates, seasons
from app.core.access import AnyMember, Anyone, Db, Member
from app.core.activity import broadcast, record
from app.core.errors import ApiError
from app.core.models import (
    DEFAULT_BEATS,
    Communique,
    Contact,
    Figure,
    Item,
    MemberPref,
    PublicQuestion,
    Source,
    Workspace,
)
from app.core.places import MG_REGIONS, fold
from app.core.words import words
from app.modules.items import ItemOut, _get_item, _out

log = logging.getLogger("checky.rubrique")
router = APIRouter(tags=["rubrique"])

WEEKDAYS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")
CIRCULATING_HOURS = 48
FIGURE_OLD_DAYS = 730
# Words that put a text in a beat when nobody tagged it (French, Malagasy, a little English).
# Beats are the newsroom's; a beat with no entry here matches on its own name only.
BEAT_WORDS: dict[str, tuple[str, ...]] = {
    "santé": ("santé", "peste", "choléra", "épidémie", "vaccin", "hôpital", "malade", "paludisme",
              "médicament", "mpox", "pesta", "aretina", "fahasalamana", "eau du robinet",
              "empoisonné", "empoisonnée"),
    "éducation": ("éducation", "bac", "baccalauréat", "examen", "cepe", "bepc", "école", "élèves",
                  "enseignants", "rentrée", "université", "fianarana", "sekoly"),
    "politique": ("politique", "élection", "élections", "ministre", "président", "député",
                  "gouvernement", "ceni", "vote", "maire", "sénat", "fifidianana"),
    "économie": ("économie", "prix", "riz", "vary", "ariary", "salaire", "inflation", "billet",
                 "taxe", "banque", "pénurie", "vidin-javatra"),
    "énergie": ("énergie", "délestage", "jirama", "électricité", "coupure de courant",
                "carburant", "centrale", "tarif", "jiro", "fahatapahan-jiro", "herinaratra",
                "solika"),
    "sécurité": ("sécurité", "enlèvement", "dahalo", "attaque", "police", "gendarmerie",
                 "meurtre", "kidnapping", "braquage", "fakana an-keriny", "mpangalatra"),
    "environnement": ("environnement", "cyclone", "inondation", "crue", "sécheresse", "feux",
                      "forêt", "bngrc", "rivodoza", "tondra-drano"),
    "transport": ("transport", "pont", "route", "taxi-be", "bus", "aéroport", "train", "rn7",
                  "circulation", "lalana"),
    "sport": ("sport", "barea", "match", "football", "rugby", "makis", "baolina"),
    "culture": ("culture", "festival", "concert", "artiste", "musique", "film"),
    "société": ("société", "fokontany", "mariage", "église", "religion", "eau", "logement"),
    "international": ("international", "onu", "oms", "union africaine", "france", "chine",
                      "comores", "maurice"),
}  # fmt: skip
DOCUMENT_WORDS = (
    "loi", "décret", "arrêté", "ordonnance", "circulaire", "décision", "rapport", "budget",
    "communiqué", "recensement", "enquête", "note", "relevé", "calendrier", "programme",
    "plan", "convention", "statuts", "bulletin officiel", "journal officiel",
)  # fmt: skip


# ----------------------------------------------------------------------------------- beats
def offered_beats(workspace: Workspace | None) -> list[str]:
    beats = (workspace.settings or {}).get("beats") if workspace else None
    if isinstance(beats, list) and any(isinstance(b, str) and b.strip() for b in beats):
        return [b.strip() for b in beats if isinstance(b, str) and b.strip()]
    return list(DEFAULT_BEATS)


def _contains(folded: str, phrase: str) -> bool:
    return bool(re.search(rf"(?<![a-z0-9]){re.escape(fold(phrase))}(?:s|x)?(?![a-z0-9])", folded))


def beats_for(text: str, offered: list[str]) -> list[str]:
    """The newsroom's beats a text belongs to, by their name or their usual words."""
    folded = fold(text or "")
    if not folded:
        return []
    out = []
    for beat in offered:
        lexicon = BEAT_WORDS.get(beat) or BEAT_WORDS.get(fold(beat)) or (beat,)
        if any(_contains(folded, w) for w in (beat, *lexicon)):
            out.append(beat)
    return out


def _same(a: str, b: str) -> bool:
    return fold(a) == fold(b)


# ----------------------------------------------------------------------------------- prefs
class PrefsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    beats: list[str] = Field(default_factory=list, max_length=20)
    # Place names: a region, a town (« Toamasina » counts as Atsinanana), any place in the world.
    regions: list[str] = Field(default_factory=list, max_length=30)
    language: Literal["fr", "mg", "en"] = "fr"
    station: str | None = Field(default=None, max_length=120)  # a veilleur's radio


class PrefsOut(PrefsIn):
    beats_offered: list[str]
    regions_offered: list[str]


async def load_prefs(db: AsyncSession, member: Member) -> MemberPref | None:
    return await db.scalar(
        select(MemberPref).where(
            MemberPref.workspace_id == member.workspace_id, MemberPref.user_id == member.user.id
        )
    )


def _clean(values: list[str], limit: int) -> list[str]:
    out: list[str] = []
    for v in values:
        v = re.sub(r"\s+", " ", v or "").strip()[:80]
        if v and not any(_same(v, o) for o in out):
            out.append(v)
    return out[:limit]


def _prefs_out(pref: MemberPref | None, workspace: Workspace) -> PrefsOut:
    return PrefsOut(
        beats=list(pref.beats or []) if pref else [],
        regions=list(pref.regions or []) if pref else [],
        language=(pref.language if pref and pref.language in ("fr", "mg", "en") else "fr"),
        station=pref.station if pref else None,
        beats_offered=offered_beats(workspace),
        regions_offered=sorted(MG_REGIONS),
    )


@router.get("/workspaces/{ws}/me/prefs")
async def get_prefs(member: Anyone, db: Db) -> PrefsOut:
    return _prefs_out(await load_prefs(db, member), await db.get(Workspace, member.workspace_id))


async def save_prefs(db: AsyncSession, workspace_id: uuid.UUID, user_id: str, body: PrefsIn):
    from app.modules.veille import canonical_region

    beats = _clean(body.beats, 20)
    regions = _clean([canonical_region(r) or r for r in body.regions], 30)
    values = {
        "beats": beats,
        "regions": regions,
        "language": body.language,
        "station": (body.station or "").strip() or None,
    }
    await db.execute(
        insert(MemberPref)
        .values(id=uuid.uuid4(), workspace_id=workspace_id, user_id=user_id, **values)
        .on_conflict_do_update(index_elements=["workspace_id", "user_id"], set_=values)
    )


@router.put("/workspaces/{ws}/me/prefs")
async def put_prefs(body: PrefsIn, member: Anyone, db: Db) -> PrefsOut:
    await save_prefs(db, member.workspace_id, member.user.id, body)
    await db.commit()
    return await get_prefs(member, db)


# -------------------------------------------------------------------------------- the page
class Circulating(BaseModel):
    id: str
    kind: Literal["item", "tip", "sms", "clip", "press"]
    title: str
    at: datetime
    place: dict[str, Any] | None
    station: str | None = None
    url: str | None = None
    beats: list[str]
    item: ItemOut | None = None  # a dossier: the page draws its numbered line
    item_id: uuid.UUID | None = None
    already_checked: dict[str, Any] | None = None
    seasons: list[str] = []
    demo: bool = False


class ContactCard(BaseModel):
    id: uuid.UUID
    name: str
    role: str
    institution: str
    topics: list[str]
    phone: str | None
    whatsapp: str | None
    email: str | None
    website: str | None
    region: str | None
    verified: bool
    is_demo: bool


class FigureCard(BaseModel):
    id: uuid.UUID
    topic: str
    label: str
    value: str
    unit: str | None
    as_of: str | None
    source_name: str
    source_url: str | None
    age_days: int | None
    old: bool
    is_demo: bool


class AngleCard(BaseModel):
    title: str
    why: str
    rests_on: list[dict[str, Any]] = []
    missing_figure: str | None = None
    item_id: uuid.UUID | None = None
    ref: str | None = None
    # kept: a journalist kept it on a dossier; piste: drawn by code from the season and the desk
    kind: Literal["kept", "piste"]


class RubriqueOut(BaseModel):
    today: str
    today_label: str
    beats: list[str]
    regions: list[str]
    prefs: PrefsOut
    circulating: list[Circulating]
    mine: list[ItemOut]
    to_sign: list[ItemOut]
    contacts: list[ContactCard]
    figures: list[FigureCard]
    angles: list[AngleCard]
    meteo: dict[str, Any]
    antenne: list[dict[str, Any]]


def today_label(day: date | None = None) -> str:
    """« lundi 2 novembre 2026 », in Madagascar time."""
    day = day or dates.today()
    return f"{WEEKDAYS[day.weekday()]} {dates.fr(day)}"


def _region_keys(regions: list[str]) -> set[str]:
    from app.modules.veille import canonical_region

    return {fold(canonical_region(r) or r) for r in regions}


def _score(beats_hit: list[str], region: str | None, beats: list[str], regions: set[str]) -> int:
    """2 when an entry is on my beat and in my place, 1 for either, 0 for neither. With no
    preference at all everything counts."""
    if not beats and not regions:
        return 1
    on_beat = bool(beats) and any(_same(b, m) for b in beats_hit for m in beats)
    in_place = bool(regions) and bool(region) and fold(region) in regions
    return int(on_beat) + int(in_place)


async def circulating(
    db: AsyncSession,
    workspace: Workspace,
    beats: list[str],
    regions: list[str],
    weather: dict[str, Any] | None = None,
    limit: int = 12,
) -> list[Circulating]:
    """What circulates on my beats and places in the last 48 hours: the desk's open claims (tips
    included) and the SMS questions, radio clips and press items not yet in a dossier."""
    from app.modules.veille import _place_out, feed_entries, item_location

    offered = offered_beats(workspace)
    since = datetime.now(UTC) - timedelta(hours=CIRCULATING_HOURS)
    keys = _region_keys(regions)
    weather_now = (weather or await seasons.meteo(db, workspace, beats=beats))["seasons"]
    scored: list[tuple[int, Circulating]] = []
    followed: set[uuid.UUID] = set()
    for item in await db.scalars(
        select(Item).where(
            Item.workspace_id == workspace.id, Item.type == "claim", Item.created_at >= since
        )
    ):
        d = item.data or {}
        at = dates.parse_moment(d.get("first_seen_at")) or item.created_at
        if at < since:
            continue
        place = _place_out(item_location(item))
        hit = sorted(
            {t for t in item.tags or [] if any(_same(t, o) for o in offered)}
            | set(beats_for(f"{item.title} {item.body}", offered))
        )
        score = _score(hit, (place or {}).get("region"), beats, keys)
        followed.add(item.id)
        if score:
            text = f"{item.title} {item.body}"
            scored.append(
                (
                    score,
                    Circulating(
                        id=f"item:{item.id}",
                        kind="tip" if d.get("public_tip") else "item",
                        title=item.title,
                        at=at,
                        place=place,
                        url=d.get("tip_url"),
                        beats=hit,
                        item=ItemOut.model_validate(item),
                        item_id=item.id,
                        seasons=seasons.matching(weather_now, text),
                        demo=bool(d.get("demo")),
                    ),
                )
            )
    for e in await feed_entries(db, workspace, days=2):
        if e.kind == "tip" or (e.item_id and e.item_id in followed) or e.at < since:
            continue
        score = _score(e.beats, (e.place or {}).get("region"), beats, keys)
        if score:
            scored.append(
                (
                    score,
                    Circulating(
                        id=e.id,
                        kind=e.kind,
                        title=e.title,
                        at=e.at,
                        place=e.place,
                        station=e.station,
                        url=e.url,
                        beats=e.beats,
                        item_id=e.item_id,
                        already_checked=e.already_checked.model_dump(mode="json")
                        if e.already_checked
                        else None,
                        seasons=seasons.matching(weather_now, f"{e.title} {e.text}"),
                        demo=e.demo,
                    ),
                )
            )
    scored.sort(key=lambda r: (r[0], r[1].at), reverse=True)
    return [c for _, c in scored[:limit]]


async def _contacts(
    db: AsyncSession, workspace_id: uuid.UUID, beats: list[str], regions: list[str]
) -> list[ContactCard]:
    """Who to call for my beats: the Annuaire's best matches (topics, then place)."""
    try:
        from app.modules import directory

        top = getattr(directory, "top_contacts", None)
        if top is not None:
            return [ContactCard(**c) for c in await top(db, workspace_id, beats, regions, 3)]
    except Exception:  # noqa: BLE001 - the Annuaire is another shelf; the page goes on without it
        log.warning("directory.top_contacts failed; falling back to the Contact table")
    rows = await db.scalars(
        select(Contact).where(or_(Contact.workspace_id == workspace_id, Contact.shared.is_(True)))
    )
    keys = _region_keys(regions)
    scored = []
    for c in rows:
        topics = [fold(t) for t in c.topics or []]
        on_beat = any(fold(b) in topics for b in beats)
        region = (c.location or {}).get("region")
        in_place = bool(region) and fold(region) in keys
        score = 2 * on_beat + in_place + 0.5 * bool(c.verified_at)
        if beats and not on_beat:
            continue
        scored.append((score, c))
    scored.sort(key=lambda r: (r[0], (r[1].stats or {}).get("answered", 0)), reverse=True)
    return [
        ContactCard(
            id=c.id,
            name=c.name,
            role=c.role or "",
            institution=c.institution or "",
            topics=list(c.topics or []),
            phone=c.phone,
            whatsapp=c.whatsapp,
            email=c.email,
            website=c.website,
            region=(c.location or {}).get("region"),
            verified=bool(c.verified_at),
            is_demo=bool(c.is_demo),
        )
        for _, c in scored[:3]
    ]


def _as_of(value: str | None) -> date | None:
    if not value:
        return None
    if re.fullmatch(r"\d{4}", value):
        return date(int(value), 12, 31)
    return dates.parse(value)


async def _figures(db: AsyncSession, workspace_id: uuid.UUID, beats: list[str]) -> list[FigureCard]:
    """The latest official figures on my beats, with their age (old past two years)."""
    rows = await db.scalars(
        select(Figure).where(
            or_(Figure.workspace_id == workspace_id, Figure.workspace_id.is_(None))
        )
    )
    today = dates.today()
    picked = []
    for f in rows:
        hay = {fold(f.topic), *(fold(k) for k in f.keywords or [])}
        if beats and not any(fold(b) in hay for b in beats):
            continue
        seen = _as_of(f.as_of)
        age = (today - seen).days if seen else None
        picked.append(
            FigureCard(
                id=f.id,
                topic=f.topic,
                label=f.label,
                value=f.value,
                unit=f.unit,
                as_of=f.as_of,
                source_name=f.source_name,
                source_url=f.source_url,
                age_days=max(age, 0) if age is not None else None,
                old=age is not None and age > FIGURE_OLD_DAYS,
                is_demo=bool(f.is_demo),
            )
        )
    picked.sort(key=lambda f: (f.age_days is None, f.age_days or 0))
    return picked[:4]


async def _angles(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    beats: list[str],
    weather: dict[str, Any],
    offered: list[str],
) -> list[AngleCard]:
    """Three angles: those journalists kept on dossiers of my beats, then pistes drawn by code
    from the season and « Ça revient » (no model call on a page load)."""
    out: list[AngleCard] = []
    rows = await db.scalars(
        select(Item)
        .where(Item.workspace_id == workspace_id, Item.data.has_key("angles"))
        .order_by(Item.updated_at.desc())
        .limit(30)
    )
    for item in rows:
        hit = set(item.tags or []) | set(beats_for(item.title, offered))
        if beats and not any(_same(b, h) for b in beats for h in hit):
            continue
        for kept in reversed((item.data or {}).get("angles") or []):
            if isinstance(kept, dict) and kept.get("title"):
                out.append(
                    AngleCard(
                        title=str(kept["title"])[:200],
                        why=str(kept.get("why") or "")[:500],
                        rests_on=[r for r in kept.get("rests_on") or [] if isinstance(r, dict)],
                        missing_figure=kept.get("missing_figure"),
                        item_id=item.id,
                        ref=(item.data or {}).get("ref"),
                        kind="kept",
                    )
                )
    for season in weather.get("seasons") or []:
        out.append(
            AngleCard(
                title=f"{season['name']} : les rumeurs qui reviennent chaque année",
                why=season["note"],
                rests_on=[{"kind": "season", "label": season["name"]}],
                kind="piste",
            )
        )
    for back in weather.get("returning") or []:
        out.append(
            AngleCard(
                title=f"Ce qui avait circulé à la même période en {back['year']}",
                why=f"« {back['title']} » : la rumeur peut revenir avec la saison.",
                rests_on=[{"kind": "verdict", "label": back["title"], "item_id": back["id"]}],
                kind="piste",
            )
        )
    return out[:3]


async def _dossiers(
    db: AsyncSession, member: Member, beats: list[str], offered: list[str]
) -> tuple[list[ItemOut], list[ItemOut]]:
    rows = list(
        await db.scalars(
            select(Item)
            .where(
                Item.workspace_id == member.workspace_id,
                Item.type == "claim",
                Item.status != "published",
            )
            .order_by(Item.updated_at.desc())
            .limit(300)
        )
    )
    mine = [
        i
        for i in rows
        if (i.data or {}).get("assignee_id") == member.user.id
        and i.status in ("to_check", "in_progress")
    ]

    def on_beat(i: Item) -> bool:
        hit = set(i.tags or []) | set(beats_for(i.title, offered))
        return any(_same(b, h) for b in beats for h in hit)

    to_sign = [
        i
        for i in rows
        if (i.data or {}).get("verdict_suggested") and not (i.data or {}).get("verdict")
    ]
    to_sign.sort(key=lambda i: not on_beat(i))
    return (
        [ItemOut.model_validate(i) for i in mine[:5]],
        [ItemOut.model_validate(i) for i in to_sign[:5]],
    )


def _pick(override: str | None, saved: list[str]) -> list[str]:
    """An explicit `?beat=` replaces my saved beats; `*` shows every beat."""
    if override is None or not override.strip():
        return saved
    return [] if override.strip() == "*" else [override.strip()]


@router.get("/workspaces/{ws}/rubrique")
async def rubrique(
    member: AnyMember, db: Db, beat: str | None = None, region: str | None = None
) -> RubriqueOut:
    from app.modules.veille import antenne_rows

    workspace = await db.get(Workspace, member.workspace_id)
    pref = await load_prefs(db, member)
    prefs = _prefs_out(pref, workspace)
    beats = _pick(beat, prefs.beats)
    regions = _pick(region, prefs.regions)
    offered = offered_beats(workspace)
    weather = await seasons.meteo(db, workspace, regions[0] if regions else None, beats)
    mine, to_sign = await _dossiers(db, member, beats, offered)
    keys = _region_keys(regions)
    antenne = []
    for row in await antenne_rows(db, member.workspace_id):
        hit = beats_for(f"{row.claim} {row.latest.heard_text}", offered)
        if _score(hit, (row.regions_24h or [None])[0], beats, keys):
            antenne.append(row.model_dump(mode="json"))
    return RubriqueOut(
        today=dates.today().isoformat(),
        today_label=today_label(),
        beats=beats,
        regions=regions,
        prefs=prefs,
        circulating=await circulating(db, workspace, beats, regions, weather),
        mine=mine,
        to_sign=to_sign,
        contacts=await _contacts(db, member.workspace_id, beats, regions),
        figures=await _figures(db, member.workspace_id, beats),
        angles=await _angles(db, member.workspace_id, beats, weather, offered),
        meteo=weather,
        antenne=antenne[:3],
    )


VERDICT_WORDS = {
    "true": "Vrai",
    "misleading": "Trompeur",
    "false": "Faux",
    "unverifiable": "Invérifiable",
}


@router.get("/workspaces/{ws}/rubrique/brief")
async def brief(
    member: AnyMember, db: Db, beat: str | None = None, region: str | None = None
) -> dict[str, str]:
    """The morning page as a short text, for WhatsApp or an SMS. Facts only, no AI."""
    page = await rubrique(member, db, beat, region)
    head = " · ".join([*page.beats, *page.regions]) or "Toutes les rubriques"
    lines = [f"Checky · Ma rubrique · {page.today_label}", head, ""]
    if page.circulating:
        lines.append("Ce qui circule :")
        for c in page.circulating[:5]:
            where = (c.place or {}).get("name") or (c.place or {}).get("region")
            suffix = f" ({where})" if where else ""
            checked = c.already_checked or {}
            if checked.get("verdict") in VERDICT_WORDS:
                suffix += f" · déjà vérifié : {VERDICT_WORDS[checked['verdict']]}"
            elif c.item and (c.item.data or {}).get("verdict") in VERDICT_WORDS:
                suffix += f" · {VERDICT_WORDS[c.item.data['verdict']]}"
            lines.append(f"- {c.title}{suffix}")
    else:
        lines.append("Rien de nouveau sur vos rubriques depuis 48 h.")
    if page.meteo.get("seasons"):
        names = ", ".join(s["name"].lower() for s in page.meteo["seasons"][:3])
        lines += ["", f"Météo des rumeurs : {names}."]
    if page.to_sign:
        n = len(page.to_sign)
        lines.append(f"À signer : {n} dossier{'s' if n > 1 else ''}.")
    if page.mine:
        n = len(page.mine)
        lines.append(f"Pour vous : {n} dossier{'s' if n > 1 else ''} en cours.")
    return {"text": "\n".join(lines).strip()}


# ----------------------------------------------------------------------------------- angles
ANGLES_SYSTEM = (
    "Tu aides une rédaction de vérification à Madagascar à trouver des angles de reportage. "
    "Tu ne t'appuies QUE sur les faits numérotés fournis : ce sont les dossiers, les questions du "
    "public, les saisons et les chiffres de la rédaction. Propose 3 à 5 angles. Chaque angle cite "
    "au moins un fait par son numéro dans `rests_on`. N'invente aucun fait, aucun chiffre, aucun "
    "nom, aucune date. Si un chiffre officiel manque pour traiter l'angle, dis lequel dans "
    "`missing_figure` (sinon null). Réponds en français, uniquement en JSON : "
    '{"angles": [{"title": "…", "why": "…", "rests_on": [1, 3], "missing_figure": null}]}'
)
MAX_FACTS = 16


class AnglesIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    topic: str | None = Field(default=None, max_length=200)
    item_id: uuid.UUID | None = None
    region: str | None = Field(default=None, max_length=120)

    @model_validator(mode="after")
    def _something(self) -> "AnglesIn":
        if not (self.topic or "").strip() and not self.item_id:
            raise ValueError("Give a topic or a dossier")
        return self


class Fact(BaseModel):
    n: int
    kind: Literal["claim", "verdict", "season", "question", "figure", "missing"]
    label: str
    item_id: uuid.UUID | None = None


class Angle(BaseModel):
    title: str
    why: str
    rests_on: list[Fact]
    missing_figure: str | None = None


class AnglesOut(BaseModel):
    topic: str
    angles: list[Angle]
    facts: list[Fact]
    dropped: int
    model: str | None


def _relevant(text: str, topic_words: set[str], topic_beats: list[str], offered: list[str]) -> bool:
    if topic_words and words(text) & topic_words:
        return True
    return bool(topic_beats) and bool(set(beats_for(text, offered)) & set(topic_beats))


async def ground(
    db: AsyncSession, workspace: Workspace, topic: str, item: Item | None, region: str | None
) -> list[Fact]:
    """The newsroom's own facts on a topic, numbered: the dossier, recent claims, verdicts that
    come back, the season, what the public asks, and the figures available or missing."""
    offered = offered_beats(workspace)
    topic_beats = [b for b in offered if _same(b, topic)] or beats_for(topic, offered)
    topic_words = words(topic)
    facts: list[Fact] = []

    def add(kind: str, label: str, item_id: uuid.UUID | None = None) -> None:
        if len(facts) < MAX_FACTS and label.strip():
            facts.append(Fact(n=len(facts) + 1, kind=kind, label=label[:400], item_id=item_id))

    def claim_line(i: Item) -> str:
        d = i.data or {}
        seen = dates.parse(d.get("first_seen_at"))
        state = VERDICT_WORDS.get(d.get("verdict")) or {
            "to_check": "à vérifier",
            "in_progress": "en cours",
            "verified": "vérifié",
            "published": "publié",
        }.get(i.status, i.status)
        when = f", vu le {dates.fr(seen)}" if seen else ""
        return f"Dossier {d.get('ref') or ''} « {i.title} » ({state}{when})".replace("  ", " ")

    if item is not None:
        add("claim", claim_line(item), item.id)
        analysis = (item.data or {}).get("analysis") or {}
        if isinstance(analysis, dict):
            if analysis.get("reason"):
                add("claim", f"Lecture des sources : {analysis['reason']}", item.id)
            if analysis.get("missing"):
                add("missing", f"Il manque : {analysis['missing']}", item.id)
    since = datetime.now(UTC) - timedelta(days=30)
    for i in await db.scalars(
        select(Item)
        .where(
            Item.workspace_id == workspace.id,
            Item.type == "claim",
            Item.created_at >= since,
        )
        .order_by(Item.created_at.desc())
        .limit(200)
    ):
        if item is not None and i.id == item.id:
            continue
        hay = f"{i.title} {' '.join(i.tags or [])}"
        if _relevant(hay, topic_words, topic_beats, offered):
            add("claim", claim_line(i), i.id)
            missing = ((i.data or {}).get("analysis") or {}).get("missing")
            if isinstance(missing, str) and missing.strip():
                add("missing", f"Il manque ({(i.data or {}).get('ref') or ''}) : {missing}", i.id)
        if sum(f.kind == "claim" for f in facts) >= 7:
            break
    weather = await seasons.meteo(db, workspace, region, topic_beats)
    for back in weather["returning"]:
        if _relevant(back["title"], topic_words, topic_beats, offered):
            add(
                "verdict",
                f"En {back['year']}, à la même période : « {back['title']} » "
                f"({VERDICT_WORDS.get(back['verdict'], back['verdict'])})",
                uuid.UUID(back["id"]),
            )
    for s in weather["seasons"]:
        if any(_same(s["topic"], b) for b in topic_beats) or _relevant(
            f"{s['name']} {' '.join(s['keywords'])}", topic_words, [], offered
        ):
            add("season", f"Saison en cours : {s['name']} ({s['note']})")
    asked = 0
    for q in await db.scalars(
        select(PublicQuestion)
        .where(PublicQuestion.workspace_id == workspace.id, PublicQuestion.created_at >= since)
        .order_by(PublicQuestion.created_at.desc())
        .limit(100)
    ):
        if asked < 4 and _relevant(q.text, topic_words, topic_beats, offered):
            add("question", f"Question du public ({q.channel}) : « {q.text[:200]} »")
            asked += 1
    for f in await db.scalars(
        select(Figure).where(
            or_(Figure.workspace_id == workspace.id, Figure.workspace_id.is_(None))
        )
    ):
        hay = f"{f.topic} {f.label} {' '.join(f.keywords or [])}"
        if _relevant(hay, topic_words, topic_beats, offered):
            unit = f" {f.unit}" if f.unit else ""
            add(
                "figure",
                f"Chiffre disponible : {f.label} = {f.value}{unit} ({f.source_name}, {f.as_of})",
            )
    return facts


def _numbers(text: str) -> set[str]:
    return {n.replace(" ", "").replace(",", ".") for n in re.findall(r"\d[\d  ,.]*\d|\d", text)}


def clean_angles(raw: Any, facts: list[Fact], allowed_text: str) -> tuple[list[Angle], int]:
    """Keep the angles that rest on known facts and invent no number; at most five."""
    by_n = {f.n: f for f in facts}
    known_numbers = _numbers(allowed_text)
    kept, dropped = [], 0
    proposed = raw.get("angles") if isinstance(raw, dict) else None
    for a in proposed if isinstance(proposed, list) else []:
        if not isinstance(a, dict):
            dropped += 1
            continue
        title = re.sub(r"\s+", " ", str(a.get("title") or "")).strip()[:200]
        why = re.sub(r"\s+", " ", str(a.get("why") or "")).strip()[:600]
        refs = []
        for r in a.get("rests_on") or []:
            try:
                n = int(str(r).strip("[] "))
            except ValueError:
                continue
            if n in by_n and by_n[n] not in refs:
                refs.append(by_n[n])
        missing = a.get("missing_figure")
        missing = re.sub(r"\s+", " ", str(missing)).strip()[:200] if missing else None
        if not title or not refs or not _numbers(f"{title} {why}") <= known_numbers:
            dropped += 1
            continue
        kept.append(Angle(title=title, why=why, rests_on=refs, missing_figure=missing or None))
    return kept[:5], dropped + max(0, len(kept) - 5)


def _parse(content: str) -> dict[str, Any]:
    m = re.search(r"\{.*\}", content or "", re.DOTALL)
    if not m:
        raise ValueError("The model did not return JSON")
    return json.loads(m.group(0))


@router.post("/workspaces/{ws}/angles")
async def angles(body: AnglesIn, member: AnyMember, db: Db) -> AnglesOut:
    """3 to 5 story angles grounded in the newsroom's own facts. One model call; an angle that
    cites no fact or brings a number of its own is dropped. Drawn dashed: a suggestion."""
    workspace = await db.get(Workspace, member.workspace_id)
    if (workspace.settings or {}).get("ai_enabled") is False:
        raise ApiError(409, "ai_disabled", "Angles need the AI; this newsroom runs without it")
    item = await _get_item(db, member, body.item_id) if body.item_id else None
    topic = (body.topic or "").strip() or (item.title if item else "")
    facts = await ground(db, workspace, topic, item, body.region)
    if not facts:
        return AnglesOut(topic=topic, angles=[], facts=[], dropped=0, model=None)
    numbered = "\n".join(f"[{f.n}] {f.label}" for f in facts)
    try:
        reply = await ai.complete(
            [
                {"role": "system", "content": f"{ANGLES_SYSTEM}\n{dates.today_line()}"},
                {"role": "user", "content": f"Sujet : {topic}\n\nFaits :\n{numbered}"},
            ],
            workspace_id=member.workspace_id,
            temperature=0.4,
            max_tokens=1500,
            response_format={"type": "json_object"},
        )
    except ai.AiUnavailable as e:
        raise ApiError(503, "ai_unavailable", "The AI is unavailable right now") from e
    try:
        raw = _parse(reply.content)
    except (ValueError, json.JSONDecodeError):
        raw = {}
    kept, dropped = clean_angles(raw, facts, f"{topic}\n{numbered}")
    return AnglesOut(topic=topic, angles=kept, facts=facts, dropped=dropped, model=reply.model)


class KeepIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    angle: Angle


@router.post("/workspaces/{ws}/items/{item_id}/angles/keep")
async def keep_angle(item_id: uuid.UUID, body: KeepIn, member: AnyMember, db: Db) -> ItemOut:
    """A journalist keeps a suggested angle on a dossier (`item.data.angles`)."""
    item = await _get_item(db, member, item_id)
    angle = body.angle.model_dump(mode="json")
    angle.update(kept_by=member.user.id, kept_at=datetime.now(UTC).isoformat())
    previous = [a for a in (item.data or {}).get("angles") or [] if isinstance(a, dict)]
    previous = [a for a in previous if fold(a.get("title", "")) != fold(angle["title"])]
    item.data = {**(item.data or {}), "angles": [*previous, angle][-10:]}
    await record(
        db, member.workspace_id, member.user.id, "item", item.id, "angle", {"title": angle["title"]}
    )
    await db.commit()
    await db.refresh(item)
    await broadcast(member.workspace_id, "item.updated", _out(item))
    return ItemOut.model_validate(item)


# -------------------------------------------------------------------------------- documents
class CommuniqueRef(BaseModel):
    id: uuid.UUID
    issuer: str
    number: str | None
    issued_on: str | None


class DocumentOut(BaseModel):
    id: uuid.UUID
    title: str
    kind: str
    status: str
    doc_type: str
    issuer: str | None
    url: str | None
    published_at: str | None
    created_at: datetime
    item_id: uuid.UUID | None
    excerpt: str
    beats: list[str]
    communique: CommuniqueRef | None
    demo: bool


_DEMO_PREFIX = re.compile(r"^\s*d[ée]mo\s*[·:-]\s*", re.IGNORECASE)
_ISSUER = re.compile(r"\b(?:de la|de l'|du|des|de)\s+(.{3,80}?)(?:\s*\(|$| à | sur | pour )")


def document_type(title: str) -> str | None:
    """The document word a title starts with (« Communiqué du ministère… » → communiqué)."""
    head = fold(_DEMO_PREFIX.sub("", title or ""))
    for word in DOCUMENT_WORDS:
        if re.match(rf"{re.escape(fold(word))}(?![a-z0-9])", head):
            return word
    return None


def _issuer(title: str) -> str | None:
    rest = _DEMO_PREFIX.sub("", title or "")
    m = _ISSUER.search(rest)
    return m.group(1).strip(" .,") if m else None


@router.get("/workspaces/{ws}/documents")
async def documents(
    member: AnyMember, db: Db, topic: str | None = None, q: str | None = None
) -> list[DocumentOut]:
    """The newsroom's reference documents: sources whose title names a document (loi, décret,
    communiqué, rapport…) and the files of the Registre's originals, newest first."""
    workspace = await db.get(Workspace, member.workspace_id)
    offered = offered_beats(workspace)
    originals = {
        c.file_id: c
        for c in await db.scalars(
            select(Communique).where(
                Communique.workspace_id == member.workspace_id, Communique.file_id.is_not(None)
            )
        )
    }
    stmt = select(Source).where(
        Source.workspace_id == member.workspace_id, Source.kind.in_(["pdf", "text", "url"])
    )
    if q and q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Source.title.ilike(like), Source.text.ilike(like)))
    out = []
    for s in await db.scalars(stmt.order_by(Source.created_at.desc()).limit(500)):
        original = originals.get(s.file_id) if s.file_id else None
        kind = document_type(s.title) or ("communiqué" if original else None)
        if not kind:
            continue
        text = f"{s.title} {s.text[:3000]}"
        hit = beats_for(text, offered)
        if (
            topic
            and topic.strip()
            and not (any(_same(topic, b) for b in hit) or words(topic) & words(text))
        ):
            continue
        out.append(
            DocumentOut(
                id=s.id,
                title=s.title,
                kind=s.kind,
                status=s.status,
                doc_type=kind,
                issuer=original.issuer if original else _issuer(s.title),
                url=s.url,
                published_at=s.published_at,
                created_at=s.created_at,
                item_id=s.item_id,
                excerpt=re.sub(r"\s+", " ", s.text[:280]).strip(),
                beats=hit,
                communique=CommuniqueRef(
                    id=original.id,
                    issuer=original.issuer,
                    number=original.number,
                    issued_on=original.issued_on,
                )
                if original
                else None,
                demo=bool(_DEMO_PREFIX.match(s.title or "")) or "exemple fictif" in s.title,
            )
        )
    return out


# ------------------------------------------------------------------------------- demo seed
