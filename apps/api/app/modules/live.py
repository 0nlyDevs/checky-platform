"""Live alerts in the desk (brief 8.4): what a journalist must hear about now, wherever they are.

`GET /workspaces/{ws}/live` lists, by code, over the last `hours` (24 by default):
- `high_risk`: a new high-risk rumour in the newsroom's regions (an alert, or a dossier whose
  danger level is high), the regions being the newsroom's home region, its journalists' Ma
  rubrique regions and its partner radios'; all regions when none is set;
- `on_air`: a watched word (« Mots surveillés ») heard on a radio clip;
- `truth_late`: a route of « Le trajet » where the rumour was seen more than 24 hours ago and the
  truth has not followed (no truth stop on that channel and region);
- `kit_sent`: an alert kit sent to the desk.
The desk polls it and shows each new notice once (`components/shell/live-notices.tsx`).
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import dates, places
from app.core.access import AnyMember, Db
from app.core.models import Item, MemberPref, RadioClip, RadioPartner, Route, Signal, Workspace
from app.modules.veille import canonical_region, mentions, risk_level

router = APIRouter(tags=["live"])

LATE = timedelta(hours=24)
LOOK_BACK = timedelta(days=14)  # rumour stops older than this are history, not news
MAX_NOTICES = 30


class Notice(BaseModel):
    id: str  # stable: the desk shows each notice once
    kind: Literal["high_risk", "on_air", "truth_late", "kit_sent"]
    at: datetime
    title: str
    detail: str = ""
    ref: str | None = None
    href: str  # inside the desk, relative to /w/{ws}
    demo: bool = False


async def newsroom_regions(db: AsyncSession, ws: uuid.UUID) -> set[str]:
    """The regions the newsroom watches, folded: home region, journalists' and radios'."""
    workspace = await db.get(Workspace, ws)
    names = [(workspace.settings or {}).get("region") if workspace else None]
    for pref in await db.scalars(select(MemberPref).where(MemberPref.workspace_id == ws)):
        names += list(pref.regions or [])
    for radio in await db.scalars(select(RadioPartner).where(RadioPartner.workspace_id == ws)):
        names.append(places.region_of(radio.location))
    return {places.fold(canonical_region(n) or n) for n in names if n}


def _in(regions: list[str | None], watched: set[str]) -> bool:
    if not watched:
        return True
    return any(r and places.fold(r) in watched for r in regions)


async def notices(db: AsyncSession, ws: uuid.UUID, hours: int = 24) -> list[Notice]:
    from app.modules.alerts import _members
    from app.modules.trajet import _covers
    from app.modules.veille import item_location

    now = datetime.now(UTC)
    since = now - timedelta(hours=hours)
    watched = await newsroom_regions(db, ws)
    out: list[Notice] = []

    # A new high-risk rumour in the newsroom's regions: alerts first, then single dossiers.
    alerts = list(
        await db.scalars(select(Item).where(Item.workspace_id == ws, Item.type == "alert"))
    )
    in_alert = {m.get("item_id") for a in alerts for m in _members(a) if m.get("item_id")}
    for a in alerts:
        d = a.data or {}
        regions = list((d.get("facts") or {}).get("regions") or [])
        if (
            a.status == "open"
            and a.created_at >= since
            and risk_level(d) == "high"
            and _in(regions, watched)
        ):
            out.append(
                Notice(
                    id=f"alert:{a.id}",
                    kind="high_risk",
                    at=a.created_at,
                    title=a.title,
                    detail=", ".join(regions),
                    ref=d.get("ref"),
                    href=f"/watch#alerte-{a.id}",
                    demo=bool(d.get("demo")),
                )
            )
        for sent in (d.get("kit") or {}).get("sent") or []:
            at = dates.parse_moment(sent.get("at"))
            if at and at >= since and sent.get("desks"):
                out.append(
                    Notice(
                        id=f"kit:{a.id}:{sent.get('at')}",
                        kind="kit_sent",
                        at=at,
                        title=a.title,
                        detail=((d.get("kit") or {}).get("script") or {}).get("fr") or "",
                        ref=d.get("ref"),
                        href=f"/watch#alerte-{a.id}",
                        demo=bool(d.get("demo")),
                    )
                )
    for item in await db.scalars(
        select(Item).where(Item.workspace_id == ws, Item.type == "claim", Item.created_at >= since)
    ):
        d = item.data or {}
        if risk_level(d) != "high" or str(item.id) in in_alert:
            continue
        region = (item_location(item) or {}).get("region")
        if _in([region], watched):
            out.append(
                Notice(
                    id=f"item:{item.id}",
                    kind="high_risk",
                    at=item.created_at,
                    title=item.title,
                    detail=region or "",
                    ref=d.get("ref"),
                    href=f"/claims/{item.id}",
                    demo=bool(d.get("demo")),
                )
            )

    # A watched word heard on air.
    words = list(
        await db.scalars(select(Signal).where(Signal.workspace_id == ws, Signal.active.is_(True)))
    )
    if words:
        for clip in await db.scalars(
            select(RadioClip).where(RadioClip.workspace_id == ws, RadioClip.recorded_at >= since)
        ):
            for s in words:
                if mentions(s.word, clip.heard_text or ""):
                    out.append(
                        Notice(
                            id=f"word:{s.id}:{clip.id}",
                            kind="on_air",
                            at=clip.recorded_at,
                            title=s.word,
                            detail=f"{clip.station} · {(clip.heard_text or '')[:160]}",
                            href="/watch?type=clip",
                            demo="démo" in (clip.station or "").lower(),
                        )
                    )

    # A route of « Le trajet » where the truth has not followed for 24 hours.
    stops = list(
        await db.scalars(
            select(Route)
            .join(Item, Item.id == Route.item_id)
            .where(Route.workspace_id == ws, Item.type == "claim", Route.at >= now - LOOK_BACK)
        )
    )
    truth: dict[uuid.UUID, list[Route]] = {}
    for r in stops:
        if r.side == "truth":
            truth.setdefault(r.item_id, []).append(r)
    items = {}
    late = [r for r in stops if r.side == "rumour" and r.at <= now - LATE]
    if late:
        items = {
            i.id: i
            for i in await db.scalars(select(Item).where(Item.id.in_({r.item_id for r in late})))
        }
    for r in late:
        if any(_covers(t, r) for t in truth.get(r.item_id, [])):
            continue
        item = items.get(r.item_id)
        if item is None:
            continue
        out.append(
            Notice(
                id=f"gap:{r.id}",
                kind="truth_late",
                at=r.at + LATE,
                title=item.title,
                detail=r.place,
                ref=(item.data or {}).get("ref"),
                href=f"/claims/{item.id}#trajet",
                demo=bool((item.data or {}).get("demo")),
            )
        )
    out.sort(key=lambda n: n.at, reverse=True)
    return out[:MAX_NOTICES]


@router.get("/workspaces/{ws}/live")
async def live(
    member: AnyMember, db: Db, hours: int = Query(default=24, ge=1, le=168)
) -> list[Notice]:
    return await notices(db, member.workspace_id, hours)
