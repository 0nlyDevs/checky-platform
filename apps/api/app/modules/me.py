import uuid
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from app.core.access import Db
from app.core.models import Membership, Workspace
from app.core.security import User

router = APIRouter(tags=["me"])


class MembershipOut(BaseModel):
    workspace_id: uuid.UUID
    name: str
    slug: str
    role: Literal["admin", "editor", "journalist", "veilleur", "issuer"]


class MeOut(BaseModel):
    id: str
    email: str | None
    name: str | None
    memberships: list[MembershipOut]


@router.get("/me")
async def me(user: User, db: Db) -> MeOut:
    rows = await db.execute(
        select(Workspace, Membership.role)
        .join(Membership, Membership.workspace_id == Workspace.id)
        .where(Membership.user_id == user.id)
        .order_by(Workspace.created_at)
    )
    memberships = [
        MembershipOut(workspace_id=w.id, name=w.name, slug=w.slug, role=role) for w, role in rows
    ]
    return MeOut(id=user.id, email=user.email, name=user.name, memberships=memberships)
