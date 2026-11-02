"""Human radio observations, linked to original clips already uploaded as sources."""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.core.access import Db, Veilleur
from app.core.errors import ApiError
from app.core.models import RadioClip, Source

router = APIRouter(tags=["veille"])


class ClipIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    station: str = Field(min_length=1, max_length=120)
    heard_text: str = Field(min_length=10, max_length=4000)
    language: str = Field(default="mg", min_length=2, max_length=10)
    recorded_at: datetime
    source_id: uuid.UUID | None = None


class ClipOut(ClipIn):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    status: str


@router.get("/workspaces/{ws}/radio-clips")
async def clips(member: Veilleur, db: Db) -> list[ClipOut]:
    stmt = select(RadioClip).where(RadioClip.workspace_id == member.workspace_id)
    if member.role == "veilleur":
        stmt = stmt.where(RadioClip.created_by == member.user.id)
    return [
        ClipOut.model_validate(row)
        for row in await db.scalars(stmt.order_by(RadioClip.recorded_at.desc()).limit(100))
    ]


@router.post("/workspaces/{ws}/radio-clips", status_code=201)
async def create_clip(body: ClipIn, member: Veilleur, db: Db) -> ClipOut:
    if body.recorded_at.tzinfo is None or body.recorded_at > datetime.now(UTC):
        raise ApiError(422, "invalid_time", "Use a past recording time with timezone")
    if body.source_id:
        source = await db.get(Source, body.source_id)
        if source is None or source.workspace_id != member.workspace_id:
            raise ApiError(404, "not_found", "Source not found")
        if source.kind not in ("audio", "video"):
            raise ApiError(422, "invalid_source", "Attach an audio or video source")
    clip = RadioClip(
        workspace_id=member.workspace_id, created_by=member.user.id, **body.model_dump()
    )
    db.add(clip)
    await db.commit()
    return ClipOut.model_validate(clip)
