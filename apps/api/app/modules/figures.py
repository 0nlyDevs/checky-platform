"""« Chiffres »: official figures, each dated and attributed to an explicit source, and the check of
the numbers a text claims against them (« 72 heures » against « 4 h/jour »). No model is involved
and no statistic is invented: a number with no matching figure is « sans chiffre officiel », which
proves nothing either way. A figure more than two years old is flagged « ancien ».

Shared figures (`workspace_id` empty) serve every newsroom: national statistics seeds and the
World Bank values the `figures_refresh` job keeps current. A newsroom adds its own beside them.
"""

import calendar
import re
import uuid
from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator
from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import dates, numbers, places
from app.core.access import AnyMember, Db
from app.core.activity import record
from app.core.models import Communique, Figure, Item, Workspace
from app.core.words import words
from app.workers import figures_refresh  # registers the `figures_refresh` job
from app.workers.queue import enqueue

router = APIRouter(tags=["figures"])

OLD_DAYS = 730  # a figure older than two years is shown « ancien »
_FIG_STOP = {"demo", "exemple", "fictif", "total", "totale", "taux", "nombre", "selon", "part"}


def as_of_date(as_of: str | None) -> date | None:
    """The day a figure describes: a year counts as its last day, a month as its last day,
    never later than today."""
    if not as_of:
        return None
    m = re.fullmatch(r"(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?", as_of.strip())
    if not m:
        return None
    year, month, day = int(m[1]), int(m[2] or 12), m[3]
    try:
        found = (
            date(year, month, int(day))
            if day
            else date(year, month, calendar.monthrange(year, month)[1])
        )
    except ValueError:
        return None
    return min(found, dates.today())


def as_of_label(as_of: str | None) -> str:
    """« 2018 », « octobre 2026 », « 1er novembre 2026 »."""
    if not as_of:
        return ""
    parts = as_of.split("-")
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return f"{dates.MONTHS[int(parts[1]) - 1]} {parts[0]}"
    day = dates.parse(as_of)
    return dates.fr(day) if day else as_of


class FigureIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    topic: str = Field(min_length=1, max_length=80)
    label: str = Field(min_length=1, max_length=300)
    value: str = Field(min_length=1, max_length=80)
    unit: str | None = Field(default=None, max_length=40)
    as_of: str = Field(min_length=4, max_length=10)
    country: str | None = Field(default=None, max_length=80)
    # Where the figure applies when narrower than the country (« Antananarivo »).
    place: str | None = Field(default=None, max_length=200)
    source_name: str = Field(min_length=1, max_length=200)
    source_url: HttpUrl
    keywords: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("as_of")
    @classmethod
    def period(cls, value):
        value = value.strip()
        m = re.fullmatch(r"(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?", value)
        if not m or as_of_date(value) is None:
            raise ValueError("Use YYYY, YYYY-MM or YYYY-MM-DD")
        today = dates.today()
        future = (
            int(m[1]) > today.year
            or (m[2] and (int(m[1]), int(m[2])) > (today.year, today.month))
            or (m[3] and date(int(m[1]), int(m[2]), int(m[3])) > today)
        )
        if future:
            raise ValueError("A figure describes the past or the present")
        return value

    @field_validator("keywords")
    @classmethod
    def tidy(cls, value):
        return [k.strip()[:60] for k in value if k.strip()]


class FigureOut(BaseModel):
    id: uuid.UUID
    topic: str
    label: str
    value: str
    unit: str | None
    as_of: str | None
    as_of_label: str
    country: str | None
    location: dict[str, Any]
    source_name: str
    source_url: str | None
    keywords: list[str]
    communique_id: uuid.UUID | None
    is_demo: bool
    shared: bool
    age_days: int | None
    old: bool
    created_at: datetime


def out(f: Figure) -> FigureOut:
    day = as_of_date(f.as_of)
    age = (dates.today() - day).days if day else None
    return FigureOut(
        id=f.id,
        topic=f.topic,
        label=f.label,
        value=f.value,
        unit=f.unit,
        as_of=f.as_of,
        as_of_label=as_of_label(f.as_of),
        country=f.country,
        location=f.location or {},
        source_name=f.source_name,
        source_url=f.source_url,
        keywords=f.keywords or [],
        communique_id=f.communique_id,
        is_demo=f.is_demo,
        shared=f.workspace_id is None,
        age_days=age,
        old=age is not None and age > OLD_DAYS,
        created_at=f.created_at,
    )


def _visible(workspace_id: uuid.UUID):
    return select(Figure).where(
        or_(Figure.workspace_id == workspace_id, Figure.workspace_id.is_(None))
    )


@router.get("/workspaces/{ws}/figures")
async def figures(
    member: AnyMember,
    db: Db,
    q: str = Query(default="", max_length=200),
    topic: str = Query(default="", max_length=80),
    country: str = Query(default="", max_length=80),
) -> list[FigureOut]:
    stmt = _visible(member.workspace_id)
    if topic:
        stmt = stmt.where(Figure.topic.ilike(topic))
    if country:
        stmt = stmt.where(Figure.country.ilike(country))
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            or_(
                Figure.label.ilike(like),
                Figure.topic.ilike(like),
                Figure.country.ilike(like),
                Figure.source_name.ilike(like),
            )
        )
    rows = await db.scalars(
        stmt.order_by(Figure.topic, Figure.country, Figure.as_of.desc().nulls_last()).limit(500)
    )
    return [out(row) for row in rows]


@router.post("/workspaces/{ws}/figures", status_code=201)
async def create_figure(body: FigureIn, member: AnyMember, db: Db) -> FigureOut:
    data = body.model_dump(mode="json", exclude={"place"})
    location = None
    if body.place:
        location = await places.geocode(db, body.place) or places.place(body.place)
    figure = Figure(
        workspace_id=member.workspace_id,
        added_by=member.user.id,
        location=location or {},
        **data,
    )
    db.add(figure)
    await db.flush()
    await record(db, member.workspace_id, member.user.id, "figure", figure.id, "create")
    await db.commit()
    await db.refresh(figure)
    return out(figure)


# --- check_numbers ---------------------------------------------------------------------------


def _ordered_words(text: str) -> list[str]:
    flat = places.fold(text)
    return [w for w in re.findall(r"[a-z0-9]+", flat) if len(w) >= 3]


def _stem(word: str) -> str:
    return re.sub(r"s$", "", places.fold(word or "").strip())


def _figure_terms(f: Figure) -> tuple[set[str], str | None]:
    """The words a figure is recognised by, and its key term (first keyword, else the label's first
    meaningful word). Country names are left out: the country is matched on its own."""
    terms = words(f"{f.label} {f.topic} {' '.join(f.keywords or [])}") - _FIG_STOP
    terms -= words(f.country or "")
    ordered = [
        w
        for w in _ordered_words(" ".join(f.keywords or []) or f.label)
        if w in terms and w not in _FIG_STOP
    ]
    return terms, (ordered[0] if ordered else None)


def figure_brief(f: Figure) -> dict[str, Any]:
    o = out(f)
    return {
        "id": str(f.id),
        "label": f.label,
        "value": f.value,
        "unit": f.unit,
        "as_of": f.as_of,
        "as_of_label": o.as_of_label,
        "topic": f.topic,
        "country": f.country,
        "source_name": f.source_name,
        "source_url": f.source_url,
        "age_days": o.age_days,
        "old": o.old,
        "is_demo": f.is_demo,
        "shared": o.shared,
    }


def _summary(claim: dict[str, Any], fig: dict[str, Any] | None, verdict: str) -> str:
    if fig is None:
        return (
            f"Aucun chiffre officiel enregistré pour « {claim['claimed']} » "
            "(cela ne prouve rien dans un sens ou dans l'autre)."
        )
    official = f"{fig['value']} {fig['unit'] or ''}".strip()
    source = ", ".join(x for x in (fig["source_name"], fig["as_of_label"]) if x)
    said = (
        f"Conforme au chiffre officiel : {official} ({source})."
        if verdict == "matches"
        else f"Le chiffre officiel dit {official} ({source}) ; le texte dit « {claim['claimed']} »."
    )
    if fig["old"]:
        said += " Ce chiffre a plus de deux ans."
    return said


async def check_numbers(
    db: AsyncSession, workspace_id: uuid.UUID, text: str, location: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    """Each number the text claims, set against the official figure that speaks of the same thing:
    same kind of number (a percentage with a percentage), a key word of the figure in the clause
    around the number, the same country (named in the text, given in `location`, the newsroom's,
    or Madagascar). `verdict`: `matches`, `differs` or `no_figure` (proves nothing)."""
    claims = numbers.extract_numbers(text or "")
    if not claims:
        return []
    rows = (await db.scalars(_visible(workspace_id).limit(1000))).all()
    ws = await db.get(Workspace, workspace_id)
    folded = places.fold(text)
    known = {f.country for f in rows if f.country} | set(figures_refresh.COUNTRIES.values())
    named = {
        places.fold(c) for c in known if re.search(rf"\b{re.escape(places.fold(c))}\b", folded)
    }
    seen_place = places.gazetteer(text) or {}
    country = (location or {}).get("country") or seen_place.get("country")
    if country:
        named.add(places.fold(country))
    if not named:
        named.add(places.fold(((ws.settings or {}).get("country") if ws else None) or "Madagascar"))
    region = (location or {}).get("region") or seen_place.get("region")

    candidates = []
    for f in rows:
        fig = numbers.parse_figure(f.value, f.unit)
        if fig is None:
            continue
        terms, key = _figure_terms(f)
        candidates.append((f, fig, terms, key))

    results, seen = [], set()
    for claim in claims:
        marker = (claim["claimed"].lower(), claim["kind"])
        if marker in seen:
            continue
        seen.add(marker)
        clause, sentence = words(claim["clause"]), words(claim["context"])
        best = None
        for f, fig, terms, key in candidates:
            if fig["kind"] != claim["kind"]:
                continue
            if claim["kind"] == "amount" and fig.get("currency") != claim.get("currency"):
                continue
            if f.country and places.fold(f.country) not in named:
                continue
            in_clause = clause & terms
            hits = in_clause | (sentence & terms)
            # « 33 millions d'habitants »: the unit itself names what is counted.
            strong = key in hits or (
                claim["kind"] == "count" and _stem(claim["unit"]) in {_stem(t) for t in terms}
            )
            if not in_clause or (len(hits) < 2 and not strong):
                continue
            score = 2 * len(in_clause) + len(hits - in_clause) + (key in hits)
            if region and places.same_region({"region": region}, f.location):
                score += 1
            rank = (score, f.workspace_id is not None, as_of_date(f.as_of) or date.min)
            if best is None or rank > best[0]:
                best = (rank, f, fig)
        if best is None:
            figure, verdict = None, "no_figure"
        else:
            _, f, fig = best
            figure = figure_brief(f)
            verdict = "matches" if numbers.same(claim, fig) else "differs"
        results.append(
            {
                "claimed": claim["claimed"],
                "kind": claim["kind"],
                "context": claim["context"],
                "clause": claim["clause"],
                "figure": figure,
                "verdict": verdict,
                "summary": _summary(claim, figure, verdict),
            }
        )
    return results


class CheckIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=30000)
    place: str | None = Field(default=None, max_length=200)


@router.post("/workspaces/{ws}/figures/check")
async def check(body: CheckIn, member: AnyMember, db: Db) -> list[dict[str, Any]]:
    """The numbers of a text against the official figures (no model involved)."""
    location = places.gazetteer(body.place) if body.place else None
    return await check_numbers(db, member.workspace_id, body.text, location)


# --- shared seeds and the World Bank refresh ---------------------------------------------------

# Real public figures with their real source, so a fresh install can check numbers before the
# first refresh. The World Bank rows are the values its API returned on 2 November 2026; the job
# keeps them current.
SHARED_SEEDS: list[dict[str, Any]] = [
    {
        "topic": "démographie",
        "label": "Population recensée (RGPH-3)",
        "value": "25 674 196",
        "unit": "habitants",
        "as_of": "2018",
        "country": "Madagascar",
        "source_name": "INSTAT, troisième recensement général de la population (RGPH-3)",
        "source_url": "https://www.instat.mg/autres/rgph-3",
        "keywords": ["population", "habitants", "recensement", "rgph", "mponina"],
    },
    figures_refresh.wb_row("SP.POP.TOTL", "MG", "Madagascar", "2025", 32740678),
    figures_refresh.wb_row("FP.CPI.TOTL.ZG", "MG", "Madagascar", "2025", 8.05052431791227),
    figures_refresh.wb_row("EG.ELC.ACCS.ZS", "MG", "Madagascar", "2024", 42.5),
    figures_refresh.wb_row("NY.GDP.PCAP.CD", "MG", "Madagascar", "2025", 599.265294255357),
    figures_refresh.wb_row("SP.DYN.LE00.IN", "MG", "Madagascar", "2024", 63.835),
]


async def seed_shared(db: AsyncSession) -> None:
    """The shared seeds, inserted once and never duplicated (a refreshed value is kept)."""
    for row in SHARED_SEEDS:
        exists = await db.scalar(
            select(Figure.id).where(
                Figure.workspace_id.is_(None),
                Figure.source_url == row["source_url"],
                Figure.country == row["country"],
                Figure.label == row["label"],
            )
        )
        if exists is None:
            await figures_refresh.upsert_shared(db, row)


@router.post("/workspaces/{ws}/figures/refresh", status_code=202)
async def refresh(member: AnyMember, db: Db) -> dict[str, Any]:
    """Seed the shared figures if they are missing, then fetch the World Bank's latest values."""
    await seed_shared(db)
    await db.commit()
    job = await enqueue(db, member.workspace_id, member.user.id, "figures_refresh", {})
    return {"job_id": str(job.id)}


# --- demo --------------------------------------------------------------------------------------


async def seed_demo(db: AsyncSession, workspace_id, user_id, items: dict[str, Item]) -> None:
    """The shared seeds, and the two fictional figures of the pitch (flagged démo): the délestage
    the JIRAMA original N° 2026-118 announces (4 h a day) and the tariff rise (+12 %)."""
    await seed_shared(db)
    await db.execute(
        delete(Figure).where(Figure.workspace_id == workspace_id, Figure.is_demo.is_(True))
    )
    original = await db.scalar(
        select(Communique).where(
            Communique.workspace_id == workspace_id,
            Communique.is_demo.is_(True),
            Communique.status == "original",
            Communique.number == "2026-118",
        )
    )
    signature = ((original.sealed or {}).get("signature") if original else None) or None
    from app.core.seal import seal_url

    tana = places.gazetteer("Antananarivo") or {}
    db.add_all(
        [
            Figure(
                workspace_id=workspace_id,
                added_by=user_id,
                topic="énergie",
                label="Délestage programmé à Antananarivo",
                value="4",
                unit="h/jour",
                as_of="2026-11-01",
                country="Madagascar",
                location=tana,
                source_name="JIRAMA, communiqué N° 2026-118 (démo)",
                source_url=seal_url(original.id, signature) if signature else None,
                communique_id=original.id if original else None,
                keywords=["délestage", "coupure", "électricité", "jirama", "antananarivo"],
                is_demo=True,
            ),
            Figure(
                workspace_id=workspace_id,
                added_by=user_id,
                topic="énergie",
                label="Hausse du tarif de l'électricité",
                value="+12",
                unit="%",
                as_of="2026-10",
                country="Madagascar",
                location={},
                source_name="ORE, décision tarifaire d'octobre 2026 (démo)",
                source_url=None,
                keywords=["tarif", "électricité", "hausse", "jirama", "ore", "prix", "kwh"],
                is_demo=True,
            ),
        ]
    )
    await db.flush()
