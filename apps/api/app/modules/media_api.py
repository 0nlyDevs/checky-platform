"""Pictures in the desk: the image memory of a source, and revealing a face that was blurred.

`GET  /workspaces/{ws}/sources/{id}/memory`  older pictures that look the same (`media.memory_matches`)
`POST /workspaces/{ws}/sources/{id}/reveal {frame?}`  the original picture (faces not blurred), for a
      journalist who asks for it; the reveal is logged (`face_revealed`) on the dossier's carnet.
"""

import uuid
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core import media, storage
from app.core.access import AnyMember, Db
from app.core.activity import record
from app.core.errors import ApiError
from app.core.models import File, Source

router = APIRouter(tags=["media"])


class MemoryMatch(BaseModel):
    source_id: uuid.UUID
    title: str
    kind: str
    item_id: uuid.UUID | None
    ref: str | None
    verdict_id: uuid.UUID | None
    newsroom: str | None
    own: bool
    date: str | None
    date_basis: str
    days_before: int | None
    distance: int
    at_s: float | None
    their_at_s: float | None
    line: str


class RevealIn(BaseModel):
    frame: int | None = Field(default=None, ge=0, le=20)


class RevealOut(BaseModel):
    url: str
    faces: int | None


async def _source(db, member, source_id: uuid.UUID) -> tuple[Source, File]:
    source = await db.get(Source, source_id)
    if source is None or source.workspace_id != member.workspace_id or not source.file_id:
        raise ApiError(404, "not_found", "Source not found")
    file = await db.get(File, source.file_id)
    if file is None or file.status != "ready":
        raise ApiError(404, "not_found", "Source not found")
    return source, file


@router.get("/workspaces/{ws}/sources/{source_id}/memory")
async def memory(source_id: uuid.UUID, member: AnyMember, db: Db) -> list[MemoryMatch]:
    """Fact, no model: the same picture seen before, with the date it carried then."""
    source, _ = await _source(db, member, source_id)
    found = await media.memory_matches(db, member.workspace_id, source.id)
    return [MemoryMatch(**m) for m in found]


@router.post("/workspaces/{ws}/sources/{source_id}/reveal")
async def reveal(source_id: uuid.UUID, body: RevealIn, member: AnyMember, db: Db) -> RevealOut:
    """The picture as it was received. Logged, since a face may be someone who never agreed to be
    shown: the carnet keeps who looked and when."""
    source, file = await _source(db, member, source_id)
    meta: dict[str, Any] = file.meta or {}
    if body.frame is None:
        if not file.mime.startswith("image/"):
            raise ApiError(422, "not_an_image", "Give the frame of a video")
        key, faces = file.storage_key, meta.get("faces")
    else:
        frames = meta.get("keyframes") or []
        if body.frame >= len(frames):
            raise ApiError(404, "not_found", "Frame not found")
        frame = frames[body.frame]
        key = frame.get("key") or f"{file.storage_key}/frames/{body.frame}.jpg"
        faces = frame.get("faces")
    diff = {"source_id": str(source.id), "frame": body.frame, "faces": faces}
    await record(
        db, member.workspace_id, member.user.id, "source", source.id, "face_revealed", diff
    )
    if source.item_id:
        await record(
            db, member.workspace_id, member.user.id, "item", source.item_id, "face_revealed", diff
        )
    await db.commit()
    return RevealOut(url=storage.presign_download(key), faces=faces)
