import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select

from app.core.access import AnyMember, Db, Editor, Member
from app.core.activity import broadcast, record
from app.core.errors import ApiError
from app.core.models import Activity, Comment, Item

router = APIRouter(tags=["items"])


class ItemIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    body: str = ""
    type: str = "claim"
    status: str = "to_check"
    tags: list[str] = []
    data: dict[str, Any] = {}


class ItemPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    body: str | None = None
    type: str | None = None
    status: str | None = None
    tags: list[str] | None = None
    # Merged into the existing JSONB, so day-one fields need no migration.
    data: dict[str, Any] | None = None


class ItemOut(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    workspace_id: uuid.UUID
    author_id: str
    type: str
    title: str
    body: str
    status: str
    tags: list[str]
    data: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class ItemPage(BaseModel):
    items: list[ItemOut]
    total: int


class CommentIn(BaseModel):
    body: str = Field(min_length=1)


class CommentOut(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    item_id: uuid.UUID
    author_id: str
    body: str
    created_at: datetime


class ActivityOut(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    actor_id: str
    entity: str
    entity_id: uuid.UUID
    action: str
    diff: dict[str, Any]
    created_at: datetime


def _out(item: Item) -> dict:
    return ItemOut.model_validate(item).model_dump(mode="json")


async def _get_item(db: Db, member: Member, item_id: uuid.UUID) -> Item:
    item = await db.get(Item, item_id)
    if item is None or item.workspace_id != member.workspace_id:
        raise ApiError(404, "not_found", "Item not found")
    return item


@router.get("/workspaces/{ws}/items")
async def list_items(
    member: AnyMember,
    db: Db,
    status: str | None = None,
    type: str | None = None,
    tag: str | None = None,
    q: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> ItemPage:
    where = [Item.workspace_id == member.workspace_id]
    if status:
        where.append(Item.status == status)
    if type:
        where.append(Item.type == type)
    if tag:
        where.append(Item.tags.contains([tag]))
    if q:
        like = f"%{q}%"
        where.append(or_(Item.title.ilike(like), Item.body.ilike(like)))
    total = await db.scalar(select(func.count()).select_from(Item).where(*where))
    rows = await db.scalars(
        select(Item).where(*where).order_by(Item.created_at.desc()).limit(limit).offset(offset)
    )
    return ItemPage(items=[ItemOut.model_validate(i) for i in rows], total=total or 0)


@router.post("/workspaces/{ws}/items", status_code=201)
async def create_item(body: ItemIn, member: AnyMember, db: Db) -> ItemOut:
    item = Item(workspace_id=member.workspace_id, author_id=member.user.id, **body.model_dump())
    db.add(item)
    await db.flush()
    await record(db, member.workspace_id, member.user.id, "item", item.id, "create")
    await db.commit()
    await db.refresh(item)
    await broadcast(member.workspace_id, "item.created", _out(item))
    return ItemOut.model_validate(item)


@router.get("/workspaces/{ws}/items/{item_id}")
async def get_item(item_id: uuid.UUID, member: AnyMember, db: Db) -> ItemOut:
    return ItemOut.model_validate(await _get_item(db, member, item_id))


@router.patch("/workspaces/{ws}/items/{item_id}")
async def update_item(item_id: uuid.UUID, body: ItemPatch, member: AnyMember, db: Db) -> ItemOut:
    item = await _get_item(db, member, item_id)
    if item.author_id != member.user.id and not member.at_least("editor"):
        raise ApiError(403, "forbidden", "Only the author or an editor can edit this item")
    changes = body.model_dump(exclude_unset=True)
    diff = {}
    for field, value in changes.items():
        if field == "data":
            value = {**item.data, **value}
        old = getattr(item, field)
        if old != value:
            diff[field] = {"from": old, "to": value}
            setattr(item, field, value)
    if diff:
        await record(db, member.workspace_id, member.user.id, "item", item.id, "update", diff)
        await db.commit()
        await db.refresh(item)
        await broadcast(member.workspace_id, "item.updated", _out(item))
    return ItemOut.model_validate(item)


@router.delete("/workspaces/{ws}/items/{item_id}", status_code=204)
async def delete_item(item_id: uuid.UUID, member: Editor, db: Db) -> None:
    item = await _get_item(db, member, item_id)
    await db.delete(item)
    await record(db, member.workspace_id, member.user.id, "item", item_id, "delete")
    await db.commit()
    await broadcast(member.workspace_id, "item.deleted", {"id": str(item_id)})


@router.get("/workspaces/{ws}/items/{item_id}/comments")
async def list_comments(item_id: uuid.UUID, member: AnyMember, db: Db) -> list[CommentOut]:
    await _get_item(db, member, item_id)
    rows = await db.scalars(
        select(Comment).where(Comment.item_id == item_id).order_by(Comment.created_at)
    )
    return [CommentOut.model_validate(c) for c in rows]


@router.post("/workspaces/{ws}/items/{item_id}/comments", status_code=201)
async def add_comment(item_id: uuid.UUID, body: CommentIn, member: AnyMember, db: Db) -> CommentOut:
    await _get_item(db, member, item_id)
    c = Comment(item_id=item_id, author_id=member.user.id, body=body.body)
    db.add(c)
    await db.flush()
    # Logged against the claim, so its history reads as one thread.
    await record(
        db,
        member.workspace_id,
        member.user.id,
        "item",
        item_id,
        "comment",
        {"comment_id": str(c.id)},
    )
    await db.commit()
    await db.refresh(c)
    out = CommentOut.model_validate(c)
    await broadcast(member.workspace_id, "comment.created", out.model_dump(mode="json"))
    return out


@router.get("/workspaces/{ws}/activity")
async def list_activity(
    member: AnyMember,
    db: Db,
    entity_id: uuid.UUID | None = None,
    limit: int = Query(50, ge=1, le=200),
) -> list[ActivityOut]:
    where = [Activity.workspace_id == member.workspace_id]
    if entity_id:
        where.append(Activity.entity_id == entity_id)
    rows = await db.scalars(
        select(Activity).where(*where).order_by(Activity.created_at.desc()).limit(limit)
    )
    return [ActivityOut.model_validate(a) for a in rows]
