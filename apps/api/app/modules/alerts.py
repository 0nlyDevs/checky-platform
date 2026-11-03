"""« Fanairana »: the danger level a journalist adjusts, and the alerts a newsroom raises.

A rumour that can hurt (a kidnapping said to have happened, a fake official order, a call to
violence) rarely arrives once. The same story comes back as a tip, an SMS, a radio clip, a
veilleur's sentence, a press item and a dossier, in French or Malagasy, sometimes about another
town. This module:

- lets a journalist adjust the danger level Checky computed (`item.data.risk_override`, logged in
  the Carnet); the adjusted level wins everywhere (`veille.risk_level`);
- groups the variants that say the same thing (`group`). Veille's own grouping comes first, so
  the two never disagree: what « À l'antenne » shows as one rumour (`veille.group_clips`) and a
  clip or SMS attached to a dossier are always in the same group. Then shared words, with a small
  French–Malagasy concept list and town names set aside (another town is the same rumour), then
  embeddings (cosine ≥ 0.78) when a provider is configured. A group of two or more with a high
  danger level becomes an **alert**: an `Item(type="alert")` whose members live in `data.members`
  (the items list leaves alerts out unless asked for them). Journalists split and merge; a split
  member is never put back by code. Alerts carry no beat: nothing here labels a story political.

No model decides anything here: grouping, counts and levels are code.
"""

import hashlib
import logging
import math
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import dates, embed, refs, tone
from app.core.access import AnyMember, Db, Member
from app.core.activity import broadcast, record
from app.core.errors import ApiError
from app.core.models import Item, Workspace
from app.core.places import MG_REGIONS, MG_TOWNS, fold
from app.core.words import words
from app.modules.items import ItemOut, _get_item, _out
from app.modules.veille import AlertRef, canonical_region, risk_level

log = logging.getLogger("checky.alerts")
router = APIRouter(tags=["alerts"])


# ------------------------------------------------------------------------- danger level
class RiskIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    level: Literal["high", "medium", "low"]
    reason: str = Field(min_length=3, max_length=500)


@router.put("/workspaces/{ws}/items/{item_id}/risk")
async def adjust_risk(item_id: uuid.UUID, body: RiskIn, member: AnyMember, db: Db) -> ItemOut:
    """A journalist sets the danger level, with a reason. Checky's own level (`data.risk`) stays
    beside it; the adjusted one wins everywhere (feed, map, alerts)."""
    item = await _get_item(db, member, item_id)
    if item.type not in ("claim", "alert"):
        raise ApiError(422, "not_a_dossier", "Only a dossier or an alert has a danger level")
    data = dict(item.data or {})
    before = risk_level(data)
    reason = " ".join(body.reason.split())
    data["risk_override"] = {
        "level": body.level,
        "reason": reason,
        "by": member.user.id,
        "at": datetime.now(UTC).isoformat(),
    }
    item.data = data
    await record(
        db,
        member.workspace_id,
        member.user.id,
        "item",
        item.id,
        "risk",
        {"from": before, "to": body.level, "reason": reason},
    )
    await db.commit()
    await db.refresh(item)
    await broadcast(member.workspace_id, "item.updated", _out(item))
    return ItemOut.model_validate(item)


@router.delete("/workspaces/{ws}/items/{item_id}/risk")
async def reset_risk(item_id: uuid.UUID, member: AnyMember, db: Db) -> ItemOut:
    """Back to Checky's own level (the adjustment is removed, the Carnet keeps both lines)."""
    item = await _get_item(db, member, item_id)
    data = dict(item.data or {})
    if "risk_override" not in data:
        return ItemOut.model_validate(item)
    before = risk_level(data)
    data.pop("risk_override")
    item.data = data
    await record(
        db,
        member.workspace_id,
        member.user.id,
        "item",
        item.id,
        "risk",
        {"from": before, "to": risk_level(data), "reset": True},
    )
    await db.commit()
    await db.refresh(item)
    await broadcast(member.workspace_id, "item.updated", _out(item))
    return ItemOut.model_validate(item)


# ------------------------------------------------------------------------------ variants
WINDOW_DAYS = 7
SAME_WORDS = 0.34  # share of the shorter text's concepts, as for radio clips (veille.SAME_RUMOUR)
SAME_MEANING = 0.78  # cosine; measured on gemini-embedding-2: related 0.82-0.91, unrelated ≤ 0.76
MAX_VARIANTS = 300
ORDER = {"low": 0, "medium": 1, "high": 2}

# The same concept in French and Malagasy (and a few French forms), folded, so a Malagasy radio
# sentence and a French tip about the same story share words without a model. A first list, to be
# reread by a native speaker; embeddings take over when a provider is configured.
CONCEPTS: dict[str, str] = {
    "fakana": "enlevement", "keriny": "enlevement", "nalaina": "enlevement",
    "nangalarina": "enlevement", "enleve": "enlevement", "enlevee": "enlevement",
    "enlevements": "enlevement", "kidnapping": "enlevement", "kidnappe": "enlevement",
    "rapt": "enlevement", "ankizy": "enfant", "zaza": "enfant", "enfants": "enfant",
    "fillette": "enfant", "garcon": "enfant", "tsena": "marche", "marches": "marche",
    "jiro": "electricite", "herinaratra": "electricite", "fahatapahan": "delestage",
    "coupure": "delestage", "coupures": "delestage", "delestages": "delestage",
    "ora": "heure", "heures": "heure", "rahampitso": "demain", "omaly": "hier",
    "zandary": "gendarmerie", "zandarimariam": "gendarmerie", "polisy": "police",
    "poizina": "poison", "voapoizina": "poison", "empoisonne": "poison", "empoisonnee": "poison",
    "rano": "eau", "vary": "riz", "sekoly": "ecole", "mpianatra": "eleve", "eleves": "eleve",
    "aretina": "maladie", "areti": "maladie", "maty": "mort", "morts": "mort",
}  # fmt: skip
# Words every report carries, which say nothing about the story itself.
GENERIC = {
    "selon", "affirme", "auditeur", "auditrice", "appel", "radio", "journal", "message",
    "rumeur", "circule", "dit", "dire", "nilaza", "mpihaino", "iray", "hisy", "eto", "tout",
    "tous", "toute", "aurait", "serait", "auraient", "seraient", "rien", "antenne", "hier",
    "soir", "matin", "demain", "aujourd", "hui", "pres", "ainsi", "comme", "mais", "elle",
    "ils", "lui", "son", "ses", "leur", "leurs", "nous", "vous", "avez", "avoir", "fait",
    "faire", "partagez", "urgent", "demo", "exemple", "fictif",
}  # fmt: skip
PLACE_WORDS = {
    *(w for town in MG_TOWNS for w in words(town)),
    *(w for region, (capital, _, _) in MG_REGIONS.items() for w in words(f"{region} {capital}")),
}


def concepts(text: str) -> set[str]:
    """The words a story is made of: accents, places and reporting words set aside, Malagasy and
    French forms of the same concept made one, a plural s dropped."""
    out = set()
    for w in words(text or ""):
        w = CONCEPTS.get(w, w)
        if w in GENERIC or w in PLACE_WORDS or w.isdigit():
            continue
        out.add(CONCEPTS.get(w.rstrip("s"), w.rstrip("s")) if len(w) > 4 else w)
    return out


def word_overlap(a: set[str], b: set[str]) -> float:
    if not a or not b or len(a & b) < 2:
        return 0.0
    return len(a & b) / min(len(a), len(b))


@dataclass
class Variant:
    """One report of what circulates: a dossier, a tip, an SMS, a radio clip, a press item, a page
    a search engine saw. `key` is stable (`item:<id>`, `clip:<id>`, `sms:<id>`)."""

    key: str
    kind: str
    title: str
    text: str
    at: datetime
    region: str | None = None
    place: str | None = None
    station: str | None = None
    item_id: uuid.UUID | None = None
    url: str | None = None
    risk: str = "low"
    reasons: list[dict[str, str]] = field(default_factory=list)
    demo: bool = False

    @property
    def words(self) -> set[str]:
        return concepts(f"{self.title} {self.text}")

    def member(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "kind": self.kind,
            "title": self.title[:300],
            "excerpt": re.sub(r"\s+", " ", self.text or "")[:300],
            "at": self.at.isoformat(),
            "region": self.region,
            "place": self.place,
            "station": self.station,
            "item_id": str(self.item_id) if self.item_id else None,
            "url": self.url,
            "risk": self.risk,
            "demo": self.demo,
        }


def _level(text: str) -> tuple[str, list[dict[str, str]]]:
    found = tone.risk(text)
    return found["level"], found["reasons"]


async def variants(
    db: AsyncSession, workspace: Workspace, days: int = WINDOW_DAYS
) -> list[Variant]:
    """Everything that circulated in the newsroom in the last `days`: the Veille feed (tips, SMS,
    radio clips, press, search-engine sightings) and the dossiers. Each with its danger level: a
    dossier's adjusted level, otherwise the tone lexicon on its words."""
    from app.modules.veille import _place_out, feed_entries, item_location

    since = datetime.now(UTC) - timedelta(days=days)
    out: dict[str, Variant] = {}
    for e in await feed_entries(db, workspace, days=days, checked=False):
        level, reasons = _level(f"{e.title} {e.text}")
        out[e.id] = Variant(
            key=e.id,
            kind=e.kind,
            title=e.title,
            text=e.text,
            at=e.at,
            region=(e.place or {}).get("region"),
            place=(e.place or {}).get("name"),
            station=e.station if e.kind == "clip" else None,
            item_id=e.item_id,
            url=e.url,
            risk=level,
            reasons=reasons,
            demo=e.demo,
        )
    for item in await db.scalars(
        select(Item).where(
            Item.workspace_id == workspace.id, Item.type == "claim", Item.created_at >= since
        )
    ):
        d = item.data or {}
        text = f"{item.title} {(item.body or '')[:600]}"
        level, reasons = _level(text)
        adjusted = risk_level(d)
        code = d.get("risk") if isinstance(d.get("risk"), dict) else {}
        place = _place_out(item_location(item)) or {}
        key = f"item:{item.id}"
        previous = out.get(key)
        out[key] = Variant(
            key=key,
            kind=previous.kind if previous else "item",
            title=item.title,
            text=(item.body or "")[:600],
            at=dates.parse_moment(d.get("first_seen_at")) or item.created_at,
            region=place.get("region"),
            place=place.get("name"),
            item_id=item.id,
            url=d.get("tip_url"),
            risk=adjusted or level,
            reasons=list(code.get("reasons") or []) or reasons,
            demo=bool(d.get("demo")),
        )
    rows = sorted(out.values(), key=lambda v: v.at, reverse=True)[:MAX_VARIANTS]
    return [v for v in rows if len(v.words) >= 2]


_vectors: dict[str, list[float]] = {}


async def _embedded(texts: list[str]) -> list[list[float]] | None:
    """Vectors for `texts`, cached per text; None when no embedding provider answers."""
    if not embed.configured():
        return None
    keys = [hashlib.sha1(t.encode()).hexdigest() for t in texts]
    missing = [t for t, k in zip(texts, keys, strict=True) if k not in _vectors]
    if missing:
        try:
            for t, v in zip(missing, await embed.embed(missing), strict=True):
                _vectors[hashlib.sha1(t.encode()).hexdigest()] = v
        except embed.EmbedUnavailable as e:
            log.info("alerts: embeddings unavailable, words only (%s)", e)
            return None
        while len(_vectors) > 4000:
            _vectors.pop(next(iter(_vectors)))
    return [_vectors[k] for k in keys]


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


async def clusters(rows: list[Variant], links: list[set[str]] | None = None) -> list[list[Variant]]:
    """Variants that say the same thing. Union-find, so a chain of close variants is one story:
    first the links Veille already made (`links`, sets of keys; a report attached to a dossier
    goes with it), then shared concepts, then meaning when embeddings are available."""
    parent = list(range(len(rows)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def join(i: int, j: int) -> None:
        parent[find(i)] = find(j)

    at = {v.key: i for i, v in enumerate(rows)}
    for v in rows:
        if v.item_id and (home := at.get(f"item:{v.item_id}")) is not None:
            join(at[v.key], home)
    for keys in links or []:
        found = [at[k] for k in keys if k in at]
        for i in found[1:]:
            join(i, found[0])
    sets = [v.words for v in rows]
    for i in range(len(rows)):
        for j in range(i + 1, len(rows)):
            if word_overlap(sets[i], sets[j]) >= SAME_WORDS:
                join(i, j)
    vectors = await _embedded([f"{v.title}\n{v.text}"[:1500] for v in rows]) if rows else None
    if vectors:
        for i in range(len(rows)):
            for j in range(i + 1, len(rows)):
                if find(i) != find(j) and cosine(vectors[i], vectors[j]) >= SAME_MEANING:
                    join(i, j)
    groups: dict[int, list[Variant]] = {}
    for i, v in enumerate(rows):
        groups.setdefault(find(i), []).append(v)
    return [sorted(g, key=lambda v: v.at) for g in groups.values()]


# -------------------------------------------------------------------------------- alerts
def _members(alert: Item) -> list[dict[str, Any]]:
    return [m for m in (alert.data or {}).get("members") or [] if isinstance(m, dict)]


def _keys(alert: Item) -> set[str]:
    return {m["key"] for m in _members(alert) if m.get("key")}


def summarise(members: list[dict[str, Any]]) -> dict[str, Any]:
    """The facts of a group, counted by code: how many reports, which channels, radios, regions,
    since when, the highest danger level and its reasons."""
    stations, regions, kinds = [], [], {}
    for m in sorted(members, key=lambda m: m.get("at") or ""):
        kinds[m.get("kind")] = kinds.get(m.get("kind"), 0) + 1
        if m.get("station") and m["station"] not in stations:
            stations.append(m["station"])
        region = canonical_region(m.get("region"))
        if region and region not in regions:
            regions.append(region)
    times = sorted(m["at"] for m in members if m.get("at"))
    level = max((m.get("risk") or "low" for m in members), key=lambda x: ORDER.get(x, 0))
    return {
        "reports": len(members),
        "kinds": kinds,
        "stations": stations,
        "regions": regions,
        "first_at": times[0] if times else None,
        "last_at": times[-1] if times else None,
        "level": level,
    }


def _first_sentence(text: str) -> str:
    from app.modules.veille import first_sentence

    return first_sentence(text, 300) or text[:300]


async def _new_ref(db: AsyncSession, workspace_id: uuid.UUID) -> str:
    return await refs.next_ref(db, workspace_id, "ALR")


def _refresh(alert: Item, members: list[dict[str, Any]], reasons: list[dict] | None) -> None:
    facts = summarise(members)
    data = dict(alert.data or {})
    data["members"] = sorted(members, key=lambda m: m.get("at") or "")
    data["facts"] = facts
    data["demo"] = any(m.get("demo") for m in members)
    if not isinstance(data.get("risk_override"), dict):
        old = data.get("risk") if isinstance(data.get("risk"), dict) else {}
        data["risk"] = {
            "level": facts["level"],
            "reasons": (reasons if reasons is not None else old.get("reasons") or [])[:6],
            "by": "code",
        }
    alert.data = data


async def _new_alert(
    db: AsyncSession, workspace_id: uuid.UUID, group: list[Variant], by: str = "system"
) -> Item:
    # The title reads like the desk's own: a dossier's title first, else the first high-risk report.
    dossiers = [v for v in group if v.key.startswith("item:")]
    lead = next(
        (v for v in dossiers if v.risk == "high"),
        dossiers[0] if dossiers else next((v for v in group if v.risk == "high"), group[0]),
    )
    reasons = [r for v in group for r in v.reasons if v.risk == "high"]
    alert = Item(
        workspace_id=workspace_id,
        author_id=by,
        type="alert",
        title=_first_sentence(lead.title),
        body="",
        status="open",
        tags=[],
        data={"ref": await _new_ref(db, workspace_id), "state": "open", "excluded": []},
    )
    _refresh(alert, [v.member() for v in group], reasons)
    db.add(alert)
    await db.flush()
    return alert


async def open_alerts(db: AsyncSession, workspace_id: uuid.UUID) -> list[Item]:
    return list(
        await db.scalars(
            select(Item)
            .where(
                Item.workspace_id == workspace_id,
                Item.type == "alert",
                Item.status == "open",
            )
            .order_by(Item.created_at)
        )
    )


async def group(db: AsyncSession, ws: uuid.UUID) -> dict[str, list[Item]]:
    """Group what circulates into alerts. Open alerts take the new variants of their story (never
    one a journalist split out); a new group of two or more with a high danger level becomes a
    new alert. Commits; broadcasts `alert.updated` for each alert created or changed and returns
    them as {"created": […], "updated": […]}."""
    await close_published(db, ws)
    workspace = await db.get(Workspace, ws)
    rows = await variants(db, workspace)
    links = await antenne_links(db, ws)
    by_key = {v.key: v for v in rows}
    alerts = list(
        await db.scalars(select(Item).where(Item.workspace_id == ws, Item.type == "alert"))
    )
    taken = {k for a in alerts for k in _keys(a)}
    created, updated = [], []
    # Members already in an alert take the latest facts (an adjusted level, a transcript).
    for alert in alerts:
        if alert.status != "open":
            continue
        members = _members(alert)
        fresh = [by_key[m["key"]].member() if m["key"] in by_key else m for m in members]
        if fresh != members:
            _refresh(alert, fresh, None)
            updated.append(alert)
    for cluster in await clusters(rows, links):
        keys = {v.key for v in cluster}
        homes = [a for a in alerts if a.status == "open" and _keys(a) & keys]
        new = [v for v in cluster if v.key not in taken]
        if homes:
            home = max(homes, key=lambda a: len(_keys(a) & keys))
            barred = set((home.data or {}).get("excluded") or [])
            joining = [v for v in new if v.key not in barred]
            if joining:
                _refresh(home, [*_members(home), *(v.member() for v in joining)], None)
                taken |= {v.key for v in joining}
                if home not in updated:
                    updated.append(home)
            continue
        if len(new) >= 2 and any(v.risk == "high" for v in new):
            alert = await _new_alert(db, ws, new)
            alerts.append(alert)
            taken |= {v.key for v in new}
            created.append(alert)
    if not (created or updated):
        return {"created": [], "updated": []}
    for alert in created:
        await record(db, ws, "system", "alert", alert.id, "create", {"ref": alert.data["ref"]})
    await db.commit()
    for alert in [*created, *updated]:
        await db.refresh(alert)
        await broadcast(ws, "alert.updated", alert_out(alert).model_dump(mode="json"))
    return {"created": created, "updated": updated}


async def antenne_links(db: AsyncSession, ws: uuid.UUID) -> list[set[str]]:
    """The rumours « À l'antenne » shows, as sets of variant keys (its clips, and the dossier
    they are attached to)."""
    from app.modules.veille import _items_of, group_clips, recent_clips

    clips = await recent_clips(db, ws, WINDOW_DAYS)
    out = []
    for g in group_clips(clips, await _items_of(db, clips)):
        keys = {f"clip:{c.id}" for c in g.clips}
        if g.item is not None:
            keys.add(f"item:{g.item.id}")
        out.append(keys)
    return out


async def open_for(db: AsyncSession, ws: uuid.UUID, item_id: uuid.UUID) -> list[Item]:
    """The open alerts a dossier belongs to."""
    key = f"item:{item_id}"
    return [a for a in await open_alerts(db, ws) if key in _keys(a)]


async def alert_index(db: AsyncSession, ws: uuid.UUID) -> dict[str, AlertRef]:
    """Each report of an open alert → that alert, for Veille's rows."""
    out: dict[str, AlertRef] = {}
    for alert in await open_alerts(db, ws):
        d = alert.data or {}
        ref = AlertRef(
            id=alert.id,
            ref=d.get("ref"),
            level=risk_level(d) or "low",
            reports=len(_members(alert)),
        )
        for key in _keys(alert):
            out.setdefault(key, ref)
    return out


# -------------------------------------------------------------------------------- closing
def _linked_ids(alert: Item) -> set[uuid.UUID]:
    out = set()
    for m in _members(alert):
        if m.get("item_id"):
            try:
                out.add(uuid.UUID(str(m["item_id"])))
            except ValueError:
                continue
    return out


async def close_published(
    db: AsyncSession, ws: uuid.UUID, item_ids: list[uuid.UUID] | None = None
) -> list[Item]:
    """An alert stays open until a verdict is published on one of its dossiers: then it closes by
    itself, naming the dossier and its verdict. `item_ids` limits the look to those dossiers (a
    signature that just published). Commits and broadcasts when something closed."""
    alerts = await open_alerts(db, ws)
    wanted = set(item_ids) if item_ids is not None else None
    linked = {a.id: _linked_ids(a) for a in alerts}
    ids = {i for s in linked.values() for i in s if wanted is None or i in wanted}
    if not ids:
        return []
    published = {
        i.id: i
        for i in await db.scalars(
            select(Item).where(
                Item.id.in_(ids), Item.workspace_id == ws, Item.status == "published"
            )
        )
        if (i.data or {}).get("verdict")
    }
    closed = []
    for alert in alerts:
        hit = next((published[i] for i in linked[alert.id] if i in published), None)
        if hit is None:
            continue
        d = dict(alert.data or {})
        d.update(
            state="closed",
            closed={
                "reason": "verdict",
                "note": f"Verdict publié sur {(hit.data or {}).get('ref') or 'un dossier lié'}",
                "item_id": str(hit.id),
                "ref": (hit.data or {}).get("ref"),
                "verdict": (hit.data or {}).get("verdict"),
                "by": (hit.data or {}).get("published_by") or "system",
                "at": datetime.now(UTC).isoformat(),
            },
        )
        alert.data, alert.status = d, "closed"
        await record(
            db, ws, "system", "alert", alert.id, "close",
            {"reason": "verdict", "item_id": str(hit.id)},
        )  # fmt: skip
        closed.append(alert)
    if closed:
        await db.commit()
        for alert in closed:
            await db.refresh(alert)
            await broadcast(ws, "alert.updated", alert_out(alert).model_dump(mode="json"))
    return closed


# --------------------------------------------------------------------------------- routes
class AlertMember(BaseModel):
    key: str
    kind: str
    title: str
    excerpt: str = ""
    at: datetime
    region: str | None = None
    place: str | None = None
    station: str | None = None
    item_id: uuid.UUID | None = None
    url: str | None = None
    risk: str = "low"
    demo: bool = False


class AlertFacts(BaseModel):
    reports: int
    kinds: dict[str, int]
    stations: list[str]
    regions: list[str]
    first_at: datetime | None
    last_at: datetime | None
    hours: int | None  # since the first report


class KitBrief(BaseModel):
    """Where the « Kit d'alerte » stands, for lists (the kit itself: `GET …/alerts/{id}/kit`)."""

    status: Literal["draft", "approved"]
    written_by: str
    approved_at: datetime | None = None
    sent_at: datetime | None = None
    radios: int = 0
    script_fr: str = ""


class AlertOut(BaseModel):
    id: uuid.UUID
    ref: str | None
    title: str
    state: Literal["open", "closed"]
    level: str
    code_level: str | None
    override: dict[str, Any] | None
    reasons: list[dict[str, Any]]
    facts: AlertFacts
    members: list[AlertMember]
    excluded: list[str]
    closed: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime
    demo: bool
    kit: KitBrief | None = None


def kit_brief(d: dict[str, Any]) -> KitBrief | None:
    kit = d.get("kit") if isinstance(d.get("kit"), dict) else None
    if not kit:
        return None
    sent = [s for s in kit.get("sent") or [] if isinstance(s, dict)]
    return KitBrief(
        status="approved" if kit.get("status") == "approved" else "draft",
        written_by=kit.get("written_by") or "template",
        approved_at=dates.parse_moment(kit.get("approved_at")),
        sent_at=dates.parse_moment(sent[-1].get("at")) if sent else None,
        radios=len({r.get("id") for s in sent for r in s.get("radios") or []}),
        script_fr=(kit.get("script") or {}).get("fr") or "",
    )


def alert_out(alert: Item) -> AlertOut:
    d = alert.data or {}
    facts = d.get("facts") or summarise(_members(alert))
    first = dates.parse_moment(facts.get("first_at"))
    risk = d.get("risk") if isinstance(d.get("risk"), dict) else {}
    override = d.get("risk_override") if isinstance(d.get("risk_override"), dict) else None
    return AlertOut(
        id=alert.id,
        ref=d.get("ref"),
        title=alert.title,
        state="closed" if alert.status == "closed" else "open",
        level=risk_level(d) or "low",
        code_level=risk.get("level"),
        override=override,
        reasons=[r for r in risk.get("reasons") or [] if isinstance(r, dict)],
        facts=AlertFacts(
            reports=facts.get("reports", 0),
            kinds=facts.get("kinds") or {},
            stations=facts.get("stations") or [],
            regions=facts.get("regions") or [],
            first_at=first,
            last_at=dates.parse_moment(facts.get("last_at")),
            hours=int((datetime.now(UTC) - first).total_seconds() // 3600) if first else None,
        ),
        members=[AlertMember.model_validate(m) for m in _members(alert)],
        excluded=list(d.get("excluded") or []),
        closed=d.get("closed") if isinstance(d.get("closed"), dict) else None,
        created_at=alert.created_at,
        updated_at=alert.updated_at,
        demo=bool(d.get("demo")),
        kit=kit_brief(d),
    )


_SCANNED: dict[uuid.UUID, float] = {}
SCAN_EVERY = 60.0


async def maybe_group(db: AsyncSession, ws: uuid.UUID, force: bool = False) -> None:
    """The desk's visits drive the grouping too (at most once a minute per newsroom)."""
    if not force and time.monotonic() - _SCANNED.get(ws, -SCAN_EVERY) < SCAN_EVERY:
        return
    _SCANNED[ws] = time.monotonic()
    try:
        await group(db, ws)
    except Exception:  # grouping must never break the page that asked
        log.exception("alerts: grouping failed")
        await db.rollback()


async def _get_alert(db: AsyncSession, member: Member, alert_id: uuid.UUID) -> Item:
    alert = await db.get(Item, alert_id)
    if alert is None or alert.workspace_id != member.workspace_id or alert.type != "alert":
        raise ApiError(404, "not_found", "Alert not found")
    return alert


@router.get("/workspaces/{ws}/alerts")
async def list_alerts(
    member: AnyMember,
    db: Db,
    state: Literal["open", "closed", "all"] = "open",
    region: str | None = None,
    item_id: uuid.UUID | None = None,
    days: int = 30,
) -> list[AlertOut]:
    """The newsroom's alerts, open first, newest report first; `region` keeps those seen there,
    `item_id` those a dossier belongs to."""
    await maybe_group(db, member.workspace_id)
    since = datetime.now(UTC) - timedelta(days=max(1, min(days, 365)))
    stmt = select(Item).where(
        Item.workspace_id == member.workspace_id, Item.type == "alert", Item.updated_at >= since
    )
    if state != "all":
        stmt = stmt.where(Item.status == state)
    out = [alert_out(a) for a in await db.scalars(stmt)]
    if item_id:
        out = [a for a in out if f"item:{item_id}" in {m.key for m in a.members}]
    if region:
        want = fold(canonical_region(region) or region)
        out = [a for a in out if want in {fold(r) for r in a.facts.regions}]
    out.sort(key=lambda a: (a.state != "open", -(a.facts.last_at or a.created_at).timestamp()))
    return out


@router.post("/workspaces/{ws}/alerts/scan")
async def scan_alerts(member: AnyMember, db: Db) -> dict[str, int]:
    """Group what circulates now."""
    found = await group(db, member.workspace_id)
    _SCANNED[member.workspace_id] = time.monotonic()
    return {"created": len(found["created"]), "updated": len(found["updated"])}


@router.get("/workspaces/{ws}/alerts/{alert_id}")
async def get_alert(alert_id: uuid.UUID, member: AnyMember, db: Db) -> AlertOut:
    return alert_out(await _get_alert(db, member, alert_id))


class SplitIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    keys: list[str] = Field(min_length=1, max_length=100)


@router.post("/workspaces/{ws}/alerts/{alert_id}/split", status_code=201)
async def split_alert(alert_id: uuid.UUID, body: SplitIn, member: AnyMember, db: Db) -> AlertOut:
    """« Ce n'est pas la même rumeur »: the chosen members leave this alert for a new one, and
    code never puts them back."""
    alert = await _get_alert(db, member, alert_id)
    members = _members(alert)
    chosen = [m for m in members if m["key"] in set(body.keys)]
    rest = [m for m in members if m["key"] not in set(body.keys)]
    if not chosen:
        raise ApiError(422, "unknown_members", "None of these reports belong to this alert")
    if not rest:
        raise ApiError(422, "nothing_left", "Keep at least one report in this alert")
    data = dict(alert.data or {})
    data["excluded"] = sorted({*(data.get("excluded") or []), *(m["key"] for m in chosen)})
    alert.data = data
    _refresh(alert, rest, None)
    other = Item(
        workspace_id=member.workspace_id,
        author_id=member.user.id,
        type="alert",
        title=_first_sentence(
            next((m for m in chosen if m["key"].startswith("item:")), chosen[0])["title"]
        ),
        body="",
        status=alert.status,
        tags=[],
        data={
            "ref": await _new_ref(db, member.workspace_id),
            "state": alert.status,
            "excluded": [m["key"] for m in rest],
            "split_from": str(alert.id),
        },
    )
    _refresh(other, chosen, None)
    db.add(other)
    await db.flush()
    await record(
        db, member.workspace_id, member.user.id, "alert", alert.id, "split",
        {"into": str(other.id), "keys": [m["key"] for m in chosen]},
    )  # fmt: skip
    await db.commit()
    for a in (alert, other):
        await db.refresh(a)
        await broadcast(member.workspace_id, "alert.updated", alert_out(a).model_dump(mode="json"))
    return alert_out(other)


class MergeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    other_id: uuid.UUID


@router.post("/workspaces/{ws}/alerts/{alert_id}/merge")
async def merge_alert(alert_id: uuid.UUID, body: MergeIn, member: AnyMember, db: Db) -> AlertOut:
    """« C'est la même rumeur »: the other alert's reports join this one; the other is closed as
    merged."""
    alert = await _get_alert(db, member, alert_id)
    other = await _get_alert(db, member, body.other_id)
    if other.id == alert.id:
        raise ApiError(422, "same_alert", "Merge two different alerts")
    keys = _keys(alert)
    joined = [*_members(alert), *(m for m in _members(other) if m["key"] not in keys)]
    data = dict(alert.data or {})
    moved = {m["key"] for m in _members(other)}
    data["excluded"] = [k for k in data.get("excluded") or [] if k not in moved]
    alert.data = data
    _refresh(alert, joined, None)
    od = dict(other.data or {})
    od.update(
        state="closed",
        members=[],
        closed={
            "reason": "merged",
            "note": f"Fusionnée dans {(alert.data or {}).get('ref') or 'une autre alerte'}",
            "into": str(alert.id),
            "by": member.user.id,
            "at": datetime.now(UTC).isoformat(),
        },
    )
    other.data, other.status = od, "closed"
    await record(
        db, member.workspace_id, member.user.id, "alert", alert.id, "merge",
        {"from": str(other.id)},
    )  # fmt: skip
    await db.commit()
    for a in (alert, other):
        await db.refresh(a)
        await broadcast(member.workspace_id, "alert.updated", alert_out(a).model_dump(mode="json"))
    return alert_out(alert)


class CloseIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=3, max_length=500)


@router.post("/workspaces/{ws}/alerts/{alert_id}/close")
async def close_alert(alert_id: uuid.UUID, body: CloseIn, member: AnyMember, db: Db) -> AlertOut:
    """A journalist closes an alert before any verdict, and says why (required, kept in the
    activity). « Diffuser » then proposes the radios the kit went to, on the linked dossiers."""
    alert = await _get_alert(db, member, alert_id)
    if alert.status == "closed":
        raise ApiError(409, "already_closed", "This alert is already closed")
    note = " ".join(body.reason.split())
    if len(note) < 3:
        raise ApiError(422, "reason_required", "Say why the alert is closed")
    d = dict(alert.data or {})
    d.update(
        state="closed",
        closed={
            "reason": "journalist",
            "note": note,
            "by": member.user.id,
            "at": datetime.now(UTC).isoformat(),
        },
    )
    alert.data, alert.status = d, "closed"
    await record(
        db, member.workspace_id, member.user.id, "alert", alert.id, "close",
        {"reason": "journalist", "note": note},
    )  # fmt: skip
    await db.commit()
    await db.refresh(alert)
    out = alert_out(alert)
    await broadcast(member.workspace_id, "alert.updated", out.model_dump(mode="json"))
    return out
