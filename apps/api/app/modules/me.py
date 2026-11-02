import uuid

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from app.core.access import Db
from app.core.models import Membership, Workspace
from app.core.security import User
from app.modules.verification import is_platform_admin

router = APIRouter(tags=["me"])


class MembershipOut(BaseModel):
    workspace_id: uuid.UUID
    name: str
    slug: str
    verification: str


class MeOut(BaseModel):
    id: str
    email: str | None
    name: str | None
    memberships: list[MembershipOut]
    # Member of the Checky team that verifies newsrooms (PLATFORM_ADMINS).
    platform_admin: bool = False


@router.get("/me")
async def me(user: User, db: Db) -> MeOut:
    rows = await db.execute(
        select(Workspace)
        .join(Membership, Membership.workspace_id == Workspace.id)
        .where(Membership.user_id == user.id)
        .order_by(Workspace.created_at)
    )
    memberships = [
        MembershipOut(workspace_id=w.id, name=w.name, slug=w.slug, verification=w.verification)
        for w in rows.scalars()
    ]
    return MeOut(
        id=user.id,
        email=user.email,
        name=user.name,
        memberships=memberships,
        platform_admin=is_platform_admin(user),
    )
