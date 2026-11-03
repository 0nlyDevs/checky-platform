import base64
import binascii
import uuid
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from sqlalchemy import TIMESTAMP, and_, case, cast, func, not_, or_, select, tuple_

from app.core.access import AnyMember, Db, Member
from app.core.activity import broadcast, record
from app.core.errors import ApiError
from app.core.models import Activity, Comment, Item
from app.core.refs import next_ref
from app.core.words import words

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
    # Merged into the existing JSONB, so new fields need no migration.
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
    # With `order`: the cursor of the next page (`after=`), null on the last one.
    next: str | None = None
    # With `tab`: how many dossiers each tab holds under the same search and assignee.
    counts: dict[str, int] | None = None


VERDICTS = ("true", "misleading", "false", "unverifiable")
TABS = ("all", "todo", "confirm", "done")

# When the rumour was first seen, else when the item was created. `first_seen_at` is free text in
# the JSONB, so it is only cast when Postgres says it reads as a timestamp (never a 500).
_seen_text = Item.data["first_seen_at"].astext
SEEN = case(
    (func.pg_input_is_valid(_seen_text, "timestamptz"), cast(_seen_text, TIMESTAMP(timezone=True))),
    else_=Item.created_at,
)


def _tab_filter(tab: str):
    """The dossier tabs of the numbered line, as the web reads them (components/claims/verdict.ts)."""
    # A missing field reads as NULL in SQL: coalesce makes it a plain « no ».
    confirmed = func.coalesce(Item.data["verdict"].astext.in_(VERDICTS), False)
    suggested = func.coalesce(Item.data["verdict_suggested"].astext.in_(VERDICTS), False)
    if tab == "done":
        return confirmed
    if tab == "confirm":
        return and_(not_(confirmed), suggested)
    if tab == "todo":
        return and_(not_(confirmed), not_(suggested))
    return None


def _encode_cursor(seen: datetime, item_id: uuid.UUID) -> str:
    raw = f"{seen.isoformat()}|{item_id}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode_cursor(value: str) -> tuple[datetime, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4)).decode()
        seen, item_id = raw.split("|")
        at = datetime.fromisoformat(seen)
        if at.tzinfo is None:
            raise ValueError
        return at, uuid.UUID(item_id)
    except (ValueError, UnicodeDecodeError, binascii.Error) as e:
        raise ApiError(422, "bad_cursor", "This page cursor cannot be read") from e


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
    order: Literal["newest", "oldest"] | None = Query(
        None, description="Sort by when the rumour was first seen and page with `after`"
    ),
    after: str | None = Query(None, description="The `next` cursor of the previous page"),
    tab: Literal["all", "todo", "confirm", "done"] | None = Query(
        None, description="Dossier tab; the answer then carries every tab's count"
    ),
    assignee: str | None = Query(None, description="`me`, `none` or a member's user id"),
) -> ItemPage:
    where = [Item.workspace_id == member.workspace_id]
    if status:
        where.append(Item.status == status)
    if type:
        where.append(Item.type == type)
    else:  # alerts group dossiers and reports (app/modules/alerts.py); they are not dossiers
        where.append(Item.type != "alert")
    if tag:
        where.append(Item.tags.contains([tag]))
    if q and q.strip():
        needle = q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        like = f"%{needle}%"
        where.append(
            or_(
                Item.title.ilike(like, escape="\\"),
                Item.body.ilike(like, escape="\\"),
                Item.data["ref"].astext.ilike(like, escape="\\"),
                func.array_to_string(Item.tags, " ").ilike(like, escape="\\"),
            )
        )
    if assignee:
        owner = Item.data["assignee_id"].astext
        if assignee == "none":
            where.append(owner.is_(None))
        else:
            where.append(owner == (member.user.id if assignee == "me" else assignee))

    counts = None
    if tab:
        filters = {k: _tab_filter(k) for k in TABS}
        row = (
            await db.execute(
                select(
                    *(
                        func.count().filter(f).label(k) if f is not None else func.count().label(k)
                        for k, f in filters.items()
                    )
                ).where(*where)
            )
        ).one()
        counts = {k: int(getattr(row, k)) for k in TABS}
        tab_where = filters[tab]
        if tab_where is not None:
            where.append(tab_where)

    total = await db.scalar(select(func.count()).select_from(Item).where(*where))

    if order is None:
        rows = await db.scalars(
            select(Item).where(*where).order_by(Item.created_at.desc()).limit(limit).offset(offset)
        )
        return ItemPage(
            items=[ItemOut.model_validate(i) for i in rows], total=total or 0, counts=counts
        )

    seen = SEEN.label("seen")
    stmt = select(Item, seen).where(*where)
    if after:
        at, last_id = _decode_cursor(after)
        key = tuple_(SEEN, Item.id)
        stmt = stmt.where(
            key < tuple_(at, last_id) if order == "newest" else key > tuple_(at, last_id)
        )
    if order == "newest":
        stmt = stmt.order_by(SEEN.desc(), Item.id.desc())
    else:
        stmt = stmt.order_by(SEEN.asc(), Item.id.asc())
    rows = (await db.execute(stmt.limit(limit + 1))).all()
    more = len(rows) > limit
    rows = rows[:limit]
    nxt = _encode_cursor(rows[-1].seen, rows[-1].Item.id) if more and rows else None
    return ItemPage(
        items=[ItemOut.model_validate(r.Item) for r in rows],
        total=total or 0,
        next=nxt,
        counts=counts,
    )


@router.post("/workspaces/{ws}/items", status_code=201)
async def create_item(body: ItemIn, member: AnyMember, db: Db) -> ItemOut:
    if "ref" in body.data:
        raise ApiError(422, "protected_fields", "References are assigned by the server")
    if body.type == "claim":
        # A dossier gets the newsroom's next FAN reference, allocated atomically (app/core/refs.py).
        body = body.model_copy(
            update={"data": {**body.data, "ref": await next_ref(db, member.workspace_id)}}
        )
    return await _create_item(body, member, db)


async def _create_item(body: ItemIn, member: AnyMember, db: Db) -> ItemOut:
    """Create an item from a trusted server flow, which may have allocated its reference."""
    from app.modules.signing import SIGNATURE_FIELDS, publication_guard

    if SIGNATURE_FIELDS & body.data.keys():
        raise ApiError(422, "protected_fields", "Use the signature endpoint")
    await publication_guard(db, member, body.status, body.title, body.body, body.data)
    item = Item(workspace_id=member.workspace_id, author_id=member.user.id, **body.model_dump())
    db.add(item)
    await db.flush()
    await record(db, member.workspace_id, member.user.id, "item", item.id, "create")
    await db.commit()
    await db.refresh(item)
    await broadcast(member.workspace_id, "item.created", _out(item))
    return ItemOut.model_validate(item)


class SimilarOut(BaseModel):
    score: float
    item: ItemOut


@router.get("/workspaces/{ws}/items/similar")
async def similar_items(
    member: AnyMember, db: Db, q: str = Query(min_length=1, max_length=600)
) -> list[SimilarOut]:
    """Claims of the desk that share most of their words with `q`: a duplicate warning while
    a new claim is typed. Word overlap only, so it answers at once and without any AI."""
    asked = words(q)
    if len(asked) < 2:
        return []
    rows = await db.scalars(
        select(Item)
        .where(Item.workspace_id == member.workspace_id, Item.type == "claim")
        .order_by(Item.created_at.desc())
        .limit(500)
    )
    scored = []
    for item in rows:
        known = words(f"{item.title} {item.body}")
        shared = asked & known
        if len(shared) < 2:
            continue
        score = len(shared) / min(len(asked), len(known))
        # Same bar as the public "already checked?" match; only a warning, so a near miss is fine.
        if score >= 0.4:
            scored.append((score, item))
    scored.sort(key=lambda r: r[0], reverse=True)
    return [SimilarOut(score=round(s, 2), item=i) for s, i in scored[:3]]


@router.get("/workspaces/{ws}/items/{item_id}")
async def get_item(item_id: uuid.UUID, member: AnyMember, db: Db) -> ItemOut:
    return ItemOut.model_validate(await _get_item(db, member, item_id))


@router.patch("/workspaces/{ws}/items/{item_id}")
async def update_item(item_id: uuid.UUID, body: ItemPatch, member: AnyMember, db: Db) -> ItemOut:
    item = await _get_item(db, member, item_id)
    from app.modules.signing import SIGNATURE_FIELDS, publication_guard

    # The voice note is attached through its own route, which checks the file (never transcribed).
    if body.data is not None and (SIGNATURE_FIELDS | {"ref", "voice_note"}) & body.data.keys():
        raise ApiError(422, "protected_fields", "Signature fields and references are server-owned")
    changes = body.model_dump(exclude_unset=True)
    status = body.status or item.status
    title = body.title or item.title
    text = body.body if body.body is not None else item.body
    data = {**item.data, **(body.data or {})}
    await publication_guard(db, member, status, title, text, data)
    # A published verdict carries a signature: what the public reads cannot change under it.
    if status == "published" and item.data.get("signed_by"):
        from app.modules.signing import digest

        if digest(title, text, data) != item.data.get("signed_digest"):
            raise ApiError(409, "signature_required", "Sign the new version before publication")
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
async def delete_item(item_id: uuid.UUID, member: AnyMember, db: Db) -> None:
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
