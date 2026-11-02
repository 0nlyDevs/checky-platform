"""Job `figures_refresh`: the World Bank's latest values for a few indicators and countries, kept as
figures every newsroom shares (`workspace_id` empty), each dated and linked to its source page.

The World Bank API is free and keyless. `mrnev=1` asks for each country's most recent non-empty
value, so a figure always says which year it describes; a value the API does not return leaves the
stored one untouched. Tests swap `_transport` for a mock.
"""

import logging
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import SessionLocal
from app.core.http import shared as shared_http
from app.core.models import Figure
from app.workers.queue import JobContext, handler

log = logging.getLogger("checky.figures")

WB_API = "https://api.worldbank.org/v2"
SEED = "seed"  # `added_by` of the shared rows code maintains
_transport: httpx.AsyncBaseTransport | None = None

# The countries pulled by default (ISO2 → name as newsrooms write it): Madagascar first, its
# neighbours in the Indian Ocean, and France.
COUNTRIES = {
    "MG": "Madagascar",
    "KM": "Comores",
    "MU": "Maurice",
    "SC": "Seychelles",
    "FR": "France",
}
# indicator → topic, label, unit, decimals, keywords (the first keyword is the figure's key term)
INDICATORS: dict[str, dict[str, Any]] = {
    "SP.POP.TOTL": {
        "topic": "démographie",
        "label": "Population totale",
        "unit": "habitants",
        "decimals": 0,
        "keywords": ["population", "habitants", "mponina", "malgaches"],
    },
    "FP.CPI.TOTL.ZG": {
        "topic": "économie",
        "label": "Inflation (prix à la consommation, sur un an)",
        "unit": "%",
        "decimals": 1,
        "keywords": ["inflation", "prix", "consommation", "vidim-piainana"],
    },
    "EG.ELC.ACCS.ZS": {
        "topic": "énergie",
        "label": "Accès à l'électricité (part de la population)",
        "unit": "%",
        "decimals": 1,
        "keywords": ["électricité", "accès", "raccordés", "jiro"],
    },
    "NY.GDP.PCAP.CD": {
        "topic": "économie",
        "label": "PIB par habitant (dollars courants)",
        "unit": "dollars US",
        "decimals": 0,
        "keywords": ["pib", "richesse", "habitant", "revenu"],
    },
    "SP.DYN.LE00.IN": {
        "topic": "santé",
        "label": "Espérance de vie à la naissance",
        "unit": "ans",
        "decimals": 1,
        "keywords": ["espérance", "vie", "naissance", "longévité"],
    },
}


def source_url(indicator: str, iso2: str) -> str:
    return f"https://data.worldbank.org/indicator/{indicator}?locations={iso2}"


def fr_number(value: float, decimals: int) -> str:
    """32 740 678 · 8,1 — the way a French text writes it."""
    text = f"{value:,.{decimals}f}".replace(",", " ").replace(".", ",")
    return text


def wb_row(indicator: str, iso2: str, country: str, year: str, value: float) -> dict[str, Any]:
    meta = INDICATORS[indicator]
    return {
        "topic": meta["topic"],
        "label": meta["label"],
        "value": fr_number(value, meta["decimals"]),
        "unit": meta["unit"],
        "as_of": year,
        "country": country,
        "source_name": "Banque mondiale, Indicateurs du développement dans le monde",
        "source_url": source_url(indicator, iso2),
        "keywords": meta["keywords"],
    }


async def upsert_shared(db: AsyncSession, row: dict[str, Any]) -> Figure:
    """One shared figure, found again by its source page, country and label (no duplicates)."""
    figure = await db.scalar(
        select(Figure).where(
            Figure.workspace_id.is_(None),
            Figure.source_url == row["source_url"],
            Figure.country == row.get("country"),
            Figure.label == row["label"],
        )
    )
    if figure is None:
        figure = Figure(workspace_id=None, added_by=SEED, is_demo=False, location={})
        db.add(figure)
    for key, value in row.items():
        setattr(figure, key, value)
    return figure


async def fetch(indicator: str, codes: list[str]) -> list[dict[str, Any]]:
    """The latest non-empty value of `indicator` for each country code."""
    r = await shared_http("worldbank", _transport, 20).get(
        f"{WB_API}/country/{';'.join(codes)}/indicator/{indicator}",
        params={"format": "json", "mrnev": 1, "per_page": 100},
    )
    r.raise_for_status()
    body = r.json()
    if not isinstance(body, list) or len(body) < 2 or not isinstance(body[1], list):
        return []
    return [x for x in body[1] if isinstance(x, dict) and x.get("value") is not None]


async def refresh(countries: dict[str, str] | None = None) -> dict[str, Any]:
    countries = countries or COUNTRIES
    updated, failed = 0, []
    async with SessionLocal() as db:
        for indicator in INDICATORS:
            try:
                rows = await fetch(indicator, list(countries))
            except (httpx.HTTPError, ValueError) as exc:
                log.warning("world bank %s failed: %s", indicator, exc)
                failed.append(indicator)
                continue
            for x in rows:
                iso2 = (x.get("country") or {}).get("id")
                if iso2 not in countries or not str(x.get("date", "")).isdigit():
                    continue
                await upsert_shared(
                    db, wb_row(indicator, iso2, countries[iso2], x["date"], float(x["value"]))
                )
                updated += 1
        await db.commit()
    return {"updated": updated, "failed": failed}


@handler("figures_refresh")
async def figures_refresh(ctx: JobContext) -> dict[str, Any]:
    wanted = ctx.input.get("countries")
    from app.core import countries as names

    countries = {c: COUNTRIES.get(c) or names.name(c) or c for c in wanted} if wanted else None
    return await refresh(countries)
