"""« Météo des rumeurs »: the rumours a season brings back, before they spread.

Every year the same false stories return with the same calendar: old flood videos when the cyclone
season opens, leaked exam papers the week of the bac, a « shortage » of rice during the lean
months, fake pay delays at the end of the month. A newsroom that knows the calendar hears about
them before they spread. The rules are stored per country in `app.season` (seeded here for
Madagascar, the first market; any newsroom can add its own), and worked out in code: no model
guesses what month it is.

« Ça revient » adds the newsroom's own memory: verdicts published in earlier years within
±15 days of today's date (same month and day, any year).
"""

import uuid
from datetime import date, timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import dates
from app.core.models import Item, Season, Workspace
from app.core.places import fold

COUNTRY = "Madagascar"
RETURN_WINDOW_DAYS = 15
# A verdict younger than this is this season's, not one that « comes back ».
RETURN_MIN_AGE_DAYS = 300

# (name, topic, start month, end month, what comes back, keywords). Topics are default beats.
MG_SEASONS: tuple[tuple[str, str, int, int, str, list[str]], ...] = (
    (
        "Saison cyclonique",
        "environnement",
        11,
        4,
        (
            "Fausses alertes cycloniques, vieilles vidéos d'inondation, routes coupées, "
            "épidémies après les pluies."
        ),
        ["cyclone", "inondation", "alerte", "crue", "route coupée", "BNGRC"],
    ),
    (
        "Baccalauréat",
        "éducation",
        11,
        11,
        "Fuites de sujets, faux reports d'épreuves, faux résultats.",
        ["bac", "baccalauréat", "sujets", "report", "résultats"],
    ),
    (
        "CEPE",
        "éducation",
        6,
        6,
        "Fuites de sujets et dates d'examen inventées.",
        ["cepe", "examen", "sujets", "report"],
    ),
    (
        "BEPC",
        "éducation",
        7,
        7,
        "Fuites de sujets, faux reports, faux résultats.",
        ["bepc", "examen", "sujets", "résultats"],
    ),
    (
        "Reprise des cours de janvier",
        "éducation",
        1,
        1,
        "Faux calendriers scolaires, annonces de grève des enseignants.",
        ["rentrée", "école", "grève", "calendrier"],
    ),
    (
        "Rentrée scolaire",
        "éducation",
        9,
        9,
        "Fausses listes de fournitures, frais d'inscription inventés, faux calendriers.",
        ["rentrée", "école", "inscription", "fournitures"],
    ),
    (
        "Paie des fonctionnaires",
        "économie",
        1,
        12,
        "Faux retards de salaire, fausses primes, arnaques au virement.",
        ["salaire", "paie", "fonctionnaires", "prime", "solde"],
    ),
    (
        "Soudure du riz",
        "économie",
        1,
        3,
        "Pénurie annoncée, prix qui doublent, stocks cachés.",
        ["riz", "vary", "pénurie", "prix", "soudure"],
    ),
    (
        "Peste",
        "santé",
        8,
        4,
        "Faux cas, quartiers « en quarantaine », faux vaccins et remèdes miracles.",
        ["peste", "cas", "quarantaine", "vaccin", "rats"],
    ),
    (
        "Fête de l'indépendance",
        "société",
        6,
        6,
        "Faux programmes du 26 juin, défilés « annulés », alertes à la sécurité.",
        ["26 juin", "défilé", "fête", "indépendance"],
    ),
    (
        "Fêtes de fin d'année",
        "économie",
        12,
        12,
        "Faux bons d'achat, promotions inventées, flambée des prix.",
        ["promotion", "bon d'achat", "cadeau", "prix"],
    ),
)
# Rules that only hold some days of the month: (from day, to day), wrapping over the month's end.
DAY_WINDOWS = {"Paie des fonctionnaires": (25, 5)}
# Rules that concern some regions only (folded names); empty = the whole country.
REGIONS = {
    "Peste": {
        "analamanga",
        "amoron'i mania",
        "haute matsiatra",
        "vakinankaratra",
        "itasy",
        "alaotra-mangoro",
        "bongolava",
    },
}
# Elections are dated, not seasonal: `workspace.settings.election_date` (YYYY-MM-DD) switches the
# rule on from 90 days before to 30 days after.
ELECTION_BEFORE, ELECTION_AFTER = 90, 30


def in_months(start: int, end: int, month: int) -> bool:
    """`month` falls within start..end, wrapping over the new year (November to April)."""
    return start <= month <= end if start <= end else month >= start or month <= end


def _in_days(name: str, day: int) -> bool:
    window = DAY_WINDOWS.get(name)
    if not window:
        return True
    start, end = window
    return start <= day <= end if start <= end else day >= start or day <= end


def _in_region(name: str, region: str | None) -> bool:
    regions = REGIONS.get(name)
    return not regions or not region or fold(region) in regions


async def seed(db: AsyncSession, country: str = COUNTRY) -> int:
    """Add the built-in rules a country does not have yet (by name). Idempotent."""
    if country != COUNTRY:
        return 0
    have = set((await db.scalars(select(Season.name).where(Season.country == country))).all())
    added = 0
    for name, topic, start, end, note, keywords in MG_SEASONS:
        if name in have:
            continue
        db.add(
            Season(
                country=country,
                name=name,
                topic=topic,
                start_month=start,
                end_month=end,
                note=note,
                keywords=keywords,
            )
        )
        added += 1
    if added:
        await db.flush()
    return added


def _election(settings: dict[str, Any], today: date) -> dict[str, Any] | None:
    try:
        when = date.fromisoformat(str(settings.get("election_date") or "")[:10])
    except ValueError:
        return None
    days = (when - today).days
    if not -ELECTION_AFTER <= days <= ELECTION_BEFORE:
        return None
    return {
        "name": "Élections",
        "topic": "politique",
        "note": "Faux résultats, fausses consignes de vote, bureaux déplacés, candidats retirés.",
        "keywords": ["élection", "vote", "résultats", "candidat", "CENI"],
        "until": dates.fr(when + timedelta(days=ELECTION_AFTER)),
        "days_to": days,
    }


def _season_out(row: Season, today: date) -> dict[str, Any]:
    end_month = row.end_month
    year = today.year if end_month >= today.month else today.year + 1
    return {
        "name": row.name,
        "topic": row.topic,
        "note": row.note,
        "keywords": list(row.keywords or []),
        "until": f"{dates.MONTHS[end_month - 1]} {year}",
        "days_to": None,
    }


def returns_on(moment: date, today: date) -> bool:
    """`moment` (an earlier year) is within ±15 days of today's month and day."""
    if (today - moment).days < RETURN_MIN_AGE_DAYS:
        return False
    try:
        same_day = moment.replace(year=today.year)
    except ValueError:  # 29 February
        same_day = date(today.year, 2, 28)
    gap = abs((same_day - today).days)
    return min(gap, 365 - gap) <= RETURN_WINDOW_DAYS


def _seen(item: Item) -> date:
    d = item.data or {}
    return dates.parse(d.get("first_seen_at")) or item.created_at.astimezone(dates.EAT).date()


async def returning(
    db: AsyncSession, workspace_id: uuid.UUID, today: date | None = None, limit: int = 5
) -> list[dict[str, Any]]:
    """« Ça revient »: confirmed verdicts of earlier years around today's date, from this
    newsroom (verified or published) and from the public archive of other newsrooms."""
    today = today or dates.today()
    rows = (
        await db.execute(
            select(Item, Workspace)
            .join(Workspace, Workspace.id == Item.workspace_id)
            .where(
                Item.type == "claim",
                Item.data["verdict"].astext.in_(["true", "misleading", "false", "unverifiable"]),
                or_(
                    (Item.workspace_id == workspace_id)
                    & Item.status.in_(["verified", "published"]),
                    Workspace.publishes & (Item.status == "published"),
                ),
            )
            .limit(2000)
        )
    ).all()
    out = []
    for item, ws in rows:
        seen = _seen(item)
        if not returns_on(seen, today):
            continue
        out.append(
            {
                "id": str(item.id),
                "ref": (item.data or {}).get("ref"),
                "title": item.title,
                "verdict": item.data["verdict"],
                "year": seen.year,
                "seen_on": seen.isoformat(),
                "newsroom": ws.name,
                "mine": ws.id == workspace_id,
                "public": bool(ws.publishes and item.status == "published"),
                "demo": bool((item.data or {}).get("demo")),
            }
        )
    out.sort(key=lambda r: (not r["mine"], r["seen_on"]), reverse=False)
    return out[:limit]


async def meteo(
    db: AsyncSession,
    workspace: Workspace,
    region: str | None = None,
    beats: list[str] | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    """This week's likely rumours: the season rules in effect (the newsroom's beats first) and the
    verdicts that come back around this date."""
    today = today or dates.today()
    settings = workspace.settings or {}
    country = settings.get("country") or COUNTRY
    rows = (await db.scalars(select(Season).where(Season.country == country))).all()
    if not rows and await seed(db, country):
        await db.commit()
        rows = (await db.scalars(select(Season).where(Season.country == country))).all()
    seasons = [
        _season_out(r, today)
        for r in rows
        if in_months(r.start_month, r.end_month, today.month)
        and _in_days(r.name, today.day)
        and _in_region(r.name, region)
    ]
    if election := _election(settings, today):
        seasons.insert(0, election)
    mine = {fold(b) for b in beats or []}
    seasons.sort(key=lambda s: (fold(s["topic"]) not in mine, s["name"]))
    return {
        "today": today.isoformat(),
        "today_label": dates.fr(today),
        "country": country,
        "region": region,
        "seasons": seasons,
        "returning": await returning(db, workspace.id, today),
    }


def matching(seasons: list[dict[str, Any]], text: str) -> list[str]:
    """The seasons whose keywords a text mentions (a tip about the bac in November)."""
    folded = f" {fold(text)} "
    return [
        s["name"] for s in seasons if any(f" {fold(k)}" in folded for k in s.get("keywords") or [])
    ]
