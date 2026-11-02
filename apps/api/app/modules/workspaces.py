import re
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.access import Admin, AnyMember, Db, get_membership
from app.core.errors import ApiError
from app.core.models import Invitation, Membership, Workspace, auth_user
from app.core.security import User

router = APIRouter(tags=["workspaces"])

Role = Literal["admin", "editor", "journalist"]


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


class WorkspaceSettingsOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    is_public: bool


class WorkspacePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    is_public: bool | None = None


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
async def get_workspace(member: AnyMember, db: Db) -> WorkspaceSettingsOut:
    ws = await db.get(Workspace, member.workspace_id)
    return WorkspaceSettingsOut(id=ws.id, name=ws.name, slug=ws.slug, is_public=ws.is_public)


@router.patch("/workspaces/{ws}")
async def update_workspace(body: WorkspacePatch, admin: Admin, db: Db) -> WorkspaceSettingsOut:
    ws = await db.get(Workspace, admin.workspace_id)
    if body.name is not None:
        ws.name = body.name
    if body.is_public is not None:
        ws.is_public = body.is_public
    await db.commit()
    return WorkspaceSettingsOut(id=ws.id, name=ws.name, slug=ws.slug, is_public=ws.is_public)


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
