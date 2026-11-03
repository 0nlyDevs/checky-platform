"""Places: a claim can come from anywhere, so every place is structured the same way:

    {"name": "Toamasina", "country": "Madagascar", "region": "Atsinanana",
     "locality": "Toamasina", "lat": -18.15, "lng": 49.41}

`geocode(db, text)` asks OpenStreetMap Nominatim (free, no key; one request a second, a contact
User-Agent as its policy asks) and caches the answer in `app.place`. Madagascar is the first
market, so a small gazetteer of its regions and main towns answers at once and offline; it is a
fallback and a seed, never a constraint.
"""

import asyncio
import logging
import time
import unicodedata
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.http import shared as shared_http
from app.core.models import Place

log = logging.getLogger("checky.places")

NOMINATIM = "https://nominatim.openstreetmap.org/search"
UA = "Checky/0.1 (https://github.com/0nlyDevs/checky-platform; newsroom verification tool)"
_transport: httpx.AsyncBaseTransport | None = None  # tests swap in a mock
_last_call = 0.0
_lock = asyncio.Lock()

# Madagascar's regions (23 since 2021) with their capital, and the main towns people name.
MG_REGIONS: dict[str, tuple[str, float, float]] = {
    "Alaotra-Mangoro": ("Ambatondrazaka", -17.83, 48.42),
    "Amoron'i Mania": ("Ambositra", -20.53, 47.25),
    "Analamanga": ("Antananarivo", -18.88, 47.51),
    "Analanjirofo": ("Fenoarivo Atsinanana", -17.38, 49.41),
    "Androy": ("Ambovombe", -25.17, 46.08),
    "Anosy": ("Taolagnaro", -25.03, 46.98),
    "Atsimo-Andrefana": ("Toliara", -23.35, 43.67),
    "Atsimo-Atsinanana": ("Farafangana", -22.82, 47.83),
    "Atsinanana": ("Toamasina", -18.15, 49.41),
    "Betsiboka": ("Maevatanana", -16.95, 46.83),
    "Boeny": ("Mahajanga", -15.72, 46.32),
    "Bongolava": ("Tsiroanomandidy", -18.77, 46.05),
    "Diana": ("Antsiranana", -12.28, 49.29),
    "Fitovinany": ("Manakara", -22.13, 48.02),
    "Haute Matsiatra": ("Fianarantsoa", -21.45, 47.09),
    "Ihorombe": ("Ihosy", -22.40, 46.12),
    "Itasy": ("Miarinarivo", -18.95, 46.90),
    "Melaky": ("Maintirano", -18.06, 44.03),
    "Menabe": ("Morondava", -20.28, 44.28),
    "Sava": ("Sambava", -14.27, 50.17),
    "Sofia": ("Antsohihy", -14.88, 47.98),
    "Vakinankaratra": ("Antsirabe", -19.87, 47.03),
    "Vatovavy": ("Mananjary", -21.22, 48.33),
}
MG_TOWNS: dict[str, str] = {
    "antananarivo": "Analamanga", "tana": "Analamanga", "tananarive": "Analamanga",
    "analakely": "Analamanga", "ambohidratrimo": "Analamanga", "anosy": "Analamanga",
    "toamasina": "Atsinanana", "tamatave": "Atsinanana", "mahajanga": "Boeny", "majunga": "Boeny",
    "fianarantsoa": "Haute Matsiatra", "toliara": "Atsimo-Andrefana", "tulear": "Atsimo-Andrefana",
    "antsiranana": "Diana", "diego": "Diana", "diego-suarez": "Diana", "nosy be": "Diana",
    "antsirabe": "Vakinankaratra", "ambositra": "Amoron'i Mania", "morondava": "Menabe",
    "sambava": "Sava", "antalaha": "Sava", "vohemar": "Sava", "manakara": "Fitovinany",
    "mananjary": "Vatovavy", "farafangana": "Atsimo-Atsinanana", "taolagnaro": "Anosy",
    "fort-dauphin": "Anosy", "ambovombe": "Androy", "ihosy": "Ihorombe", "maintirano": "Melaky",
    "antsohihy": "Sofia", "maevatanana": "Betsiboka", "tsiroanomandidy": "Bongolava",
    "miarinarivo": "Itasy", "ambatondrazaka": "Alaotra-Mangoro", "moramanga": "Alaotra-Mangoro",
    "fenoarivo atsinanana": "Analanjirofo", "maroantsetra": "Analanjirofo",
}  # fmt: skip


def fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").lower()
    return "".join(c for c in s if not unicodedata.combining(c)).strip()


def place(
    name: str,
    country: str | None = None,
    region: str | None = None,
    locality: str | None = None,
    lat: float | None = None,
    lng: float | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "country": country,
        "region": region,
        "locality": locality,
        "lat": lat,
        "lng": lng,
    }


def gazetteer(text: str) -> dict[str, Any] | None:
    """A Malagasy region or town named in `text`, at once and offline; None when there is none."""
    folded = f" {fold(text)} "
    for region, (capital, lat, lng) in MG_REGIONS.items():
        if f" {fold(region)} " in folded:
            return place(region, "Madagascar", region, None, lat, lng)
    best = None
    for town, region in MG_TOWNS.items():
        if f" {town} " in folded and (best is None or len(town) > len(best)):
            best = town
    if best:
        region = MG_TOWNS[best]
        _, lat, lng = MG_REGIONS[region]
        return place(best.title(), "Madagascar", region, best.title(), lat, lng)
    if " madagascar " in folded or " madagasikara " in folded:
        return place("Madagascar", "Madagascar", None, None, -18.9, 47.5)
    return None


def _from_nominatim(hit: dict[str, Any]) -> dict[str, Any]:
    addr = hit.get("address") or {}
    region = addr.get("state") or addr.get("region") or addr.get("province") or addr.get("county")
    locality = (
        addr.get("city") or addr.get("town") or addr.get("village") or addr.get("municipality")
    )
    name = hit.get("name") or (hit.get("display_name") or "").split(",")[0]
    try:
        lat, lng = float(hit["lat"]), float(hit["lon"])
    except (KeyError, TypeError, ValueError):
        lat = lng = None
    return place(name[:200], addr.get("country"), region, locality, lat, lng)


async def geocode(db: AsyncSession, text: str) -> dict[str, Any] | None:
    """The place `text` names: the gazetteer first, then the cache, then Nominatim (one call a
    second, as its usage policy asks). None when nothing is found or the service is down."""
    text = (text or "").strip()[:200]
    if not text:
        return None
    if found := gazetteer(text):
        return found
    key = fold(text)
    cached = await db.get(Place, key)
    if cached:
        return place(
            cached.name, cached.country, cached.region, cached.locality, cached.lat, cached.lng
        )
    global _last_call
    async with _lock:
        wait = 1.0 - (time.monotonic() - _last_call)
        if wait > 0:
            await asyncio.sleep(wait)
        _last_call = time.monotonic()
        try:
            r = await shared_http("nominatim", _transport, 8).get(
                NOMINATIM,
                params={"q": text, "format": "jsonv2", "addressdetails": 1, "limit": 1},
                headers={"User-Agent": UA, "Accept-Language": "fr,en"},
            )
        except httpx.HTTPError as exc:
            log.warning("nominatim failed: %s", exc)
            return None
    if r.status_code != 200:
        return None
    hits = r.json() if isinstance(r.json(), list) else []
    if not hits:
        return None
    found = _from_nominatim(hits[0])
    db.add(Place(query=key, **found))
    try:
        await db.commit()
    except Exception:  # noqa: BLE001 - a concurrent insert of the same key is fine
        await db.rollback()
    return found


def region_of(location: dict[str, Any] | None) -> str | None:
    return (location or {}).get("region") or None


def same_region(a: dict[str, Any] | None, b: dict[str, Any] | None) -> bool:
    ra, rb = region_of(a), region_of(b)
    return bool(ra and rb and fold(ra) == fold(rb))
