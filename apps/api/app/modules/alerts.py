"""« Fanairana »: the danger level a journalist adjusts, and the alerts a newsroom raises.

A rumour that can hurt (a kidnapping said to have happened, a fake official order, a call to
violence) rarely arrives once. The same story comes back as a tip, an SMS, a radio clip, a
veilleur's sentence, a press item and a dossier, in French or Malagasy, sometimes about another
town. This module:

- lets a journalist adjust the danger level Checky computed (`item.data.risk_override`, logged in
  the Carnet); the adjusted level wins everywhere (`veille.risk_level`);
"""

import logging
import uuid
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from app.core.access import AnyMember, Db
from app.core.activity import broadcast, record
from app.core.errors import ApiError
from app.modules.items import ItemOut, _get_item, _out
from app.modules.veille import RISK_LEVELS, risk_level

log = logging.getLogger("checky.alerts")
router = APIRouter(tags=["alerts"])

RISK_FR = {"high": "élevé", "medium": "moyen", "low": "faible"}


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


__all__ = ["RISK_FR", "RISK_LEVELS", "router"]
