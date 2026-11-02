"""Verified newsrooms: « Tout le monde peut vérifier ; seules les rédactions vérifiées publient ».

A newsroom sends a request (outlet, city, country, official page, the person, a phone number). The
Checky team (`PLATFORM_ADMINS`, emails in the server config, not a role inside a newsroom) calls
the number shown on the outlet's official page and approves or refuses with a reason. Until it is
approved the newsroom works privately: nothing of it leaves (archive, tips, SMS, partner radios,
« Vérifié par »). The personal data in a request is only shown to the Checky team.
"""

import re
import uuid
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select

from app.core import countries
from app.core.access import AnyMember, Db
from app.core.config import get_settings
from app.core.errors import ApiError
from app.core.models import Membership, NewsroomRequest, Workspace
from app.core.security import CurrentUser, User

router = APIRouter(tags=["verification"])

Kind = Literal["radio", "tv", "press", "online"]
Status = Literal["none", "pending", "approved", "refused"]


def is_platform_admin(user: CurrentUser) -> bool:
    admins = {e.strip().casefold() for e in get_settings().platform_admins.split(",") if e.strip()}
    return bool(user.email) and user.email.casefold() in admins


def _require_admin(user: CurrentUser) -> None:
    if not is_platform_admin(user):
        # 404, like a workspace outsiders may not see: the page does not exist for them.
        raise ApiError(404, "not_found", "Not found")


def _clean(value: str | None) -> str | None:
    value = re.sub(r"\s+", " ", value).strip() if value else None
    return value or None


class RequestIn(BaseModel):
    outlet: str = Field(min_length=2, max_length=160)
    kind: Kind
    city: str = Field(min_length=2, max_length=120)
    region: str | None = Field(default=None, max_length=120)
    country: str = Field(min_length=2, max_length=2)
    website: str = Field(min_length=4, max_length=500)
    full_name: str = Field(min_length=3, max_length=160)
    job_title: str = Field(min_length=2, max_length=120)
    phone: str = Field(min_length=6, max_length=32)
    email: str = Field(max_length=254)
    press_card: str | None = Field(default=None, max_length=120)

    @field_validator("outlet", "city", "region", "full_name", "job_title", "press_card")
    @classmethod
    def trimmed(cls, value: str | None) -> str | None:
        return _clean(value)

    @field_validator("email")
    @classmethod
    def address(cls, value: str) -> str:
        value = value.strip().lower()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
            raise ValueError("Give a professional email address")
        return value

    @field_validator("country")
    @classmethod
    def known_country(cls, value: str) -> str:
        if countries.name(value) is None:
            raise ValueError("Unknown country code")
        return value.upper()

    @field_validator("website")
    @classmethod
    def page(cls, value: str) -> str:
        value = value.strip()
        if not re.match(r"^https?://", value, re.IGNORECASE):
            value = "https://" + value
        if not re.match(r"^https?://[^\s/]+\.[^\s/]+", value, re.IGNORECASE):
            raise ValueError("Give the outlet's website or official Facebook page")
        return value


class RequestOut(BaseModel):
    outlet: str
    kind: str
    city: str
    region: str | None
    country: str
    country_name: str
    website: str
    full_name: str
    job_title: str
    phone: str
    email: str
    press_card: str | None


class VerificationOut(BaseModel):
    status: Status
    reason: str | None = None
    submitted_at: datetime | None = None
    reviewed_at: datetime | None = None
    request: RequestOut | None = None


def _request_out(r: NewsroomRequest) -> RequestOut:
    return RequestOut(
        outlet=r.outlet,
        kind=r.kind,
        city=r.city,
        region=r.region,
        country=r.country,
        country_name=countries.name(r.country) or r.country,
        website=r.website,
        full_name=r.full_name,
        job_title=r.job_title,
        phone=r.phone,
        email=r.email,
        press_card=r.press_card,
    )


def _out(ws: Workspace, r: NewsroomRequest | None) -> VerificationOut:
    return VerificationOut(
        status=ws.verification,  # type: ignore[arg-type]
        reason=r.reason if r and ws.verification == "refused" else None,
        submitted_at=r.updated_at if r else None,
        reviewed_at=r.reviewed_at if r else None,
        request=_request_out(r) if r else None,
    )


async def _request(db: Db, ws: uuid.UUID) -> NewsroomRequest | None:
    return await db.scalar(select(NewsroomRequest).where(NewsroomRequest.workspace_id == ws))


@router.get("/workspaces/{ws}/verification")
async def get_verification(member: AnyMember, db: Db) -> VerificationOut:
    ws = await db.get(Workspace, member.workspace_id)
    return _out(ws, await _request(db, ws.id))


@router.put("/workspaces/{ws}/verification")
async def request_verification(body: RequestIn, member: AnyMember, db: Db) -> VerificationOut:
    """Send (or correct and send again) the request. An approved newsroom stays approved."""
    ws = await db.get(Workspace, member.workspace_id)
    if ws.verification == "approved":
        raise ApiError(409, "already_verified", "This newsroom is already verified")
    phone = countries.phone(body.phone, body.country)
    if phone is None:
        raise ApiError(422, "invalid_phone", "This phone number is not valid for that country")
    r = await _request(db, ws.id)
    fields = body.model_dump() | {"phone": phone}
    if r is None:
        r = NewsroomRequest(workspace_id=ws.id, submitted_by=member.user.id, **fields)
        db.add(r)
    else:
        for key, value in fields.items():
            setattr(r, key, value)
        r.submitted_by = member.user.id
        r.reason = r.reviewed_by = r.reviewed_at = None
    ws.verification = "pending"
    ws.settings = {**(ws.settings or {}), "country": countries.name(body.country)}
    await db.commit()
    await db.refresh(r)
    return _out(ws, r)


# The Checky team ------------------------------------------------------------------------------


class AdminRequestOut(BaseModel):
    workspace_id: uuid.UUID
    newsroom: str
    status: Status
    members: int
    created_at: datetime
    submitted_at: datetime
    reason: str | None
    reviewed_at: datetime | None
    request: RequestOut


class RefuseIn(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)


@router.get("/platform/requests")
async def list_requests(user: User, db: Db, status: Status | None = None) -> list[AdminRequestOut]:
    _require_admin(user)
    members = (
        select(func.count())
        .select_from(Membership)
        .where(Membership.workspace_id == Workspace.id)
        .scalar_subquery()
    )
    q = (
        select(NewsroomRequest, Workspace, members)
        .join(Workspace, Workspace.id == NewsroomRequest.workspace_id)
        .order_by(NewsroomRequest.updated_at.desc())
    )
    if status:
        q = q.where(Workspace.verification == status)
    rows = await db.execute(q)
    return [
        AdminRequestOut(
            workspace_id=ws.id,
            newsroom=ws.name,
            status=ws.verification,  # type: ignore[arg-type]
            members=n,
            created_at=ws.created_at,
            submitted_at=r.updated_at,
            reason=r.reason,
            reviewed_at=r.reviewed_at,
            request=_request_out(r),
        )
        for r, ws, n in rows.all()
    ]


async def _review(db: Db, user: CurrentUser, ws_id: uuid.UUID) -> tuple[Workspace, NewsroomRequest]:
    _require_admin(user)
    ws = await db.get(Workspace, ws_id)
    r = await _request(db, ws_id)
    if ws is None or r is None:
        raise ApiError(404, "not_found", "No request for this newsroom")
    r.reviewed_by = user.id
    r.reviewed_at = datetime.now(UTC)
    return ws, r


@router.post("/platform/requests/{ws}/approve")
async def approve(ws: uuid.UUID, user: User, db: Db) -> VerificationOut:
    workspace, r = await _review(db, user, ws)
    workspace.verification = "approved"
    r.reason = None
    await db.commit()
    await db.refresh(r)
    return _out(workspace, r)


@router.post("/platform/requests/{ws}/refuse")
async def refuse(ws: uuid.UUID, body: RefuseIn, user: User, db: Db) -> VerificationOut:
    workspace, r = await _review(db, user, ws)
    workspace.verification = "refused"
    r.reason = body.reason.strip()
    await db.commit()
    await db.refresh(r)
    return _out(workspace, r)
