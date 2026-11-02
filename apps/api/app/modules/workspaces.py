import re
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select

from app.core.access import Admin, AnyMember, Anyone, Db, get_membership
from app.core.errors import ApiError
from app.core.models import DEFAULT_BEATS, Invitation, Membership, Workspace, auth_user
from app.core.security import User

router = APIRouter(tags=["workspaces"])

Role = Literal["admin", "editor", "journalist", "veilleur", "issuer"]


class WorkspaceIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class WorkspaceOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    role: Role


class MemberOut(BaseModel):
    user_id: str
    role: Role
    name: str | None = None
    email: str | None = None


class InvitationIn(BaseModel):
    role: Role = "journalist"


class InvitationOut(BaseModel):
    token: str
    role: Role
    expires_at: datetime


class NewsroomSettings(BaseModel):
    """A newsroom's own rules, kept in `workspace.settings` (JSONB): a field left out of a PATCH
    keeps its value, and a newsroom that never set one reads the default."""

    # A journalist signs (`verified`), a different editor releases (`published`).
    double_signature: bool = False
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
    settings: NewsroomSettings = Field(default_factory=NewsroomSettings)


class WorkspacePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    is_public: bool | None = None
    settings: NewsroomSettings | None = None


class RoleIn(BaseModel):
    role: Role


def _slugify(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "workspace"
    return f"{base[:120]}-{secrets.token_hex(3)}"


@router.post("/workspaces", status_code=201)
async def create_workspace(body: WorkspaceIn, user: User, db: Db) -> WorkspaceOut:
    ws = Workspace(name=body.name, slug=_slugify(body.name))
    db.add(ws)
    await db.flush()
    db.add(Membership(workspace_id=ws.id, user_id=user.id, role="admin"))
    await db.commit()
    return WorkspaceOut(id=ws.id, name=ws.name, slug=ws.slug, role="admin")


@router.get("/workspaces/{ws}")
async def get_workspace(member: Anyone, db: Db) -> WorkspaceSettingsOut:
    ws = await db.get(Workspace, member.workspace_id)
    return WorkspaceSettingsOut(
        id=ws.id,
        name=ws.name,
        slug=ws.slug,
        is_public=ws.is_public,
        settings=newsroom_settings(ws),
    )


@router.patch("/workspaces/{ws}")
async def update_workspace(body: WorkspacePatch, admin: Admin, db: Db) -> WorkspaceSettingsOut:
    ws = await db.get(Workspace, admin.workspace_id)
    if body.name is not None:
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
    return [
        MemberOut(user_id=m.user_id, role=m.role, name=name, email=email) for m, name, email in rows
    ]


@router.post("/workspaces/{ws}/invitations", status_code=201)
async def create_invitation(body: InvitationIn, admin: Admin, db: Db) -> InvitationOut:
    inv = Invitation(
        workspace_id=admin.workspace_id,
        token=secrets.token_urlsafe(24),
        role=body.role,
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )
    db.add(inv)
    await db.commit()
    return InvitationOut(token=inv.token, role=inv.role, expires_at=inv.expires_at)


@router.post("/invitations/{token}/accept")
async def accept_invitation(token: str, user: User, db: Db) -> WorkspaceOut:
    inv = await db.scalar(select(Invitation).where(Invitation.token == token).with_for_update())
    if inv is None or inv.used_at is not None or inv.expires_at < datetime.now(UTC):
        raise ApiError(404, "invalid_invitation", "Invitation is invalid or expired")
    ws = await db.get(Workspace, inv.workspace_id)
    existing = await get_membership(db, inv.workspace_id, user.id)
    role = existing.role if existing else inv.role
    if existing is None:
        db.add(Membership(workspace_id=inv.workspace_id, user_id=user.id, role=inv.role))
    inv.used_at = datetime.now(UTC)
    await db.commit()
    return WorkspaceOut(id=ws.id, name=ws.name, slug=ws.slug, role=role)


async def _target(db: Db, admin, user_id: str) -> Membership:
    m = await get_membership(db, admin.workspace_id, user_id)
    if m is None:
        raise ApiError(404, "not_found", "Member not found")
    return m


async def _guard_last_admin(db: Db, admin, m: Membership) -> None:
    if m.role != "admin":
        return
    admins = await db.scalars(
        select(Membership).where(
            Membership.workspace_id == admin.workspace_id, Membership.role == "admin"
        )
    )
    if len(admins.all()) <= 1:
        raise ApiError(409, "last_admin", "A workspace needs at least one admin")


@router.patch("/workspaces/{ws}/members/{user_id}")
async def change_role(user_id: str, body: RoleIn, admin: Admin, db: Db) -> MemberOut:
    m = await _target(db, admin, user_id)
    if body.role != "admin":
        await _guard_last_admin(db, admin, m)
    m.role = body.role
    await db.commit()
    return MemberOut(user_id=m.user_id, role=m.role)


@router.delete("/workspaces/{ws}/members/{user_id}", status_code=204)
async def remove_member(user_id: str, admin: Admin, db: Db) -> None:
    m = await _target(db, admin, user_id)
    await _guard_last_admin(db, admin, m)
    await db.delete(m)
    await db.commit()
