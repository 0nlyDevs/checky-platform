"""« Un démenti malgache en 30 secondes avec sa propre voix »: the journalist's voice note.

The journalist records the démenti in their own voice (Malagasy first, for groups that listen more
than they read), uploads it straight to storage through `files/upload-url`, then attaches it here.
It is never a source and never transcribed: spoken Malagasy stays with people (brief, section 9).
The public verdict page plays it (`voice_note` on `/public/verdicts/{id}`) only while the newsroom
publishes, and « Diffuser » sends it to WhatsApp as the `voice_note` format.

    PUT    /workspaces/{ws}/items/{id}/voice-note  {file_id, seconds?, language?}
    GET    /workspaces/{ws}/items/{id}/voice-note
    DELETE /workspaces/{ws}/items/{id}/voice-note
"""

import logging
import uuid
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import storage
from app.core.access import AnyMember, Db
from app.core.activity import broadcast, record
from app.core.errors import ApiError
from app.core.models import File, Item
from app.modules.items import _get_item, _out

log = logging.getLogger("checky.voicenote")
router = APIRouter(tags=["voice-note"])

# 30 seconds of Opus or AAC weigh a few hundred kB; the cap leaves room for an uncompressed phone.
MAX_SECONDS = 30.0
MAX_BYTES = 6 * 1024 * 1024
AUDIO = {
    "audio/webm",
    "audio/ogg",
    "audio/mp4",
    "audio/m4a",
    "audio/x-m4a",
    "audio/mpeg",
    "audio/wav",
    "audio/x-wav",
    "audio/aac",
}


class VoiceNoteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    file_id: uuid.UUID
    # Measured by the recorder; shown next to the player.
    seconds: float | None = Field(default=None, gt=0, le=MAX_SECONDS)
    language: Literal["mg", "fr"] = "mg"


class VoiceNoteOut(BaseModel):
    file_id: uuid.UUID
    url: str
    mime: str
    size_bytes: int
    seconds: float | None
    language: str
    by: str
    at: datetime


def voice_note(item: Item) -> dict | None:
    note = (item.data or {}).get("voice_note")
    return note if isinstance(note, dict) and note.get("file_id") else None


async def voice_file(db: AsyncSession, item: Item) -> File | None:
    """The voice note's file, only when it belongs to the dossier's newsroom and is ready."""
    note = voice_note(item)
    if not note:
        return None
    try:
        f = await db.get(File, uuid.UUID(str(note["file_id"])))
    except ValueError:
        return None
    if f is None or f.workspace_id != item.workspace_id or f.status != "ready":
        return None
    return f


def _out_note(note: dict, f: File) -> VoiceNoteOut:
    return VoiceNoteOut(
        file_id=f.id,
        url=storage.presign_download(f.storage_key, f.filename),
        mime=f.mime,
        size_bytes=f.size_bytes,
        seconds=note.get("seconds"),
        language=note.get("language") or "mg",
        by=note.get("by") or "",
        at=note.get("at") or f.created_at,
    )


async def _drop(db: AsyncSession, f: File | None) -> None:
    if f is None:
        return
    try:
        await storage.delete(f.storage_key)
    except Exception as exc:  # noqa: BLE001 - a stray object costs storage, never the request
        log.warning("voice note object not deleted: %s", type(exc).__name__)
    await db.delete(f)


async def _changed(db: AsyncSession, member, item: Item, line: str) -> None:
    await record(
        db, member.workspace_id, member.user.id, "item", item.id, "voice_note", {"carnet": line}
    )
    await db.commit()
    await db.refresh(item)
    await broadcast(member.workspace_id, "item.updated", _out(item))


@router.put("/workspaces/{ws}/items/{item_id}/voice-note")
async def attach_voice_note(
    item_id: uuid.UUID, body: VoiceNoteIn, member: AnyMember, db: Db
) -> VoiceNoteOut:
    """Attach the recorded démenti to a signed dossier (replacing an earlier one). The file was
    uploaded through `files/upload-url` and is NOT completed as a source: nothing transcribes it."""
    item = await _get_item(db, member, item_id)
    data = item.data or {}
    if not data.get("signed_by") or not data.get("verdict"):
        raise ApiError(409, "not_signed", "Sign the verdict before recording its démenti")
    f = await db.get(File, body.file_id)
    if f is None or f.workspace_id != member.workspace_id:
        raise ApiError(404, "not_found", "File not found")
    if f.mime not in AUDIO:
        raise ApiError(415, "unsupported_type", "A voice note is an audio recording")
    old = await voice_file(db, item)
    if f.status != "pending" and (old is None or old.id != f.id):
        # A file already completed is a source (and may be transcribed): never a voice note.
        raise ApiError(409, "already_completed", "This file is already used elsewhere")
    obj = await storage.head(f.storage_key)
    if obj is None:
        raise ApiError(409, "not_uploaded", "The file has not reached storage yet")
    if obj["size"] > MAX_BYTES:
        await storage.delete(f.storage_key)
        raise ApiError(413, "too_large", "A voice note is 30 seconds, a few hundred kB")
    f.status, f.size_bytes = "ready", obj["size"]
    f.meta = {**(f.meta or {}), "voice_note": True, "item_id": str(item.id)}
    if old is not None and old.id != f.id:
        await _drop(db, old)
    note = {
        "file_id": str(f.id),
        "seconds": body.seconds,
        "language": body.language,
        "by": member.user.id,
        "at": datetime.now(UTC).isoformat(),
    }
    item.data = {**data, "voice_note": note}
    secs = f" ({round(body.seconds)} s)" if body.seconds else ""
    lang = "en malgache" if body.language == "mg" else "en français"
    await _changed(db, member, item, f"Note vocale {lang} enregistrée{secs}")
    return _out_note(note, f)


@router.get("/workspaces/{ws}/items/{item_id}/voice-note")
async def read_voice_note(item_id: uuid.UUID, member: AnyMember, db: Db) -> VoiceNoteOut:
    item = await _get_item(db, member, item_id)
    f = await voice_file(db, item)
    if f is None:
        raise ApiError(404, "not_found", "No voice note on this dossier")
    return _out_note(voice_note(item) or {}, f)


@router.delete("/workspaces/{ws}/items/{item_id}/voice-note", status_code=204)
async def remove_voice_note(item_id: uuid.UUID, member: AnyMember, db: Db) -> None:
    item = await _get_item(db, member, item_id)
    if not voice_note(item):
        raise ApiError(404, "not_found", "No voice note on this dossier")
    await _drop(db, await voice_file(db, item))
    item.data = {k: v for k, v in (item.data or {}).items() if k != "voice_note"}
    await _changed(db, member, item, "Note vocale retirée")


class PublicVoiceNote(BaseModel):
    url: str
    mime: str
    seconds: float | None
    language: str


async def public_voice_note(db: AsyncSession, item: Item) -> PublicVoiceNote | None:
    """For the public verdict page only (the caller already checked the newsroom publishes)."""
    f = await voice_file(db, item)
    if f is None:
        return None
    note = voice_note(item) or {}
    return PublicVoiceNote(
        url=storage.presign_download(f.storage_key, f.filename),
        mime=f.mime,
        seconds=note.get("seconds"),
        language=note.get("language") or "mg",
    )
