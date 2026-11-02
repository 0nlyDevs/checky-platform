"""Workspace membership shared by every /workspaces/{ws} route.

Checky has one kind of account: every member of a newsroom is one of its journalists and may do
everything the newsroom can do. Outsiders get 404, so they never learn a workspace exists.
"""

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

Db = Annotated[AsyncSession, Depends(get_db)]


@dataclass(frozen=True)
class Member:
    user: CurrentUser
    workspace_id: uuid.UUID


async def get_membership(db: AsyncSession, ws: uuid.UUID, user_id: str) -> Membership | None:
    return await db.scalar(
        select(Membership).where(Membership.workspace_id == ws, Membership.user_id == user_id)
    )


async def _membership(db: AsyncSession, ws: uuid.UUID, user_id: str) -> Membership | None:
    """The membership, read in a transaction that is closed at once.

    The request's session lives as long as the route, and an SSE route (crew, ask, agent…) keeps
    it for minutes: left open, this read would hold a pooled connection « idle in transaction »
    for the whole stream. Committing a read-only transaction releases the connection; the route
    begins a new one when it touches the database again.
    """
    m = await get_membership(db, ws, user_id)
    await db.commit()
    return m


async def require_member(ws: uuid.UUID, user: User, db: Db) -> Member:
    if await _membership(db, ws, user.id) is None:
        # 404, not 403: outsiders must not learn the workspace exists.
        raise ApiError(404, "not_found", "Workspace not found")
    return Member(user=user, workspace_id=ws)


AnyMember = Annotated[Member, Depends(require_member)]
