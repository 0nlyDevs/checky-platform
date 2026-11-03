"""Veille: what circulates before it reaches the desk.

Four roads bring a rumour in before anyone pastes it into Vérifier: a citizen's tip, a question by
SMS, a radio bulletin a partner heard (« À l'antenne ») and the national press. This module merges
them into one feed and one map (counts per region, last 24 hours and 7 days), groups radio clips by
the claim they carry, watches the words a desk cares about (« Mots surveillés ») and says which
rumours the season brings back (« Météo des rumeurs », see app/core/seasons.py).

Radio clips are what a veilleur (a partner-radio journalist or correspondent) heard: a French clip
with a recording gets its transcript once ready; a Malagasy clip keeps the sentence the veilleur
typed, never a machine transcript. Nothing here makes a verdict: « Déjà vérifié » only relays a
verdict a journalist signed (this newsroom's, or `public.find_published`).

Clips carry no column for extra facts, so the demo flag lives in `location.demo`.
"""

import logging
import re
import time
import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import dates, seasons, storage
from app.core.access import AnyMember, Db, Member
from app.core.activity import broadcast, record
from app.core.config import get_settings
from app.core.errors import ApiError
from app.core.models import (
    File,
    Item,
    Job,
    PublicQuestion,
    RadioClip,
    Route,
    Signal,
    Source,
    Workspace,
)
from app.core.places import MG_REGIONS, fold, gazetteer
from app.core.words import words
from app.workers import radio_capture, veille_poll  # registers the press and capture jobs
from app.workers.queue import enqueue

log = logging.getLogger("checky.veille")
router = APIRouter(tags=["veille"])

VERDICTS = ("true", "misleading", "false", "unverifiable")
# Two clips (or a clip and a claim) carry the same rumour when they share this much of their words.
SAME_RUMOUR = 0.34
ANTENNE_DAYS = 7
FEED_LIMIT = 120
_REGIONS = {fold(r): r for r in MG_REGIONS}


# --------------------------------------------------------------------------------------- places
def canonical_region(name: str | None) -> str | None:
    """A region name as the gazetteer spells it (« analamanga » → « Analamanga »), or as given."""
    if not name or not name.strip():
        return None
    if found := _REGIONS.get(fold(name)):
        return found
    hit = gazetteer(name)
    return (hit or {}).get("region") or name.strip()


def region_of_text(*texts: str | None) -> dict[str, Any] | None:
    """The Malagasy place a text names, if any (offline gazetteer, no network). Punctuation is
    blanked first: the gazetteer reads whole words between spaces (« à Toamasina. »)."""
    text = " ".join(t for t in texts if t)
    return gazetteer(re.sub(r"[^\w'’\- ]+", " ", text)) if text.strip() else None


def item_location(item: Item) -> dict[str, Any] | None:
    loc = (item.data or {}).get("location")
    if isinstance(loc, dict) and (loc.get("region") or loc.get("name")):
        return loc
    return region_of_text(item.title, (item.body or "")[:600])


def clip_location(clip: RadioClip) -> dict[str, Any] | None:
    loc = clip.location or {}
    if loc.get("region") or loc.get("name"):
        return loc
    return region_of_text(clip.station, (clip.heard_text or "")[:600])


def _place_out(loc: dict[str, Any] | None) -> dict[str, Any] | None:
    if not loc:
        return None
    return {
        "name": loc.get("name") or loc.get("region"),
        "region": canonical_region(loc.get("region")),
        "country": loc.get("country"),
        "lat": loc.get("lat"),
        "lng": loc.get("lng"),
    }


def _is_demo(clip: RadioClip) -> bool:
    return bool((clip.location or {}).get("demo"))


# ------------------------------------------------------------------------------ Mots surveillés
class SignalIn(BaseModel):
    word: str = Field(min_length=2, max_length=120)


class SignalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    word: str
    active: bool
    hits: int
    created_at: datetime


def _word_pattern(word: str) -> re.Pattern[str]:
    # Whole words, accents and case ignored, a plural s/x allowed (« délestages »).
    return re.compile(rf"(?<![a-z0-9]){re.escape(fold(word))}(?:s|x)?(?![a-z0-9])")


def mentions(word: str, text: str) -> bool:
    return bool(word.strip()) and bool(_word_pattern(word).search(fold(text)))


async def match_signals(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    text: str,
    where: str,
    item_id: uuid.UUID | None = None,
) -> list[str]:
    """The watched words `text` mentions. Each match adds a hit and is broadcast as
    `signal.matched {word, where, item_id, excerpt}`. Commits its own update, so call it once
    your own rows are committed. Other modules (tips, SMS) call it lazily."""
    if not text or not text.strip():
        return []
    rows = (
        await db.scalars(
            select(Signal).where(Signal.workspace_id == workspace_id, Signal.active.is_(True))
        )
    ).all()
    hit = [s for s in rows if mentions(s.word, text)]
    if not hit:
        return []
    for s in hit:
        s.hits = (s.hits or 0) + 1
    await db.commit()
    excerpt = re.sub(r"\s+", " ", text).strip()[:200]
    for s in hit:
        await broadcast(
            workspace_id,
            "signal.matched",
            {
                "word": s.word,
                "where": where,
                "item_id": str(item_id) if item_id else None,
                "excerpt": excerpt,
            },
        )
    return [s.word for s in hit]


@router.get("/workspaces/{ws}/signals")
async def list_signals(member: AnyMember, db: Db) -> list[SignalOut]:
    rows = await db.scalars(
        select(Signal)
        .where(Signal.workspace_id == member.workspace_id)
        .order_by(Signal.created_at.desc())
    )
    return [SignalOut.model_validate(s) for s in rows]


@router.post("/workspaces/{ws}/signals", status_code=201)
async def add_signal(body: SignalIn, member: AnyMember, db: Db) -> SignalOut:
    word = re.sub(r"\s+", " ", body.word).strip()
    if len(fold(word)) < 2:
        raise ApiError(422, "invalid_word", "Watch a word of two letters or more")
    existing = (
        await db.scalars(select(Signal).where(Signal.workspace_id == member.workspace_id))
    ).all()
    if any(fold(s.word) == fold(word) for s in existing):
        raise ApiError(409, "already_watched", "This word is already watched")
    signal = Signal(workspace_id=member.workspace_id, created_by=member.user.id, word=word)
    db.add(signal)
    await db.flush()
    await record(db, member.workspace_id, member.user.id, "signal", signal.id, "create")
    await db.commit()
    await db.refresh(signal)
    return SignalOut.model_validate(signal)


@router.delete("/workspaces/{ws}/signals/{signal_id}", status_code=204)
async def delete_signal(signal_id: uuid.UUID, member: AnyMember, db: Db) -> None:
    signal = await db.get(Signal, signal_id)
    if signal is None or signal.workspace_id != member.workspace_id:
        raise ApiError(404, "not_found", "Signal not found")
    await db.delete(signal)
    await record(db, member.workspace_id, member.user.id, "signal", signal_id, "delete")
    await db.commit()


# ------------------------------------------------------------------------------- À l'antenne
class ClipIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    station: str = Field(min_length=1, max_length=120)
    # What the veilleur heard, in their words. Optional for a French clip with a recording: its
    # transcript fills it once ready. Required in Malagasy: the text stays human.
    heard_text: str = Field(default="", max_length=4000)
    language: str = Field(default="mg", min_length=2, max_length=10)
    recorded_at: datetime
    source_id: uuid.UUID | None = None
    # A recording just uploaded through `radio-clips/upload-url` (the clip completes it).
    file_id: uuid.UUID | None = None
    location: dict[str, Any] | None = None
    clip_at_s: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _text_or_recording(self) -> "ClipIn":
        self.heard_text = self.heard_text.strip()
        self.language = self.language.strip().lower()
        if self.source_id and self.file_id:
            raise ValueError("Send source_id or file_id, not both")
        recording = self.source_id or self.file_id
        if len(self.heard_text) < 10 and not (recording and self.language == "fr"):
            raise ValueError("Say in one sentence what was heard (10 characters or more)")
        return self


class ServedOut(BaseModel):
    """« Votre signalement a servi »: the dossier the clip fed, its signed verdict, the routes the
    correction took."""

    item_id: uuid.UUID
    ref: str | None
    title: str
    status: str
    verdict: str | None
    signed_at: str | None
    truth_routes: int


class ClipOut(BaseModel):
    id: uuid.UUID
    station: str
    heard_text: str
    # veilleur: typed by the veilleur; transcript: the recording's transcript; pending: waiting
    text_from: Literal["veilleur", "transcript", "pending"]
    language: str | None
    recorded_at: datetime
    source_id: uuid.UUID | None
    item_id: uuid.UUID | None
    location: dict[str, Any] | None
    origin: str
    status: str
    clip_at_s: float | None
    created_by: str
    created_at: datetime
    demo: bool
    served: ServedOut | None = None


class ClipUploadIn(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    mime: str
    size_bytes: int = Field(gt=0)


class ClipUploadOut(BaseModel):
    file_id: uuid.UUID
    upload_url: str
    headers: dict[str, str]
    expires_in: int


def _clip_out(
    clip: RadioClip, source: Source | None = None, served: ServedOut | None = None
) -> ClipOut:
    text = clip.heard_text or ""
    if not text.strip():
        text_from = "pending"
    elif source is not None and source.text and text == source.text.strip()[:4000]:
        text_from = "transcript"
    else:
        text_from = "veilleur"
    return ClipOut(
        id=clip.id,
        station=clip.station,
        heard_text=text,
        text_from=text_from,
        language=clip.language,
        recorded_at=clip.recorded_at,
        source_id=clip.source_id,
        item_id=clip.item_id,
        location=_place_out(clip_location(clip)),
        origin=clip.origin,
        status=clip.status,
        clip_at_s=clip.clip_at_s,
        created_by=clip.created_by,
        created_at=clip.created_at,
        demo=_is_demo(clip),
        served=served,
    )


async def _sources(db: AsyncSession, clips: list[RadioClip]) -> dict[uuid.UUID, Source]:
    ids = {c.source_id for c in clips if c.source_id}
    if not ids:
        return {}
    return {s.id: s for s in await db.scalars(select(Source).where(Source.id.in_(ids)))}


async def fill_from_transcripts(
    db: AsyncSession, clips: list[RadioClip]
) -> dict[uuid.UUID, Source]:
    """A French clip recorded without a sentence takes its recording's transcript once the source
    is ready (the ingest job runs after the clip is saved). Malagasy clips are never filled."""
    sources = await _sources(db, clips)
    filled = []
    for clip in clips:
        source = sources.get(clip.source_id) if clip.source_id else None
        if (
            source is not None
            and (clip.language or "").startswith("fr")
            and not (clip.heard_text or "").strip()
            and source.status == "ready"
            and source.text.strip()
        ):
            clip.heard_text = source.text.strip()[:4000]
            filled.append(clip)
    if filled:
        await db.commit()
        for clip in filled:
            await match_signals(db, clip.workspace_id, clip.heard_text, "clip")
    return sources


async def _served(db: AsyncSession, clips: list[RadioClip]) -> dict[uuid.UUID, ServedOut]:
    ids = {c.item_id for c in clips if c.item_id}
    if not ids:
        return {}
    items = {i.id: i for i in await db.scalars(select(Item).where(Item.id.in_(ids)))}
    counts = dict(
        (
            await db.execute(
                select(Route.item_id, func.count())
                .where(Route.item_id.in_(ids), Route.side == "truth")
                .group_by(Route.item_id)
            )
        ).all()
    )
    out = {}
    for item_id, item in items.items():
        d = item.data or {}
        signed = d.get("verdict") in VERDICTS and item.status in ("verified", "published")
        out[item_id] = ServedOut(
            item_id=item.id,
            ref=d.get("ref"),
            title=item.title,
            status=item.status,
            verdict=d["verdict"] if signed else None,
            signed_at=(d.get("signed_at") or item.updated_at.isoformat()) if signed else None,
            truth_routes=counts.get(item_id, 0),
        )
    return out


async def _clips_out(db: AsyncSession, clips: list[RadioClip]) -> list[ClipOut]:
    sources = await fill_from_transcripts(db, clips)
    served = await _served(db, clips)
    return [
        _clip_out(
            c,
            sources.get(c.source_id) if c.source_id else None,
            served.get(c.item_id) if c.item_id else None,
        )
        for c in clips
    ]


@router.get("/workspaces/{ws}/radio-clips")
async def clips(member: AnyMember, db: Db) -> list[ClipOut]:
    stmt = select(RadioClip).where(RadioClip.workspace_id == member.workspace_id)
    rows = list(await db.scalars(stmt.order_by(RadioClip.recorded_at.desc()).limit(100)))
    return await _clips_out(db, rows)


async def _get_clip(db: AsyncSession, member: Member, clip_id: uuid.UUID) -> RadioClip:
    clip = await db.get(RadioClip, clip_id)
    if clip is None or clip.workspace_id != member.workspace_id:
        raise ApiError(404, "not_found", "Clip not found")
    return clip


@router.post("/workspaces/{ws}/radio-clips/upload-url", status_code=201)
async def clip_upload_url(body: ClipUploadIn, member: AnyMember, db: Db) -> ClipUploadOut:
    """The veilleur's recording goes straight to storage, as every upload does; the clip then
    completes it. A door of its own: `files/upload-url` belongs to the desk."""
    from app.modules.sources import KIND_BY_MIME, MAX_UPLOAD_BYTES, _safe_name

    if not storage.configured():
        raise ApiError(503, "storage_unavailable", "File storage is not configured")
    mime = body.mime.split(";")[0].strip().lower()
    if KIND_BY_MIME.get(mime) not in ("audio", "video"):
        raise ApiError(415, "unsupported_type", "Send an audio or video recording")
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
    return ClipUploadOut(
        file_id=file_id,
        upload_url=storage.presign_upload(key, mime),
        headers={"Content-Type": mime},
        expires_in=storage.UPLOAD_SECONDS,
    )


@router.get("/workspaces/{ws}/radio-clips/{clip_id}")
async def get_clip(clip_id: uuid.UUID, member: AnyMember, db: Db) -> ClipOut:
    clip = await _get_clip(db, member, clip_id)
    return (await _clips_out(db, [clip]))[0]


async def _recording_source(
    db: AsyncSession, member: Member, body: ClipIn
) -> tuple[Source | None, bool]:
    """(the clip's source, whether it was just created and must be ingested)."""
    from app.modules.sources import KIND_BY_MIME, MAX_UPLOAD_BYTES

    if body.source_id:
        source = await db.get(Source, body.source_id)
        if source is None or source.workspace_id != member.workspace_id:
            raise ApiError(404, "not_found", "Source not found")
        if source.kind not in ("audio", "video"):
            raise ApiError(422, "invalid_source", "Attach an audio or video source")
        return source, False
    if not body.file_id:
        return None, False
    f = await db.get(File, body.file_id)
    if f is None or f.workspace_id != member.workspace_id or f.uploaded_by != member.user.id:
        raise ApiError(404, "not_found", "File not found")
    if f.status != "pending":
        raise ApiError(409, "already_completed", "This upload was already completed")
    if KIND_BY_MIME.get(f.mime) not in ("audio", "video"):
        raise ApiError(422, "invalid_source", "Attach an audio or video recording")
    obj = await storage.head(f.storage_key)
    if obj is None:
        raise ApiError(409, "not_uploaded", "The file has not reached storage yet")
    if obj["size"] > MAX_UPLOAD_BYTES:
        await storage.delete(f.storage_key)
        raise ApiError(413, "too_large", "Files are limited to 25 MB")
    f.status, f.size_bytes = "ready", obj["size"]
    heard = body.recorded_at.astimezone(dates.EAT)
    source = Source(
        workspace_id=member.workspace_id,
        file_id=f.id,
        created_by=member.user.id,
        kind=KIND_BY_MIME[f.mime],
        title=f"Antenne · {body.station} · {dates.fr(heard.date())} {heard:%H:%M}"[:500],
        published_at=heard.date().isoformat(),
    )
    db.add(source)
    await db.flush()
    await record(db, member.workspace_id, member.user.id, "source", source.id, "create")
    return source, True


@router.post("/workspaces/{ws}/radio-clips", status_code=201)
async def create_clip(body: ClipIn, member: AnyMember, db: Db) -> ClipOut:
    latest = datetime.now(UTC) + timedelta(minutes=2)  # a phone clock a little ahead is fine
    if body.recorded_at.tzinfo is None or body.recorded_at > latest:
        raise ApiError(422, "invalid_time", "Use a past recording time with timezone")
    source, fresh = await _recording_source(db, member, body)
    location = dict(body.location or {})
    if location.get("region"):
        location["region"] = canonical_region(location["region"])
    elif location.get("name"):
        location = {**(gazetteer(str(location["name"])) or {}), **location}
    else:
        location = region_of_text(body.station) or {}
    location.pop("demo", None)  # only the demo seed marks its own clips
    clip = RadioClip(
        workspace_id=member.workspace_id,
        created_by=member.user.id,
        source_id=source.id if source else None,
        station=body.station.strip(),
        heard_text=body.heard_text,
        language=body.language,
        recorded_at=body.recorded_at,
        location=location,
        clip_at_s=body.clip_at_s,
    )
    db.add(clip)
    await db.flush()
    await record(
        db,
        member.workspace_id,
        member.user.id,
        "radio_clip",
        clip.id,
        "create",
        {"station": clip.station},
    )
    await db.commit()
    await db.refresh(clip)
    if source is not None and fresh:
        await enqueue(
            db,
            member.workspace_id,
            member.user.id,
            "ingest_file",
            {
                "source_id": str(source.id),
                "language": body.language if body.language in ("fr", "mg") else None,
                # a Malagasy passage keeps the veilleur's sentence, never a machine transcript
                **({"transcribe": False} if body.language == "mg" else {}),
            },
        )
    out = _clip_out(clip, source)
    await broadcast(member.workspace_id, "clip.created", out.model_dump(mode="json"))
    if clip.heard_text:
        await match_signals(db, member.workspace_id, clip.heard_text, "clip")
    return out


# --- grouping by claim
def overlap(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


class ClipGroup:
    def __init__(self, item: Item | None = None):
        self.item = item
        self.clips: list[RadioClip] = []
        self.words: set[str] = words(item.title) if item else set()

    def add(self, clip: RadioClip) -> None:
        self.clips.append(clip)
        self.words |= words(clip.heard_text or "")


def group_clips(clips: list[RadioClip], items: dict[uuid.UUID, Item]) -> list[ClipGroup]:
    """Clips that carry the same rumour, oldest first: those attached to a dossier gather under
    it; the others join the group whose words they share (≥ a third), or start a new one."""
    groups: list[ClipGroup] = []
    by_item: dict[uuid.UUID, ClipGroup] = {}
    for clip in sorted(clips, key=lambda c: c.recorded_at):
        if clip.item_id and clip.item_id in items:
            group = by_item.get(clip.item_id)
            if group is None:
                group = by_item[clip.item_id] = ClipGroup(items[clip.item_id])
                groups.append(group)
            group.add(clip)
            continue
        said = words(clip.heard_text or "")
        best, score = None, 0.0
        for group in groups:
            s = overlap(said, group.words)
            if s > score and len(said & group.words) >= 2:
                best, score = group, s
        if best is not None and score >= SAME_RUMOUR:
            best.add(clip)
        else:
            group = ClipGroup()
            group.add(clip)
            groups.append(group)
    return groups


class AntenneClip(BaseModel):
    id: uuid.UUID
    station: str
    recorded_at: datetime
    source_id: uuid.UUID | None
    clip_at_s: float | None
    heard_text: str
    language: str | None
    text_from: str
    demo: bool


class AlertRef(BaseModel):
    """The open alert a row's rumour belongs to (app/modules/alerts.py), so Veille and the alerts
    never tell two stories about the same reports."""

    id: uuid.UUID
    ref: str | None
    level: str
    reports: int


class AntenneRow(BaseModel):
    claim: str
    item_id: uuid.UUID | None
    ref: str | None
    status: Literal["new", "followed", "checked"]
    verdict: str | None
    reports: int
    stations: list[str]
    # The regions the clips were heard in over the 7 days, then over the last 24 hours.
    regions: list[str] = Field(default_factory=list)
    regions_24h: list[str]
    first_at: datetime
    latest: AntenneClip
    clip_ids: list[uuid.UUID]
    demo: bool
    alert: AlertRef | None = None
    # « RNA, 07:42, 0:18 »: the station, the time it was heard and where the passage starts.
    credit: str | None = None
    # The clip's audio, when the station kept the recording: the desk plays it from `clip_at_s`.
    audio_url: str | None = None


def first_sentence(text: str, limit: int = 300) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    m = re.match(r"(.{20,}?[.!?…])(\s|$)", text)
    return (m.group(1) if m else text)[:limit].strip()


def _row(group: ClipGroup, sources: dict[uuid.UUID, Source]) -> AntenneRow:
    clips = sorted(group.clips, key=lambda c: c.recorded_at)
    latest = clips[-1]
    item = group.item
    d = (item.data or {}) if item else {}
    if item and (d.get("verdict") in VERDICTS or item.status in ("verified", "published")):
        status = "checked"
    elif item:
        status = "followed"
    else:
        status = "new"
    day_ago = datetime.now(UTC) - timedelta(hours=24)
    regions: list[str] = []
    all_regions: list[str] = []
    for c in clips:
        region = canonical_region((clip_location(c) or {}).get("region"))
        if region and region not in all_regions:
            all_regions.append(region)
        if c.recorded_at >= day_ago and region and region not in regions:
            regions.append(region)
    stations: list[str] = []
    for c in reversed(clips):
        if c.station not in stations:
            stations.append(c.station)
    texted = next((c for c in reversed(clips) if (c.heard_text or "").strip()), latest)
    out = _clip_out(latest, sources.get(latest.source_id) if latest.source_id else None)
    return AntenneRow(
        claim=item.title if item else first_sentence(texted.heard_text) or texted.station,
        item_id=item.id if item else None,
        ref=d.get("ref"),
        status=status,
        verdict=d.get("verdict") if d.get("verdict") in VERDICTS else None,
        reports=len(clips),
        stations=stations,
        regions=all_regions,
        regions_24h=regions,
        first_at=clips[0].recorded_at,
        latest=AntenneClip(
            id=latest.id,
            station=latest.station,
            recorded_at=latest.recorded_at,
            source_id=latest.source_id,
            clip_at_s=latest.clip_at_s,
            heard_text=out.heard_text,
            language=latest.language,
            text_from=out.text_from,
            demo=out.demo,
        ),
        clip_ids=[c.id for c in clips],
        demo=any(_is_demo(c) for c in clips),
        credit=credit_of(latest),
        audio_url=(
            storage.presign_download(source.file.storage_key, source.file.filename)
            if (source := sources.get(latest.source_id)) and source.file and source.file.storage_key
            else None
        ),
    )


def credit_of(clip: RadioClip) -> str:
    """« RNA, 07:42, 0:18 »: who said it, when, and from where in the recording. Always credited, as
    the rules ask; the offset is left out when the veilleur heard it live."""
    at = clip.recorded_at.astimezone(UTC)
    word = f"{clip.station}, {at.strftime('%H:%M')}"
    if clip.clip_at_s is None:
        return word
    start = int(clip.clip_at_s)
    length = (clip.duration_s or 0) - start
    return f"{word}, {start // 60}:{start % 60:02d}" + (f" ({int(length)} s)" if length > 0 else "")


async def recent_clips(
    db: AsyncSession, workspace_id: uuid.UUID, days: int = ANTENNE_DAYS
) -> list[RadioClip]:
    since = datetime.now(UTC) - timedelta(days=days)
    return list(
        await db.scalars(
            select(RadioClip)
            .where(
                RadioClip.workspace_id == workspace_id,
                RadioClip.recorded_at >= since,
                RadioClip.status != "ignored",
            )
            .order_by(RadioClip.recorded_at.desc())
            .limit(400)
        )
    )


async def _items_of(db: AsyncSession, clips: list[RadioClip]) -> dict[uuid.UUID, Item]:
    ids = {c.item_id for c in clips if c.item_id}
    if not ids:
        return {}
    return {i.id: i for i in await db.scalars(select(Item).where(Item.id.in_(ids)))}


async def antenne_rows(db: AsyncSession, workspace_id: uuid.UUID) -> list[AntenneRow]:
    clips = await recent_clips(db, workspace_id)
    sources = await fill_from_transcripts(db, clips)
    rows = [_row(g, sources) for g in group_clips(clips, await _items_of(db, clips))]
    from app.modules.alerts import alert_index

    index = await alert_index(db, workspace_id)
    for row in rows:
        keys = [f"clip:{c}" for c in row.clip_ids]
        if row.item_id:
            keys.insert(0, f"item:{row.item_id}")
        row.alert = next((index[k] for k in keys if k in index), None)
    order = {"new": 0, "followed": 1, "checked": 2}
    rows.sort(key=lambda r: (order[r.status], -r.reports, -r.latest.recorded_at.timestamp()))
    return rows


@router.get("/workspaces/{ws}/antenne")
async def antenne(
    member: AnyMember,
    db: Db,
    region: str | None = Query(default=None, max_length=120),
    station: str | None = Query(default=None, max_length=120),
    topic: str | None = Query(default=None, max_length=160),
) -> list[AntenneRow]:
    """What the partner radios heard in the last 7 days, one row per claim: new first, then the
    ones the desk follows, then the ones it checked. Filters: region (as the map names it),
    station and a word of the topic."""
    rows = await antenne_rows(db, member.workspace_id)
    want = canonical_region(region) if region else None
    if want:
        rows = [r for r in rows if want in r.regions]
    if station:
        rows = [r for r in rows if station in r.stations]
    if topic:
        needle = fold(topic)
        rows = [r for r in rows if needle in fold(r.claim) or needle in fold(r.latest.heard_text)]
    return rows


class FollowIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # Attach to this dossier; otherwise the clip's group's dossier, or a new one.
    item_id: uuid.UUID | None = None


class FollowOut(BaseModel):
    item_id: uuid.UUID
    ref: str | None
    created: bool
    clip_ids: list[uuid.UUID]


async def add_rumour_stop(
    db: AsyncSession, member: Member, item_id: uuid.UUID, clip: RadioClip
) -> None:
    """The clip becomes a stop of the rumour's road (« Le trajet »): through `trajet.add_stop`
    when that module provides it, otherwise as the same Route row written here."""
    location = _place_out(clip_location(clip)) or {}
    proof = {
        "source_id": str(clip.source_id) if clip.source_id else None,
        "clip_at_s": clip.clip_at_s,
        "clip_id": str(clip.id),
        "note": (clip.heard_text or "")[:300],
    }
    try:
        from app.modules.trajet import add_stop
    except ImportError:
        add_stop = None
    if add_stop is not None:
        await add_stop(
            db,
            member.workspace_id,
            item_id,
            side="rumour",
            channel="radio",
            place=clip.station,
            location=location,
            proof=proof,
            added_by=member.user.id,
            at=clip.recorded_at,
            auto=True,
        )
        return
    db.add(
        Route(
            workspace_id=member.workspace_id,
            item_id=item_id,
            added_by=member.user.id,
            side="rumour",
            channel="radio",
            place=clip.station[:300],
            location=location,
            at=clip.recorded_at,
            proof=proof,
            status="seen",
            auto=True,
        )
    )


@router.post("/workspaces/{ws}/radio-clips/{clip_id}/follow")
async def follow_clip(clip_id: uuid.UUID, body: FollowIn, member: AnyMember, db: Db) -> FollowOut:
    """« Suivre »: the clip (and the clips that carry the same rumour) join a dossier, new or
    existing, and each becomes a radio stop of the rumour's road."""
    from app.modules.items import _out
    from app.modules.public import _next_ref
    from app.modules.rubrique import beats_for, offered_beats

    clip = await _get_clip(db, member, clip_id)
    if clip.status == "ignored":
        clip.status = "new"
    recent = await recent_clips(db, member.workspace_id)
    if clip.id not in {c.id for c in recent}:
        recent.append(clip)
    await fill_from_transcripts(db, recent)
    group = next(g for g in group_clips(recent, await _items_of(db, recent)) if clip in g.clips)

    item: Item | None = None
    if body.item_id:
        item = await db.get(Item, body.item_id)
        if item is None or item.workspace_id != member.workspace_id:
            raise ApiError(404, "not_found", "Item not found")
    elif group.item is not None:
        item = group.item
    created = item is None
    if item is None:
        first = min(group.clips, key=lambda c: c.recorded_at)
        texted = next((c for c in group.clips if (c.heard_text or "").strip()), clip)
        ws = await db.get(Workspace, member.workspace_id)
        item = Item(
            workspace_id=member.workspace_id,
            author_id=member.user.id,
            type="claim",
            title=first_sentence(texted.heard_text) or f"Entendu sur {texted.station}",
            body=texted.heard_text or "",
            status="to_check",
            tags=beats_for(texted.heard_text or "", offered_beats(ws)),
            data={
                "ref": await _next_ref(db, member.workspace_id),
                "first_seen_at": first.recorded_at.astimezone(dates.EAT).isoformat(),
                "origin": "radio",
                "source_count": 0,
                "location": _place_out(clip_location(texted)) or {},
                "from_clip": str(clip.id),
                **({"demo": True} if any(_is_demo(c) for c in group.clips) else {}),
            },
        )
        db.add(item)
        await db.flush()
        await record(db, member.workspace_id, member.user.id, "item", item.id, "create")

    joined = [clip] if body.item_id else [c for c in group.clips if c.item_id != item.id]
    if clip.item_id != item.id and clip not in joined:
        joined.append(clip)
    attached_sources = False
    for c in joined:
        c.item_id, c.status = item.id, "followed"
        await add_rumour_stop(db, member, item.id, c)
        if c.source_id:
            source = await db.get(Source, c.source_id)
            if source is not None and source.item_id is None:
                source.item_id = item.id
                attached_sources = True
        await record(
            db,
            member.workspace_id,
            member.user.id,
            "item",
            item.id,
            "clip",
            {"clip_id": str(c.id), "station": c.station},
        )
    await db.commit()
    await db.refresh(item)
    if attached_sources:
        from app.modules.sources import _sync_source_count

        await _sync_source_count(db, member.workspace_id, item.id)
        await db.refresh(item)
    await broadcast(member.workspace_id, "item.created" if created else "item.updated", _out(item))
    for c in joined:
        await broadcast(
            member.workspace_id,
            "clip.updated",
            {"id": str(c.id), "item_id": str(item.id), "status": c.status},
        )
    return FollowOut(
        item_id=item.id,
        ref=(item.data or {}).get("ref"),
        created=created,
        clip_ids=[c.id for c in joined],
    )


@router.post("/workspaces/{ws}/radio-clips/{clip_id}/ignore")
async def ignore_clip(clip_id: uuid.UUID, member: AnyMember, db: Db) -> ClipOut:
    clip = await _get_clip(db, member, clip_id)
    if clip.item_id:
        raise ApiError(409, "followed", "This clip already feeds a dossier")
    clip.status = "ignored"
    await record(db, member.workspace_id, member.user.id, "radio_clip", clip.id, "ignore")
    await db.commit()
    await db.refresh(clip)
    await broadcast(
        member.workspace_id, "clip.updated", {"id": str(clip.id), "status": clip.status}
    )
    return (await _clips_out(db, [clip]))[0]


# ------------------------------------------------------------------------------ Veille feed
class Checked(BaseModel):
    """A verdict a journalist already signed for this rumour (this newsroom or a public one)."""

    id: uuid.UUID
    title: str
    verdict: str
    newsroom: str
    mine: bool


class FeedEntry(BaseModel):
    id: str
    kind: Literal["tip", "sms", "clip", "press"]
    title: str
    text: str
    at: datetime
    place: dict[str, Any] | None
    station: str | None = None
    url: str | None = None
    item_id: uuid.UUID | None = None
    ref: str | None = None
    status: str
    beats: list[str]
    risk: str | None = None
    already_checked: Checked | None = None
    demo: bool = False


class Already:
    """« Déjà vérifié »: this newsroom's signed verdicts first, then the public archive of every
    newsroom (`public.find_published`). Word overlap, never a model; memoised per request."""

    def __init__(self, db: AsyncSession, workspace_id: uuid.UUID):
        self.db, self.workspace_id = db, workspace_id
        self._own: list[tuple[set[str], Item]] | None = None
        self._name: str | None = None
        self._memo: dict[str, Checked | None] = {}

    async def _load(self) -> list[tuple[set[str], Item]]:
        if self._own is None:
            rows = await self.db.scalars(
                select(Item).where(
                    Item.workspace_id == self.workspace_id,
                    Item.type == "claim",
                    Item.status.in_(["verified", "published"]),
                    Item.data["verdict"].astext.in_(list(VERDICTS)),
                )
            )
            self._own = [(words(f"{i.title} {(i.body or '')[:400]}"), i) for i in rows]
            ws = await self.db.get(Workspace, self.workspace_id)
            self._name = ws.name if ws else ""
        return self._own

    async def __call__(self, text: str, skip: uuid.UUID | None = None) -> Checked | None:
        said = words(text)
        if len(said) < 2:
            return None
        key = f"{skip}|{' '.join(sorted(said))}"
        if key in self._memo:
            return self._memo[key]
        found, best = None, 0.0
        for known, item in await self._load():
            score = overlap(said, known)
            if item.id != skip and score > best and len(said & known) >= 2:
                found, best = item, score
        result = None
        if found is not None and best >= 0.5:
            result = Checked(
                id=found.id,
                title=found.title,
                verdict=found.data["verdict"],
                newsroom=self._name or "",
                mine=True,
            )
        else:
            from app.modules.public import find_published

            for v in await find_published(self.db, text, k=3):
                known = words(v.title)
                if v.id != skip and overlap(said, known) >= 0.5 and len(said & known) >= 2:
                    result = Checked(
                        id=v.id,
                        title=v.title,
                        verdict=v.verdict,
                        newsroom=v.newsroom.name,
                        mine=False,
                    )
                    break
        self._memo[key] = result
        return result


def _matches(entry: FeedEntry, region: str | None, beat: str | None) -> bool:
    if region:
        want = canonical_region(region) or region
        got = (entry.place or {}).get("region")
        if not got or fold(got) != fold(want):
            return False
    return not beat or fold(beat) in {fold(b) for b in entry.beats}


RISK_LEVELS = ("low", "medium", "high")


def risk_level(d: dict[str, Any] | None) -> str | None:
    """The danger level of a dossier: a journalist's adjustment (`risk_override`) wins over
    Checky's own (`risk`, the tone lexicon and the Lecteur)."""
    d = d or {}
    for key in ("risk_override", "risk"):
        risk = d.get(key)
        if isinstance(risk, dict) and risk.get("level") in RISK_LEVELS:
            return risk["level"]
    return None


_risk = risk_level


async def feed_entries(
    db: AsyncSession,
    workspace: Workspace,
    *,
    days: int = 7,
    region: str | None = None,
    beat: str | None = None,
    checked: bool = True,
) -> list[FeedEntry]:
    """Tips, SMS questions, radio clips and press items of the last `days`, newest first."""
    from app.modules.rubrique import beats_for, offered_beats

    offered = offered_beats(workspace)
    since = datetime.now(UTC) - timedelta(days=days)
    entries: list[FeedEntry] = []

    rows = await db.scalars(
        select(Item).where(
            Item.workspace_id == workspace.id,
            Item.created_at >= since,
            (Item.type == "press") | (Item.data["public_tip"].astext == "true"),
        )
    )
    for item in rows:
        d = item.data or {}
        press = item.type == "press"
        at = dates.parse_moment(d.get("published_at" if press else "first_seen_at"))
        tagged = set(item.tags or []) & set(offered)
        entries.append(
            FeedEntry(
                id=f"item:{item.id}",
                kind="press" if press else "tip",
                title=item.title,
                text=(item.body or "")[:600],
                at=at or item.created_at,
                place=_place_out(item_location(item)),
                station=d.get("outlet") if press else None,
                url=d.get("link") or d.get("tip_url"),
                item_id=None if press else item.id,
                ref=d.get("ref"),
                status=item.status,
                beats=sorted(tagged | set(beats_for(f"{item.title} {item.body}", offered))),
                risk=_risk(d),
                demo=bool(d.get("demo")),
            )
        )

    for q in await db.scalars(
        select(PublicQuestion).where(
            PublicQuestion.workspace_id == workspace.id,
            PublicQuestion.channel == "sms",
            PublicQuestion.created_at >= since,
        )
    ):
        loc = q.location if (q.location or {}).get("region") else region_of_text(q.text)
        entries.append(
            FeedEntry(
                id=f"sms:{q.id}",
                kind="sms",
                title=first_sentence(q.text, 200),
                text=q.text[:600],
                at=q.created_at,
                place=_place_out(loc),
                station=q.contact_masked,
                item_id=q.item_id,
                status="followed" if q.item_id else "new",
                beats=beats_for(q.text, offered),
                demo=bool((q.location or {}).get("demo")),
            )
        )

    clips = await recent_clips(db, workspace.id, days)
    sources = await fill_from_transcripts(db, clips)
    followed = {c.item_id for c in clips if c.item_id}
    refs = (
        {
            i.id: (i.data or {}).get("ref")
            for i in (await db.scalars(select(Item).where(Item.id.in_(followed)))).all()
        }
        if followed
        else {}
    )
    for c in clips:
        out = _clip_out(c, sources.get(c.source_id) if c.source_id else None)
        entries.append(
            FeedEntry(
                id=f"clip:{c.id}",
                kind="clip",
                title=first_sentence(out.heard_text, 200) or c.station,
                text=out.heard_text[:600],
                at=c.recorded_at,
                place=out.location,
                station=c.station,
                item_id=c.item_id,
                ref=refs.get(c.item_id) if c.item_id else None,
                status=c.status,
                beats=beats_for(out.heard_text, offered),
                demo=out.demo,
            )
        )

    entries = [e for e in entries if _matches(e, region, beat)]
    entries.sort(key=lambda e: e.at, reverse=True)
    entries = entries[:FEED_LIMIT]
    if checked:
        already = Already(db, workspace.id)
        for e in entries:
            e.already_checked = await already(f"{e.title} {e.text}", skip=e.item_id)
    return entries


class FeedOut(BaseModel):
    entries: list[FeedEntry]
    counts: dict[str, int]
    since: datetime
    feeds_configured: bool
    streams_configured: bool


_POLLED: dict[uuid.UUID, float] = {}
POLL_EVERY = 20 * 60.0


CAPTURE_EVERY = timedelta(minutes=5)


async def _capture_recent(db: AsyncSession, workspace_id: uuid.UUID) -> bool:
    """This newsroom already has a capture started in the last minutes (queued or running ones
    count only while recent, so a stuck job cannot block captures for ever): each one records a
    minute of every stream, so a refresh must not stack them up."""
    since = datetime.now(UTC) - CAPTURE_EVERY
    found = await db.scalar(
        select(Job.id)
        .where(
            Job.workspace_id == workspace_id,
            Job.kind == "radio_capture",
            Job.created_at >= since,
        )
        .limit(1)
    )
    return found is not None


async def _maybe_poll(db: AsyncSession, member: Member, force: bool = False) -> list[str]:
    """Queue the press reader (and, when asked, the radio capture) when they are configured, at
    most every 20 minutes per newsroom: there is no scheduler, the desk's visits drive it."""
    s = get_settings()
    if not force and time.monotonic() - _POLLED.get(member.workspace_id, -POLL_EVERY) < POLL_EVERY:
        return []
    _POLLED[member.workspace_id] = time.monotonic()
    queued = []
    if veille_poll.parse_feeds(s.press_feeds):
        await enqueue(db, member.workspace_id, member.user.id, "veille_poll", {})
        queued.append("veille_poll")
    if (
        force
        and radio_capture.parse_streams(s.radio_streams)
        and not await _capture_recent(db, member.workspace_id)
    ):
        await enqueue(db, member.workspace_id, member.user.id, "radio_capture", {})
        queued.append("radio_capture")
    return queued


@router.get("/workspaces/{ws}/veille")
async def veille(
    member: AnyMember,
    db: Db,
    region: str | None = None,
    beat: str | None = None,
    kind: Literal["tip", "sms", "clip", "press"] | None = None,
    days: int = 7,
) -> FeedOut:
    """What circulates: tips, SMS questions, radio clips and press items, newest first, each
    marked « Déjà vérifié » when a journalist already signed a verdict on it."""
    days = max(1, min(days, 30))
    workspace = await db.get(Workspace, member.workspace_id)
    await _maybe_poll(db, member)
    entries = await feed_entries(db, workspace, days=days, region=region, beat=beat)
    counts: dict[str, int] = defaultdict(int)
    for e in entries:
        counts[e.kind] += 1
    s = get_settings()
    return FeedOut(
        entries=[e for e in entries if not kind or e.kind == kind],
        counts=dict(counts),
        since=datetime.now(UTC) - timedelta(days=days),
        feeds_configured=bool(veille_poll.parse_feeds(s.press_feeds)),
        streams_configured=bool(radio_capture.parse_streams(s.radio_streams)),
    )


@router.post("/workspaces/{ws}/veille/refresh", status_code=202)
async def refresh(member: AnyMember, db: Db) -> dict[str, list[str]]:
    """Read the press feeds (and capture the radio streams) now."""
    return {"queued": await _maybe_poll(db, member, force=True)}


class RegionCount(BaseModel):
    region: str
    country: str | None = None
    lat: float | None
    lng: float | None
    last_24h: int
    last_7d: int
    high_risk: int
    kinds: dict[str, int]


class CountryCount(BaseModel):
    country: str
    last_7d: int


class MapOut(BaseModel):
    regions: list[RegionCount]
    unplaced: int
    total: int
    # The country shown (the newsroom's by default, « monde » for every country), the newsroom's
    # own, and what circulated in each country this week (the menu above the map).
    country: str = "Madagascar"
    home: str = "Madagascar"
    countries: list[CountryCount] = Field(default_factory=list)


@router.get("/workspaces/{ws}/veille/map")
async def veille_map(member: AnyMember, db: Db, country: str | None = None) -> MapOut:
    """Where rumours circulate: per region, the claims, clips, press items and questions of the
    last 24 hours and 7 days, and how many dossiers were judged high-risk. `country` (a name, or
    « monde ») picks the country shown; the newsroom's own country by default."""
    from app.modules.workspaces import newsroom_settings

    home = newsroom_settings(await db.get(Workspace, member.workspace_id)).country
    shown = (country or "").strip() or home
    since = datetime.now(UTC) - timedelta(days=7)
    day_ago = datetime.now(UTC) - timedelta(hours=24)
    counts: dict[str, dict[str, Any]] = {}
    tally = {"unplaced": 0, "total": 0}

    def add(loc: dict[str, Any] | None, at: datetime, kind: str, high: bool = False) -> None:
        tally["total"] += 1
        region = canonical_region((loc or {}).get("region"))
        if not region:
            tally["unplaced"] += 1
            return
        where = (
            "Madagascar" if region in MG_REGIONS else ((loc or {}).get("country") or home).strip()
        )
        row = counts.setdefault(
            (where, region),
            {"last_24h": 0, "last_7d": 0, "high_risk": 0, "kinds": defaultdict(int), "loc": loc},
        )
        row["last_7d"] += 1
        row["last_24h"] += int(at >= day_ago)
        row["high_risk"] += int(high)
        row["kinds"][kind] += 1

    for item in await db.scalars(
        select(Item).where(
            Item.workspace_id == member.workspace_id,
            Item.type.in_(["claim", "press"]),
            Item.created_at >= since,
        )
    ):
        d = item.data or {}
        at = dates.parse_moment(d.get("first_seen_at")) or item.created_at
        if at < since:
            continue  # entered this week, but first seen long ago: not circulating now
        kind = "press" if item.type == "press" else "tip" if d.get("public_tip") else "claim"
        add(item_location(item), at, kind, _risk(d) == "high")
    for clip in await recent_clips(db, member.workspace_id):
        add(clip_location(clip), clip.recorded_at, "clip")
    for q in await db.scalars(
        select(PublicQuestion).where(
            PublicQuestion.workspace_id == member.workspace_id,
            PublicQuestion.created_at >= since,
        )
    ):
        loc = q.location if (q.location or {}).get("region") else region_of_text(q.text)
        add(loc, q.created_at, "sms" if q.channel == "sms" else "question")

    per_country: dict[str, int] = defaultdict(int)
    for (where, _), row in counts.items():
        per_country[where] += row["last_7d"]
    world = fold(shown) in {"monde", "world"}
    regions = []
    for (where, region), row in counts.items():
        if not world and fold(where) != fold(shown):
            continue
        lat = lng = None
        if region in MG_REGIONS:
            _, lat, lng = MG_REGIONS[region]
        elif (loc := row["loc"] or {}).get("lat") is not None:
            lat, lng = loc.get("lat"), loc.get("lng")
        regions.append(
            RegionCount(
                region=region,
                country=where,
                lat=lat,
                lng=lng,
                last_24h=row["last_24h"],
                last_7d=row["last_7d"],
                high_risk=row["high_risk"],
                kinds=dict(row["kinds"]),
            )
        )
    regions.sort(key=lambda r: (-r.last_24h, -r.last_7d, r.region))
    return MapOut(
        regions=regions,
        unplaced=tally["unplaced"],
        total=tally["total"],
        country="monde" if world else shown,
        home=home,
        countries=[
            CountryCount(country=c, last_7d=n)
            for c, n in sorted(per_country.items(), key=lambda x: (-x[1], x[0]))
        ],
    )


# ----------------------------------------------------------------------- Météo des rumeurs
@router.get("/workspaces/{ws}/meteo")
async def meteo(member: AnyMember, db: Db, region: str | None = None) -> dict[str, Any]:
    """This week's likely rumours: the season rules in effect and « Ça revient »."""
    from app.modules.rubrique import load_prefs

    workspace = await db.get(Workspace, member.workspace_id)
    pref = await load_prefs(db, member)
    return await seasons.meteo(
        db, workspace, canonical_region(region), pref.beats if pref else None
    )


# ------------------------------------------------------------------------------- demo seed
DEMO_SIGNALS = ("délestage", "enlèvement")
# Fictional stations and bulletins, flagged « démo » (location.demo). The Malagasy sentence is
# what a veilleur would type (to be reread by a native speaker).
DEMO_CLIPS: tuple[dict[str, Any], ...] = (
    {
        "station": "RDJ (démo)",
        "at": (6, 0),
        "language": "fr",
        "region": "Analamanga",
        "text": (
            "Au journal de 6 heures, un auditeur affirme que la JIRAMA prévoit 72 heures de "
            "délestage dès demain sur tout Antananarivo, communiqué à l'appui."
        ),
        "ref": "FAN-0145",
    },
    {
        "station": "Radio Fanambarana Toamasina (démo)",
        "at": (7, 30),
        "language": "mg",
        "region": "Atsinanana",
        "text": (
            "Nilaza ny mpihaino iray fa hisy fahatapahan-jiro mandritra ny 12 ora isan'andro "
            "eto Toamasina manomboka rahampitso."
        ),
        "ref": None,
    },
    {
        "station": "Radio Feon'i Boeny (démo)",
        "at": (8, 15),
        "language": "fr",
        "region": "Boeny",
        "text": (
            "Un appel d'auditeur affirme qu'un enlèvement d'enfant a eu lieu près du marché de "
            "Mahajanga hier soir ; la gendarmerie n'a rien confirmé à l'antenne."
        ),
        "ref": None,
    },
)


def _demo_moment(hour: int, minute: int) -> datetime:
    """Today at that time in Madagascar, or yesterday when that time has not come yet."""
    now = dates.now()
    moment = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return moment - timedelta(days=1) if moment > now else moment


def _region_place(region: str, name: str | None = None) -> dict[str, Any]:
    _, lat, lng = MG_REGIONS[region]
    return {
        "name": name or region,
        "country": "Madagascar",
        "region": region,
        "lat": lat,
        "lng": lng,
    }


async def seed_demo(db: AsyncSession, workspace_id: uuid.UUID, user_id: str, items) -> None:
    """Three radio clips (the RDJ one already follows FAN-0145), two watched words and the
    season rules. Idempotent: the demo clips and words are replaced. No item is added here: the
    demo's claims are `demo.DEMO_CLAIMS` (« Ça revient » shows once verdicts of earlier years
    exist)."""
    await db.execute(
        delete(RadioClip).where(
            RadioClip.workspace_id == workspace_id,
            RadioClip.location["demo"].astext == "true",
        )
    )
    await db.execute(
        delete(Signal).where(
            Signal.workspace_id == workspace_id, Signal.word.in_(list(DEMO_SIGNALS))
        )
    )
    await seasons.seed(db)
    for word in DEMO_SIGNALS:
        db.add(Signal(workspace_id=workspace_id, created_by=user_id, word=word))

    created = []
    for spec in DEMO_CLIPS:
        item = (items or {}).get(spec["ref"]) if spec["ref"] else None
        clip = RadioClip(
            workspace_id=workspace_id,
            created_by=user_id,
            station=spec["station"],
            heard_text=spec["text"],
            language=spec["language"],
            recorded_at=_demo_moment(*spec["at"]),
            location={**_region_place(spec["region"]), "demo": True},
            item_id=item.id if item is not None else None,
            status="followed" if item is not None else "new",
        )
        db.add(clip)
        created.append(clip)

    await db.commit()
    for clip in created:
        await match_signals(db, workspace_id, clip.heard_text, "clip")
