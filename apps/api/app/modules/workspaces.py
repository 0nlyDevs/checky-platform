import re
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, or_, select

from app.core import places
from app.core.access import AnyMember, Db, get_membership
from app.core.config import get_settings
from app.core.errors import ApiError
from app.core.models import (
    DEFAULT_BEATS,
    Invitation,
    Membership,
    RadioPartner,
    Route,
    Workspace,
    auth_user,
)
from app.core.security import User

router = APIRouter(tags=["workspaces"])


class WorkspaceIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class WorkspaceOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str


class MemberOut(BaseModel):
    user_id: str
    name: str | None = None
    email: str | None = None


class InvitationOut(BaseModel):
    token: str
    expires_at: datetime


class NewsroomSettings(BaseModel):
    """A newsroom's own rules, kept in `workspace.settings` (JSONB): a field left out of a PATCH
    keeps its value, and a newsroom that never set one reads the default."""

    # « Mode sans IA »: the model nodes are skipped, the facts still show.
    ai_enabled: bool = True
    # The newsroom's beats (rubriques), offered in Ma rubrique and used to file claims.
    beats: list[str] = Field(default_factory=lambda: list(DEFAULT_BEATS), max_length=40)
    # Dates shown to the newsroom and the flashes of the day are counted in this time zone.
    timezone: str = "Indian/Antananarivo"
    country: str = Field(default="Madagascar", min_length=2, max_length=80)
    # The newsroom's home region: an SMS from there lands in this newsroom first (optional).
    region: str | None = Field(default=None, max_length=120)

    @field_validator("beats")
    @classmethod
    def clean_beats(cls, value: list[str]) -> list[str]:
        out: list[str] = []
        for beat in value:
            beat = re.sub(r"\s+", " ", beat).strip().lower()
            if not 1 <= len(beat) <= 40:
                raise ValueError("A beat is 1 to 40 characters long")
            if beat not in out:
                out.append(beat)
        return out

    @field_validator("timezone")
    @classmethod
    def known_zone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(
                "Unknown time zone (use an IANA name such as Indian/Antananarivo)"
            ) from exc
        return value

    @field_validator("country", "region")
    @classmethod
    def trimmed(cls, value: str | None) -> str | None:
        value = re.sub(r"\s+", " ", value).strip() if value else None
        return value or None


def newsroom_settings(ws: Workspace) -> NewsroomSettings:
    """The stored settings with the defaults filled in; an unreadable old value falls back."""
    try:
        return NewsroomSettings.model_validate(ws.settings or {})
    except ValueError:
        return NewsroomSettings()


class WorkspaceSettingsOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    is_public: bool
    # none | pending | approved | refused (set by the Checky team, see verification.py)
    verification: str = "none"
    settings: NewsroomSettings = Field(default_factory=NewsroomSettings)


class WorkspacePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    is_public: bool | None = None
    settings: NewsroomSettings | None = None


def _slugify(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "workspace"
    return f"{base[:120]}-{secrets.token_hex(3)}"


@router.post("/workspaces", status_code=201)
async def create_workspace(body: WorkspaceIn, user: User, db: Db) -> WorkspaceOut:
    ws = Workspace(name=body.name, slug=_slugify(body.name))
    db.add(ws)
    await db.flush()
    db.add(Membership(workspace_id=ws.id, user_id=user.id))
    await db.commit()
    return WorkspaceOut(id=ws.id, name=ws.name, slug=ws.slug)


@router.get("/workspaces/{ws}")
async def get_workspace(member: AnyMember, db: Db) -> WorkspaceSettingsOut:
    ws = await db.get(Workspace, member.workspace_id)
    return WorkspaceSettingsOut(
        id=ws.id,
        name=ws.name,
        slug=ws.slug,
        is_public=ws.is_public,
        verification=ws.verification,
        settings=newsroom_settings(ws),
    )


@router.patch("/workspaces/{ws}")
async def update_workspace(body: WorkspacePatch, member: AnyMember, db: Db) -> WorkspaceSettingsOut:
    ws = await db.get(Workspace, member.workspace_id)
    if body.name is not None and body.name != ws.name:
        # The public reads this name next to « Rédaction vérifiée par Checky »: once verified it
        # only changes through a new review.
        if ws.verification == "approved":
            raise ApiError(409, "verified_name_locked", "A verified newsroom keeps its name")
        ws.name = body.name
    if body.is_public is not None:
        ws.is_public = body.is_public
    if body.settings is not None:
        ws.settings = {**(ws.settings or {}), **body.settings.model_dump(exclude_unset=True)}
    await db.commit()
    return WorkspaceSettingsOut(
        id=ws.id,
        name=ws.name,
        slug=ws.slug,
        is_public=ws.is_public,
        verification=ws.verification,
        settings=newsroom_settings(ws),
    )


@router.get("/workspaces/{ws}/members")
async def list_members(member: AnyMember, db: Db) -> list[MemberOut]:
    rows = await db.execute(
        select(Membership, auth_user.c.name, auth_user.c.email)
        .outerjoin(auth_user, auth_user.c.id == Membership.user_id)
        .where(Membership.workspace_id == member.workspace_id)
        .order_by(Membership.created_at)
    )
    return [MemberOut(user_id=m.user_id, name=name, email=email) for m, name, email in rows]


@router.post("/workspaces/{ws}/invitations", status_code=201)
async def create_invitation(member: AnyMember, db: Db) -> InvitationOut:
    """A single-use link, valid 7 days: whoever opens it joins as a journalist of the newsroom."""
    inv = Invitation(
        workspace_id=member.workspace_id,
        token=secrets.token_urlsafe(24),
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )
    db.add(inv)
    await db.commit()
    return InvitationOut(token=inv.token, expires_at=inv.expires_at)


@router.post("/invitations/{token}/accept")
async def accept_invitation(token: str, user: User, db: Db) -> WorkspaceOut:
    inv = await db.scalar(select(Invitation).where(Invitation.token == token).with_for_update())
    if inv is None or inv.used_at is not None or inv.expires_at < datetime.now(UTC):
        raise ApiError(404, "invalid_invitation", "Invitation is invalid or expired")
    ws = await db.get(Workspace, inv.workspace_id)
    if await get_membership(db, inv.workspace_id, user.id) is None:
        db.add(Membership(workspace_id=inv.workspace_id, user_id=user.id))
    inv.used_at = datetime.now(UTC)
    await db.commit()
    return WorkspaceOut(id=ws.id, name=ws.name, slug=ws.slug)


@router.delete("/workspaces/{ws}/members/{user_id}", status_code=204)
async def remove_member(user_id: str, member: AnyMember, db: Db) -> None:
    """Any journalist may remove a colleague or leave; a newsroom never loses its last member."""
    m = await get_membership(db, member.workspace_id, user_id)
    if m is None:
        raise ApiError(404, "not_found", "Member not found")
    count = await db.scalar(
        select(func.count())
        .select_from(Membership)
        .where(Membership.workspace_id == member.workspace_id)
    )
    if (count or 0) <= 1:
        raise ApiError(409, "last_member", "A newsroom needs at least one member")
    await db.delete(m)
    await db.commit()


# --- partner radios: they read the day's flashes on air and mark them « Diffusé » by a token link
class RadioIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    frequency: str | None = Field(default=None, max_length=40)
    region: str | None = Field(default=None, max_length=120)
    languages: list[Literal["fr", "mg", "en"]] = Field(default_factory=lambda: ["mg", "fr"])
    contact_role: str | None = Field(default=None, max_length=120)
    whatsapp: str | None = Field(default=None, max_length=60)
    sms: str | None = Field(default=None, max_length=60)
    format_pref: Literal["script", "audio"] = "script"
    hours: str | None = Field(default=None, max_length=120)


class RadioOut(BaseModel):
    id: uuid.UUID
    name: str
    frequency: str | None
    location: dict
    languages: list[str]
    contact_role: str | None
    whatsapp: str | None
    sms: str | None
    format_pref: str
    hours: str | None
    approved: bool
    is_demo: bool
    link: str
    broadcasts: int
    last_broadcast_at: datetime | None


def radio_link(token: str) -> str:
    return f"{get_settings().public_web_url.rstrip('/')}/flashs?radio={token}"


async def _radio_out(db: Db, radio: RadioPartner) -> RadioOut:
    # « Diffusé »: the truth stops the radio marked as broadcast. `POST /public/radios/{token}/
    # diffuse` names the stop « <name> <frequency> » and keeps the partner's id in its proof.
    station = f"{radio.name} {radio.frequency or ''}".strip()
    count, last = (
        await db.execute(
            select(func.count(Route.id), func.max(Route.at)).where(
                Route.workspace_id == radio.workspace_id,
                Route.side == "truth",
                Route.channel == "radio",
                Route.status == "broadcast",
                or_(
                    Route.proof["partner_id"].astext == str(radio.id),
                    Route.proof["radio_id"].astext == str(radio.id),
                    Route.place.in_({radio.name, station}),
                ),
            )
        )
    ).one()
    return RadioOut(
        id=radio.id,
        name=radio.name,
        frequency=radio.frequency,
        location=radio.location or {},
        languages=list(radio.languages or []),
        contact_role=radio.contact_role,
        whatsapp=radio.whatsapp,
        sms=radio.sms,
        format_pref=radio.format_pref,
        hours=radio.hours,
        approved=radio.approved,
        is_demo=radio.is_demo,
        link=radio_link(radio.token),
        broadcasts=count or 0,
        last_broadcast_at=last,
    )


@router.get("/workspaces/{ws}/radios")
async def radios(member: AnyMember, db: Db) -> list[RadioOut]:
    rows = await db.scalars(
        select(RadioPartner)
        .where(RadioPartner.workspace_id == member.workspace_id)
        .order_by(RadioPartner.name)
    )
    return [await _radio_out(db, r) for r in rows]


@router.post("/workspaces/{ws}/radios", status_code=201)
async def create_radio(body: RadioIn, member: AnyMember, db: Db) -> RadioOut:
    region = (body.region or "").strip()
    location = places.gazetteer(region) if region else None
    if region and location is None:
        location = places.place(region, region=region)
    radio = RadioPartner(
        workspace_id=member.workspace_id,
        name=body.name.strip(),
        frequency=body.frequency,
        location=location or {},
        languages=list(dict.fromkeys(body.languages)),
        contact_role=body.contact_role,
        whatsapp=body.whatsapp,
        sms=body.sms,
        format_pref=body.format_pref,
        hours=body.hours,
        token=secrets.token_urlsafe(24),
    )
    db.add(radio)
    await db.commit()
    await db.refresh(radio)
    return await _radio_out(db, radio)


@router.delete("/workspaces/{ws}/radios/{radio_id}", status_code=204)
async def delete_radio(radio_id: uuid.UUID, member: AnyMember, db: Db) -> None:
    radio = await db.get(RadioPartner, radio_id)
    if radio is None or radio.workspace_id != member.workspace_id:
        raise ApiError(404, "not_found", "Radio not found")
    await db.delete(radio)
    await db.commit()
