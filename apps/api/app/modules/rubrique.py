"""Personal newsroom desk. Beats are editable interests, never a fixed country taxonomy."""

import uuid

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.access import AnyMember, Db
from app.core.models import Item, MemberPref
from app.modules.items import ItemOut

router = APIRouter(tags=["rubrique"])


class Interests(BaseModel):
    beats: list[str] = Field(default_factory=list, max_length=20)
    regions: list[str] = Field(default_factory=list, max_length=30)


class RubriqueOut(BaseModel):
    interests: Interests
    items: list[ItemOut]


@router.get("/workspaces/{ws}/rubrique")
async def rubrique(member: AnyMember, db: Db) -> RubriqueOut:
    pref = await db.scalar(
        select(MemberPref).where(
            MemberPref.workspace_id == member.workspace_id, MemberPref.user_id == member.user.id
        )
    )
    interests = Interests(beats=pref.beats, regions=pref.regions) if pref else Interests()
    stmt = select(Item).where(Item.workspace_id == member.workspace_id)
    if interests.beats:
        stmt = stmt.where(Item.tags.overlap(interests.beats))
    return RubriqueOut(
        interests=interests,
        items=[
            ItemOut.model_validate(i)
            for i in await db.scalars(stmt.order_by(Item.updated_at.desc()).limit(30))
        ],
    )


@router.put("/workspaces/{ws}/rubrique")
async def preferences(body: Interests, member: AnyMember, db: Db) -> Interests:
    from sqlalchemy.dialects.postgresql import insert

    await db.execute(
        insert(MemberPref)
        .values(
            id=uuid.uuid4(),
            workspace_id=member.workspace_id,
            user_id=member.user.id,
            beats=body.beats,
            regions=body.regions,
        )
        .on_conflict_do_update(
            index_elements=["workspace_id", "user_id"],
            set_={"beats": body.beats, "regions": body.regions},
        )
    )
    await db.commit()
    return body
