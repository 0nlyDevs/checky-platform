"""Documented sightings and delivery records. Never infer reach from a click or download."""

import uuid
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field, HttpUrl
from sqlalchemy import select

from app.core.access import AnyMember, Db
from app.core.activity import record
from app.core.config import get_settings
from app.core.errors import ApiError
from app.core.models import Route
from app.modules.items import _get_item

router = APIRouter(tags=["trajet"])


class RouteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    side: Literal["rumour", "truth"]
    channel: Literal[
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
    place: str = Field(min_length=1, max_length=300)
    note: str = Field(min_length=5, max_length=1000)
    url: HttpUrl | None = None
    at: datetime


class RouteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    side: str
    channel: str
    place: str
    status: str
    proof: dict
    at: datetime


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
    route = Route(
        workspace_id=member.workspace_id,
        item_id=item_id,
        added_by=member.user.id,
        side=body.side,
        channel=body.channel,
        place=body.place,
        at=body.at,
        status="reported",
        auto=False,
        proof={
            "note": body.note,
            "url": str(body.url) if body.url else None,
            "method": "member_report",
        },
    )
    db.add(route)
    await db.flush()
    await record(
        db,
        member.workspace_id,
        member.user.id,
        "item",
        item_id,
        "route",
        {"route_id": str(route.id), "side": route.side, "channel": route.channel},
    )
    await db.commit()
    return RouteOut.model_validate(route)


class FormatsOut(BaseModel):
    radio: str
    sms: str
    social: str
    url: str
    delivery: Literal["draft_only"] = "draft_only"


@router.get("/workspaces/{ws}/items/{item_id}/diffusion")
async def formats(item_id: uuid.UUID, member: AnyMember, db: Db) -> FormatsOut:
    from app.core.models import Workspace

    item = await _get_item(db, member, item_id)
    if item.status != "published" or item.data.get("verdict") not in (
        "true",
        "false",
        "misleading",
        "unverifiable",
    ):
        raise ApiError(409, "not_published", "Publish a newsroom verdict first")
    workspace = await db.get(Workspace, member.workspace_id)
    if not workspace.is_public:
        raise ApiError(
            409, "private_workspace", "Enable public verdicts before preparing public links"
        )
    reason = str(item.data.get("reason") or "").strip()
    if not reason:
        raise ApiError(409, "missing_reason", "Write a public explanation first")
    verdict = {
        "true": "Vrai",
        "false": "Faux",
        "misleading": "Trompeur",
        "unverifiable": "Invérifiable",
    }[item.data["verdict"]]
    url = get_settings().public_web_url.rstrip("/") + "/verifies/" + str(item.id)
    return FormatsOut(
        radio=f"{workspace.name} a vérifié : {item.title}. Conclusion : {verdict}. {reason}",
        sms=f"{verdict} — {item.title[:90]}. {url}",
        social=f"{verdict} · {workspace.name}\n{item.title}\n\n{reason}\n\n{url}",
        url=url,
    )
