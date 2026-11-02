"""Workspace membership and role checks shared by every /workspaces/{ws} route."""

import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.errors import ApiError
from app.core.models import Membership
from app.core.security import CurrentUser, User

# A `veilleur` (partner-radio journalist, correspondent) only reports what was heard; an `issuer`
# (an institution) only keeps its own originals and seals. Neither reads the desk's dossiers.
RANK = {"veilleur": 0, "issuer": 0, "journalist": 1, "editor": 2, "admin": 3}

Db = Annotated[AsyncSession, Depends(get_db)]


@dataclass(frozen=True)
class Member:
    user: CurrentUser
    workspace_id: uuid.UUID
    role: str

    def at_least(self, role: str) -> bool:
        return RANK[self.role] >= RANK[role]


async def get_membership(db: AsyncSession, ws: uuid.UUID, user_id: str) -> Membership | None:
    return await db.scalar(
        select(Membership).where(Membership.workspace_id == ws, Membership.user_id == user_id)
    )


def require_role(min_role: str = "journalist"):
    async def dep(ws: uuid.UUID, user: User, db: Db) -> Member:
        m = await get_membership(db, ws, user.id)
        if m is None:
            # 404, not 403: outsiders must not learn the workspace exists.
            raise ApiError(404, "not_found", "Workspace not found")
        if RANK[m.role] < RANK[min_role]:
            raise ApiError(403, "forbidden", f"Requires role {min_role}")
        return Member(user=user, workspace_id=ws, role=m.role)

    return dep


def require_any(*roles: str):
    """Members holding one of `roles` exactly (for the doors rank does not describe)."""

    async def dep(ws: uuid.UUID, user: User, db: Db) -> Member:
        m = await get_membership(db, ws, user.id)
        if m is None:
            raise ApiError(404, "not_found", "Workspace not found")
        if m.role not in roles:
            raise ApiError(403, "forbidden", f"Requires one of {', '.join(roles)}")
        return Member(user=user, workspace_id=ws, role=m.role)

    return dep


AnyMember = Annotated[Member, Depends(require_role("journalist"))]
Editor = Annotated[Member, Depends(require_role("editor"))]
Admin = Annotated[Member, Depends(require_role("admin"))]
# Every member of the newsroom, veilleurs and issuers included.
Anyone = Annotated[Member, Depends(require_role("veilleur"))]
# Veilleur routes: a veilleur, or any desk member (a journalist can record a radio too).
Veilleur = Annotated[Member, Depends(require_any("veilleur", "journalist", "editor", "admin"))]
# Registry writes and seals: the institution's own account, or the newsroom's admin.
Issuer = Annotated[Member, Depends(require_any("issuer", "admin", "editor"))]
