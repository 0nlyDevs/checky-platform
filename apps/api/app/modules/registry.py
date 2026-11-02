"""Curated originals and literal comparisons. A match proves correspondence, not authenticity."""

import difflib
import hashlib
import re
import uuid

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, Field, HttpUrl
from sqlalchemy import or_, select

from app.core.access import Anyone, Db, Issuer
from app.core.activity import record
from app.core.db import SessionLocal
from app.core.models import Communique
from app.core.words import words

router = APIRouter(tags=["registry"])


class OriginalIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    issuer: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=500)
    number: str | None = Field(default=None, max_length=60)
    text: str = Field(min_length=20, max_length=30000)
    url: HttpUrl
    is_demo: bool = False


class OriginalOut(OriginalIn):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    fingerprint: str | None


@router.get("/workspaces/{ws}/registry")
async def originals(
    member: Anyone, db: Db, q: str = Query(default="", max_length=200)
) -> list[OriginalOut]:
    stmt = select(Communique).where(Communique.workspace_id == member.workspace_id)
    if member.role == "veilleur":
        from app.core.errors import ApiError

        raise ApiError(403, "forbidden", "Registry access requires a desk or issuer role")
    if member.role == "issuer":
        stmt = stmt.where(Communique.added_by == member.user.id)
    if q:
        stmt = stmt.where(or_(Communique.title.ilike(f"%{q}%"), Communique.issuer.ilike(f"%{q}%")))
    return [
        OriginalOut.model_validate(row)
        for row in await db.scalars(stmt.order_by(Communique.created_at.desc()).limit(100))
    ]


@router.post("/workspaces/{ws}/registry", status_code=201)
async def register(body: OriginalIn, member: Issuer, db: Db) -> OriginalOut:
    original = Communique(
        workspace_id=member.workspace_id,
        added_by=member.user.id,
        fingerprint=hashlib.sha256(body.text.encode()).hexdigest(),
        **body.model_dump(mode="json"),
    )
    db.add(original)
    await db.flush()
    await record(db, member.workspace_id, member.user.id, "communique", original.id, "register")
    await db.commit()
    return OriginalOut.model_validate(original)


def normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def compare(original: Communique, submitted: str) -> dict:
    left, right = normalise(original.text), normalise(submitted)
    a, b = left.split(), right.split()
    changes = [
        {"operation": tag, "original": " ".join(a[i:j]), "submitted": " ".join(b[k:l])}
        for tag, i, j, k, l in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes()
    ]
    return {
        "status": "text_match" if left == right else "differences",
        "original_id": str(original.id),
        "title": original.title,
        "issuer": original.issuer,
        "url": original.url,
        "is_demo": original.is_demo,
        "changes": changes[:100],
        "authenticity": "not_established",
        "match_method": "candidate_text_similarity",
    }


async def compare_text(ws: uuid.UUID, text: str) -> dict:
    async with SessionLocal() as db:
        rows = (
            await db.scalars(
                select(Communique)
                .where(Communique.workspace_id == ws)
                .order_by(Communique.created_at.desc())
                .limit(200)
            )
        ).all()
    asked = words(text)
    ranked = sorted(
        (
            (len(asked & words(row.text)) / max(1, len(asked | words(row.text))), row)
            for row in rows
        ),
        key=lambda pair: pair[0],
        reverse=True,
    )
    if not ranked or ranked[0][0] < 0.35:
        return {"status": "not_found", "authenticity": "not_established"}
    return compare(ranked[0][1], text)
