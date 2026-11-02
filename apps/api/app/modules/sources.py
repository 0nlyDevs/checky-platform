"""Files and sources (M4).

Upload: `POST …/files/upload-url` → the browser PUTs the file to the presigned URL →
`POST …/files/{id}/complete` creates the source and queues `ingest_file`.
Link: `POST …/sources` with a `url` queues `ingest_url`; with `text` the source is ready at once.
"""

import logging
import re
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import storage
from app.core.access import AnyMember, Db, Member
from app.core.activity import broadcast, record
from app.core.errors import ApiError
from app.core.models import File, Item, Source
from app.workers import ingest
from app.workers.queue import enqueue

log = logging.getLogger("fanilo.sources")
router = APIRouter(tags=["sources"])

MAX_UPLOAD_BYTES = 25 * 1024 * 1024
# What a journalist sends: photos and screenshots, documents, voice notes and interviews.
KIND_BY_MIME = {
    "image/jpeg": "image",
    "image/png": "image",
    "image/webp": "image",
    "image/gif": "image",
    "image/heic": "image",
    "application/pdf": "pdf",
    "audio/mpeg": "audio",
    "audio/mp4": "audio",
    "audio/x-m4a": "audio",
    "audio/m4a": "audio",
    "audio/wav": "audio",
    "audio/x-wav": "audio",
    "audio/webm": "audio",
    "audio/ogg": "audio",
}


class UploadIn(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    mime: str
    size_bytes: int = Field(gt=0)


class UploadOut(BaseModel):
    file_id: uuid.UUID
    upload_url: str
    headers: dict[str, str]
    expires_in: int


class UploadCompleteIn(BaseModel):
    item_id: uuid.UUID | None = None
    title: str | None = Field(default=None, max_length=500)


class SourceIn(BaseModel):
    item_id: uuid.UUID | None = None
    url: str | None = Field(default=None, max_length=2000)
    text: str | None = Field(default=None, max_length=200_000)
    title: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def one_of(self):
        if bool(self.url) == bool(self.text):
            raise ValueError("Give either a url or a text")
        return self


class FileOut(BaseModel):
    id: uuid.UUID
    filename: str
    mime: str
    size_bytes: int
    sha256: str | None
    meta: dict[str, Any]
    download_url: str | None


class SourceOut(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    item_id: uuid.UUID | None
    kind: str
    status: str
    title: str
    url: str | None
    author: str | None
    published_at: str | None
    excerpt: str
    error: str | None
    created_by: str
    created_at: datetime
    file: FileOut | None
    # Other sources in the workspace with the same file content (same SHA-256).
    duplicates: int = 0


def _safe_name(name: str) -> str:
    name = name.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    return re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-.")[:120] or "file"


async def source_payload(db: AsyncSession, source: Source) -> dict[str, Any]:
    return (await _source_out(db, source)).model_dump(mode="json")


async def _source_out(db: AsyncSession, source: Source) -> SourceOut:
    file_out, dupes = None, 0
    if source.file_id:
        f = await db.get(File, source.file_id)
        if f is not None:
            url = (
                storage.presign_download(f.storage_key, f.filename) if f.status == "ready" else None
            )
            file_out = FileOut(
                id=f.id,
                filename=f.filename,
                mime=f.mime,
                size_bytes=f.size_bytes,
                sha256=f.sha256,
                meta=f.meta,
                download_url=url,
            )
            if f.sha256:
                dupes = (
                    await db.scalar(
                        select(func.count())
                        .select_from(File)
                        .where(
                            File.workspace_id == f.workspace_id,
                            File.sha256 == f.sha256,
                            File.id != f.id,
                        )
                    )
                    or 0
                )
    return SourceOut(
        id=source.id,
        workspace_id=source.workspace_id,
        item_id=source.item_id,
        kind=source.kind,
        status=source.status,
        title=source.title,
        url=source.url,
        author=source.author,
        published_at=source.published_at,
        excerpt=source.text[:400],
        error=source.error,
        created_by=source.created_by,
        created_at=source.created_at,
        file=file_out,
        duplicates=dupes,
    )


async def _check_item(db: AsyncSession, member: Member, item_id: uuid.UUID | None) -> None:
    if item_id is None:
        return
    item = await db.get(Item, item_id)
    if item is None or item.workspace_id != member.workspace_id:
        raise ApiError(404, "not_found", "Item not found")


async def _sync_source_count(db: AsyncSession, ws: uuid.UUID, item_id: uuid.UUID | None) -> None:
    """Keep the claim's `data.source_count` (shown on cards) equal to its attached sources."""
    if item_id is None:
        return
    item = await db.get(Item, item_id)
    if item is None:
        return
    n = await db.scalar(select(func.count()).select_from(Source).where(Source.item_id == item_id))
    if item.data.get("source_count") != n:
        item.data = {**item.data, "source_count": n}
        await db.commit()
        await db.refresh(item)
        from app.modules.items import ItemOut

        await broadcast(ws, "item.updated", ItemOut.model_validate(item).model_dump(mode="json"))


async def _created(db: AsyncSession, member: Member, source: Source) -> SourceOut:
    await record(db, member.workspace_id, member.user.id, "source", source.id, "create")
    if source.item_id:
        await record(
            db,
            member.workspace_id,
            member.user.id,
            "item",
            source.item_id,
            "source",
            {"source_id": str(source.id), "kind": source.kind},
        )
    await db.commit()
    await db.refresh(source)
    out = await _source_out(db, source)
    await broadcast(member.workspace_id, "source.created", out.model_dump(mode="json"))
    await _sync_source_count(db, member.workspace_id, source.item_id)
    return out


@router.post("/workspaces/{ws}/files/upload-url", status_code=201)
async def upload_url(body: UploadIn, member: AnyMember, db: Db) -> UploadOut:
    if not storage.configured():
        raise ApiError(503, "storage_unavailable", "File storage is not configured")
    mime = body.mime.split(";")[0].strip().lower()
    if mime not in KIND_BY_MIME:
        raise ApiError(415, "unsupported_type", f"Files of type {mime} are not accepted")
    if body.size_bytes > MAX_UPLOAD_BYTES:
        raise ApiError(413, "too_large", "Files are limited to 25 MB")
    file_id = uuid.uuid4()
    key = f"ws/{member.workspace_id}/{file_id}/{_safe_name(body.filename)}"
    db.add(
        File(
            id=file_id,
            workspace_id=member.workspace_id,
            uploaded_by=member.user.id,
            storage_key=key,
            filename=body.filename,
            mime=mime,
            size_bytes=body.size_bytes,
        )
    )
    await db.commit()
    return UploadOut(
        file_id=file_id,
        upload_url=storage.presign_upload(key, mime),
        headers={"Content-Type": mime},
        expires_in=storage.UPLOAD_SECONDS,
    )


@router.post("/workspaces/{ws}/files/{file_id}/complete", status_code=201)
async def complete_upload(
    file_id: uuid.UUID, body: UploadCompleteIn, member: AnyMember, db: Db
) -> SourceOut:
    f = await db.get(File, file_id)
    if f is None or f.workspace_id != member.workspace_id:
        raise ApiError(404, "not_found", "File not found")
    if f.status != "pending":
        raise ApiError(409, "already_completed", "This upload was already completed")
    await _check_item(db, member, body.item_id)
    obj = await storage.head(f.storage_key)
    if obj is None:
        raise ApiError(409, "not_uploaded", "The file has not reached storage yet")
    if obj["size"] > MAX_UPLOAD_BYTES:
        await storage.delete(f.storage_key)
        raise ApiError(413, "too_large", "Files are limited to 25 MB")
    f.status, f.size_bytes = "ready", obj["size"]
    source = Source(
        workspace_id=member.workspace_id,
        item_id=body.item_id,
        file_id=f.id,
        created_by=member.user.id,
        kind=KIND_BY_MIME[f.mime],
        title=body.title or f.filename,
    )
    db.add(source)
    await db.flush()
    out = await _created(db, member, source)
    await enqueue(
        db, member.workspace_id, member.user.id, "ingest_file", {"source_id": str(source.id)}
    )
    return out


@router.post("/workspaces/{ws}/sources", status_code=201)
async def add_source(body: SourceIn, member: AnyMember, db: Db) -> SourceOut:
    await _check_item(db, member, body.item_id)
    if body.url:
        url = body.url.strip()
        try:
            await ingest.check_public_url(url)
        except ValueError as e:
            raise ApiError(422, "bad_url", str(e)) from e
        source = Source(
            workspace_id=member.workspace_id,
            item_id=body.item_id,
            created_by=member.user.id,
            kind="url",
            url=url,
            title=body.title or url,
        )
    else:
        source = Source(
            workspace_id=member.workspace_id,
            item_id=body.item_id,
            created_by=member.user.id,
            kind="text",
            status="ready",
            title=body.title or body.text.strip().splitlines()[0][:120],
            text=body.text,
        )
    db.add(source)
    await db.flush()
    out = await _created(db, member, source)
    if source.kind == "url":
        await enqueue(
            db, member.workspace_id, member.user.id, "ingest_url", {"source_id": str(source.id)}
        )
    return out


@router.get("/workspaces/{ws}/sources")
async def list_sources(
    member: AnyMember, db: Db, item_id: uuid.UUID | None = None, kind: str | None = None
) -> list[SourceOut]:
    where = [Source.workspace_id == member.workspace_id]
    if item_id:
        where.append(Source.item_id == item_id)
    if kind:
        where.append(Source.kind == kind)
    rows = await db.scalars(
        select(Source).where(*where).order_by(Source.created_at.desc()).limit(200)
    )
    return [await _source_out(db, s) for s in rows]


async def _get_source(db: AsyncSession, member: Member, source_id: uuid.UUID) -> Source:
    s = await db.get(Source, source_id)
    if s is None or s.workspace_id != member.workspace_id:
        raise ApiError(404, "not_found", "Source not found")
    return s


@router.get("/workspaces/{ws}/sources/{source_id}")
async def get_source(source_id: uuid.UUID, member: AnyMember, db: Db) -> SourceOut:
    return await _source_out(db, await _get_source(db, member, source_id))


@router.get("/workspaces/{ws}/sources/{source_id}/text")
async def get_source_text(source_id: uuid.UUID, member: AnyMember, db: Db) -> dict:
    s = await _get_source(db, member, source_id)
    return {"id": str(s.id), "text": s.text}


@router.delete("/workspaces/{ws}/sources/{source_id}", status_code=204)
async def delete_source(source_id: uuid.UUID, member: AnyMember, db: Db) -> None:
    s = await _get_source(db, member, source_id)
    if s.created_by != member.user.id and not member.at_least("editor"):
        raise ApiError(403, "forbidden", "Only who added it or an editor can remove this source")
    item_id, file_id = s.item_id, s.file_id
    await db.delete(s)
    await record(db, member.workspace_id, member.user.id, "source", source_id, "delete")
    if file_id:
        f = await db.get(File, file_id)
        if f is not None:
            try:
                await storage.delete(f.storage_key)
            except Exception:  # noqa: BLE001 - an orphan object must not block the delete
                log.warning("could not delete %s from storage", f.storage_key)
            await db.delete(f)
    await db.commit()
    await broadcast(
        member.workspace_id,
        "source.deleted",
        {"id": str(source_id), "item_id": str(item_id) if item_id else None},
    )
    await _sync_source_count(db, member.workspace_id, item_id)
