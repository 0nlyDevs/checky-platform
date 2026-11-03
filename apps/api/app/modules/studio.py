"""« Studio »: a live radio or TV show checked while it airs, then its bilan.

Before the show the producer names it, picks its topics (the newsroom's beats) and the sound input;
`GET …/studio/{show}/pack` hands the browser the published verdicts, official figures and
registered originals it keeps in memory and IndexedDB, so a weak connection does not stop it.

During the show the browser posts 8–10 s audio chunks (`POST …/chunk`). French is transcribed by
Whisper (`core/stt.py`) into timed segments; Malagasy never is (rule 6: the producer types what was
said, `POST …/claims`). Each sentence that carries a number, an institution, an attribution
(« selon… ») or a watched word is a claim, found by code; one cheap model call per 30 s of show at
most adds the claims code missed, each kept only if found verbatim. Every claim is set against the
official figures, the registry of originals and the signed verdicts, without a model, and gets a
flag that is never a verdict: `consistent` (« Conforme à … »), `contradicted` (« Contredit par … »)
or `no_source` (« Aucune source trouvée », which proves nothing).

Two screens: the producer sees every flag and sends it to the presenter or sets it aside; the
presenter sees the last three sent. « Mode prudent » (nothing reaches the presenter without the
producer) is the only mode. Realtime goes through a Socket.IO room per show (`studio.join`).
Mode débat: the producer marks who speaks; claims are counted per speaker, never scored or ranked.
After the show, the bilan lists every claim with its clip at the second; « Suivre dans le desk »
opens a dossier through the ordinary item and source routes, the clip as its first source, and
adds a radio stop to Le trajet.
"""

import asyncio
import io
import logging
import math
import re
import uuid
import wave
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import ai, dates, numbers, places, storage, stt
from app.core.access import AnyMember, Db, Member, get_membership
from app.core.activity import record
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.errors import ApiError
from app.core.models import (
    Communique,
    Figure,
    File,
    Item,
    Show,
    ShowClaim,
    Source,
    Workspace,
)
from app.core.words import words
from app.realtime.server import sio

log = logging.getLogger("checky.studio")
router = APIRouter(tags=["studio"])

CHUNK_MAX_BYTES = 3_000_000  # 10 s of opus is ~20 KB; a WAV fallback stays well under this
MODEL_EVERY_S = 30.0  # one cheap model call per 30 s of show at most
MIN_CLAIM_CHARS = 25
PRESENTER_FLAGS = 3
DEFAULT_CAMPS = ("Gouvernement", "Opposition", "Société civile", "Indépendant")
VERDICT_MIN_WORDS = 3
VERDICT_MIN_SHARE = 0.4

# « selon la JIRAMA », « d'après le ministère », « a annoncé que »: someone is quoted as a source.
ATTRIBUTION = re.compile(
    r"\b(?:selon|d['’]apr[eè]s|a annonc[ée]|annonce que|affirme|a d[ée]clar[ée]|d[ée]clare que"
    r"|confirme que|a confirm[ée]|les chiffres|officiellement|araka|hoy)\b",
    re.IGNORECASE,
)
SENTENCE = re.compile(r"(?<=[.!?…])\s+")

EXTRACT_SYSTEM = """Tu écoutes une émission de radio en direct pour une rédaction qui vérifie les \
faits. Dans le passage transcrit, relève au plus trois affirmations vérifiables (un chiffre, un fait \
daté, une décision attribuée à une institution, une accusation précise) que l'on peut comparer à une \
source. Recopie chacune MOT POUR MOT depuis le passage, sans la reformuler. Ignore les opinions, les \
questions et les salutations. Réponds avec un seul objet JSON : {"claims": [{"text": "…"}]}"""


# --- shapes ------------------------------------------------------------------------------------


class Speaker(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=80)
    camp: str | None = Field(default=None, max_length=80)


class ShowIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=200)
    station: str | None = Field(default=None, max_length=120)
    topics: list[str] = Field(default_factory=list, max_length=12)
    language: Literal["fr", "mg"] = "fr"
    input: Literal["microphone", "stream"] = "microphone"
    speakers: list[Speaker] = Field(default_factory=list, max_length=8)


class ShowPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, min_length=1, max_length=200)
    station: str | None = Field(default=None, max_length=120)
    topics: list[str] | None = Field(default=None, max_length=12)
    input: Literal["microphone", "stream"] | None = None
    speakers: list[Speaker] | None = Field(default=None, max_length=8)


class ClaimOut(BaseModel):
    id: uuid.UUID
    at_s: float
    end_s: float | None
    text: str
    speaker_id: str | None
    origin: str
    spotted: dict[str, Any]
    flag: dict[str, Any]
    status: str
    question: str | None
    sent_at: datetime | None
    item_id: uuid.UUID | None
    ref: str | None = None
    clip: dict[str, Any] | None = None


class SpeakerCount(BaseModel):
    speaker_id: str | None
    name: str | None
    camp: str | None
    claims: int
    contradicted: int
    contradicted_official: int
    consistent: int
    no_source: int


class ShowBrief(BaseModel):
    id: uuid.UUID
    title: str
    station: str | None
    topics: list[str]
    language: str
    status: str
    started_at: datetime | None
    ended_at: datetime | None
    created_at: datetime
    claims: int
    sent: int
    is_demo: bool


class ShowOut(ShowBrief):
    input: str
    mode: str
    speakers: list[Speaker]
    turns: list[dict[str, Any]]
    current_speaker_id: str | None
    camps: list[str]
    ai_enabled: bool
    segments: list[dict[str, Any]]
    chunks: int
    duration_s: float
    claim_list: list[ClaimOut]
    by_speaker: list[SpeakerCount]


class ClaimIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=3, max_length=600)
    at_s: float | None = Field(default=None, ge=0)
    speaker_id: str | None = Field(default=None, max_length=40)


class ClaimPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    speaker_id: str | None = Field(default=None, max_length=40)


class SendIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(default="", max_length=400)


class SpeakerIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    speaker_id: str | None = Field(default=None, max_length=40)
    at_s: float | None = Field(default=None, ge=0)


class FollowOut(BaseModel):
    item_id: uuid.UUID
    ref: str | None
    source_id: uuid.UUID


# --- helpers -----------------------------------------------------------------------------------


def show_room(show_id: uuid.UUID | str) -> str:
    return f"show:{show_id}"


async def emit(show_id: uuid.UUID, event: str, payload: dict[str, Any]) -> None:
    await sio.emit(event, payload, room=show_room(show_id))


@sio.on("studio.join")
async def studio_join(sid, data):
    """A member's screen joins one show's room (producer or presenter)."""
    try:
        show_id = uuid.UUID(str((data or {}).get("show_id")))
    except (ValueError, TypeError):
        return {"ok": False, "error": "bad_show"}
    session = await sio.get_session(sid)
    if not await can_join(session.get("user_id"), show_id):
        return {"ok": False, "error": "not_found"}
    await sio.enter_room(sid, show_room(show_id))
    return {"ok": True}


async def can_join(user_id: str | None, show_id: uuid.UUID) -> bool:
    if not user_id:
        return False
    async with SessionLocal() as db:
        show = await db.get(Show, show_id)
        if show is None:
            return False
        return await get_membership(db, show.workspace_id, user_id) is not None


async def _get_show(db: AsyncSession, member: Member, show_id: uuid.UUID) -> Show:
    show = await db.get(Show, show_id)
    if show is None or show.workspace_id != member.workspace_id:
        raise ApiError(404, "not_found", "Show not found")
    return show


async def _get_claim(db: AsyncSession, show: Show, claim_id: uuid.UUID) -> ShowClaim:
    claim = await db.get(ShowClaim, claim_id)
    if claim is None or claim.show_id != show.id:
        raise ApiError(404, "not_found", "Claim not found")
    return claim


def _camps(ws: Workspace | None) -> list[str]:
    camps = ((ws.settings or {}).get("camps") if ws else None) or DEFAULT_CAMPS
    return [str(c) for c in camps][:12]


def _ai_enabled(ws: Workspace | None) -> bool:
    return bool(((ws.settings or {}).get("ai_enabled", True)) if ws else True)


def speaker_at(show: Show, at_s: float) -> str | None:
    """Who was marked as speaking at `at_s` (the last turn that started before it)."""
    current = None
    for turn in sorted((show.settings or {}).get("turns") or [], key=lambda t: t["at_s"]):
        if turn["at_s"] <= at_s + 0.5:
            current = turn.get("speaker_id")
    return current


def show_time(show: Show) -> float:
    if show.started_at is None:
        return 0.0
    end = show.ended_at or datetime.now(UTC)
    return max(0.0, (end - show.started_at).total_seconds())


def chunk_at(show: Show, at_s: float) -> dict[str, Any] | None:
    """The stored chunk that holds the second `at_s`."""
    best = None
    for c in show.chunks or []:
        if c.get("key") and c["start_s"] <= at_s + 0.25:
            if at_s < c["start_s"] + (c.get("duration_s") or 10) + 0.25:
                return c
            best = c
    return best if best and at_s - best["start_s"] < 60 else None


def clip_of(show: Show, claim: ShowClaim, presign: bool) -> dict[str, Any] | None:
    c = chunk_at(show, claim.at_s)
    if c is None:
        return None
    clip = {
        "seq": c["seq"],
        "offset_s": round(max(0.0, claim.at_s - c["start_s"]), 2),
        "mime": c.get("mime"),
        "file_id": c.get("file_id"),
    }
    if presign and storage.configured():
        try:
            clip["url"] = storage.presign_download(c["key"])
        except Exception:  # noqa: BLE001 - a storage hiccup must not hide the bilan
            log.warning("could not presign %s", c["key"])
    return clip


def claim_out(claim: ShowClaim, show: Show | None = None, presign: bool = False) -> ClaimOut:
    out = ClaimOut.model_validate(claim, from_attributes=True)
    if show is not None:
        out.clip = clip_of(show, claim, presign)
    return out


def counts(show: Show, claims: list[ShowClaim]) -> list[SpeakerCount]:
    """Mode débat: claims per speaker, in the order the producer listed them. Counts only; never a
    score, never a ranking."""
    speakers = (show.settings or {}).get("speakers") or []
    rows: list[SpeakerCount] = []
    for sp in [*speakers, None]:
        sid = sp["id"] if sp else None
        mine = [c for c in claims if c.speaker_id == sid and c.status != "dismissed"]
        if sp is None and not mine:
            continue
        kinds = [(c.flag or {}).get("kind") for c in mine]
        official = [
            c
            for c in mine
            if (c.flag or {}).get("kind") == "contradicted"
            and any(
                e.get("stance") == "contradicted" and e.get("type") in ("figure", "registry")
                for e in (c.flag or {}).get("evidence") or []
            )
        ]
        rows.append(
            SpeakerCount(
                speaker_id=sid,
                name=sp["name"] if sp else None,
                camp=sp.get("camp") if sp else None,
                claims=len(mine),
                contradicted=kinds.count("contradicted"),
                contradicted_official=len(official),
                consistent=kinds.count("consistent"),
                no_source=kinds.count("no_source"),
            )
        )
    return rows


def brief(show: Show, claims: list[ShowClaim]) -> ShowBrief:
    return ShowBrief(
        id=show.id,
        title=show.title,
        station=(show.settings or {}).get("station"),
        topics=list(show.topics or []),
        language=show.language,
        status=show.status,
        started_at=show.started_at,
        ended_at=show.ended_at,
        created_at=show.created_at,
        claims=len([c for c in claims if c.status != "dismissed"]),
        sent=len([c for c in claims if c.status == "sent"]),
        is_demo=show.is_demo,
    )


async def _claims(db: AsyncSession, show_id: uuid.UUID) -> list[ShowClaim]:
    rows = await db.scalars(
        select(ShowClaim)
        .where(ShowClaim.show_id == show_id)
        .order_by(ShowClaim.at_s, ShowClaim.created_at)
    )
    return list(rows)


async def _refs(db: AsyncSession, claims: list[ShowClaim]) -> dict[uuid.UUID, str | None]:
    ids = [c.item_id for c in claims if c.item_id]
    if not ids:
        return {}
    rows = await db.scalars(select(Item).where(Item.id.in_(ids)))
    return {i.id: (i.data or {}).get("ref") for i in rows}


async def show_out(db: AsyncSession, show: Show, presign: bool = False) -> ShowOut:
    ws = await db.get(Workspace, show.workspace_id)
    claims = await _claims(db, show.id)
    refs = await _refs(db, claims)
    out = []
    for c in claims:
        o = claim_out(c, show, presign)
        o.ref = refs.get(c.item_id) if c.item_id else None
        out.append(o)
    settings = show.settings or {}
    return ShowOut(
        **brief(show, claims).model_dump(),
        input=settings.get("input", "microphone"),
        mode="prudent",
        speakers=[Speaker(**s) for s in settings.get("speakers") or []],
        turns=settings.get("turns") or [],
        current_speaker_id=settings.get("current_speaker_id"),
        camps=_camps(ws),
        ai_enabled=_ai_enabled(ws),
        segments=show.segments or [],
        chunks=len(show.chunks or []),
        duration_s=round(show_time(show), 1),
        claim_list=out,
        by_speaker=counts(show, claims),
    )


# --- spotting and flags (code, no model) -------------------------------------------------------


def sentences(text: str) -> list[str]:
    return [s.strip() for s in SENTENCE.split(text or "") if s.strip()]


def spot(sentence: str, issuers: list[str], watched: list[str]) -> dict[str, Any] | None:
    """Why a sentence is a checkable claim, or None: a number with a unit, a named institution, an
    attribution (« selon… ») or a watched word. Short sentences are left out."""
    from app.modules import crew, registry, veille

    if len(sentence) < MIN_CLAIM_CHARS:
        return None
    found_numbers = [n["claimed"] for n in numbers.extract_numbers(sentence)]
    # Known names only (registry, Annuaire, the usual institutions): speech is transcribed without
    # reliable capitals, so registry's « ministère + capitalised words » reading over-reaches here.
    folded = places.fold(sentence)
    named = [
        n for n in sorted(set(issuers), key=len, reverse=True) if registry._mentions(folded, n)
    ]
    named += [m.group(0) for m in crew.INSTITUTION.finditer(sentence) if m.group(0) not in named]
    said = bool(ATTRIBUTION.search(sentence))
    heard = [w for w in watched if veille.mentions(w, sentence)]
    if not (found_numbers or named or said or heard):
        return None
    return {
        "numbers": found_numbers[:6],
        "institutions": named[:6],
        "attribution": said,
        "watched": heard[:6],
    }


def _verdict_stance(verdict: str) -> str:
    return {"true": "consistent", "false": "contradicted", "misleading": "contradicted"}.get(
        verdict, "none"
    )


async def signed_verdicts(db: AsyncSession, ws: uuid.UUID, text: str, k: int = 2) -> list[dict]:
    """Verdicts signed and published by this newsroom or a public one that speak of the same thing
    (accent-free word overlap, no model)."""
    asked = words(text)
    if len(asked) < VERDICT_MIN_WORDS:
        return []
    rows = (
        await db.execute(
            select(Item, Workspace)
            .join(Workspace, Workspace.id == Item.workspace_id)
            .where(
                or_(Item.workspace_id == ws, Workspace.is_public.is_(True)),
                Item.type == "claim",
                Item.status == "published",
                Item.data["verdict"].astext.in_(["true", "misleading", "false", "unverifiable"]),
            )
            .limit(500)
        )
    ).all()
    scored = []
    for item, newsroom in rows:
        shared = asked & words(f"{item.title} {item.body}")
        share = len(shared) / max(1, len(asked))
        if len(shared) >= VERDICT_MIN_WORDS and share >= VERDICT_MIN_SHARE:
            scored.append((share, item, newsroom))
    scored.sort(key=lambda r: r[0], reverse=True)
    out = []
    for _, item, newsroom in scored[:k]:
        d = item.data or {}
        signed = dates.parse_moment(d.get("signed_at") or d.get("published_at")) or item.updated_at
        out.append(
            {
                "type": "verdict",
                "stance": _verdict_stance(d["verdict"]),
                "verdict": d["verdict"],
                "ref": d.get("ref"),
                "title": item.title,
                "item_id": str(item.id) if item.workspace_id == ws else None,
                "source": newsroom.name,
                "own": item.workspace_id == ws,
                "date": signed.date().isoformat() if signed else None,
                "date_label": dates.fr(signed.astimezone(dates.EAT).date()) if signed else "",
                "url": None,
                "demo": bool(d.get("demo")),
            }
        )
    return out


RANKING = {"contradicted": 0, "consistent": 1, "related": 2, "none": 3}


async def flag_for(db: AsyncSession, ws: uuid.UUID, text: str) -> dict[str, Any]:
    """Set a claim against the official figures, the registry and the signed verdicts. The flag is
    `contradicted` when one source says otherwise, `consistent` when one agrees and none
    contradicts, `no_source` otherwise. Each piece of evidence carries its source and its date."""
    from app.modules import figures, registry

    evidence: list[dict[str, Any]] = []
    for r in await figures.check_numbers(db, ws, text):
        f = r.get("figure")
        if r["verdict"] == "no_figure" or not f:
            continue
        evidence.append(
            {
                "type": "figure",
                "stance": "consistent" if r["verdict"] == "matches" else "contradicted",
                "claimed": r["claimed"],
                "official": f"{f['value']} {f['unit'] or ''}".strip(),
                "title": f["label"],
                "source": f["source_name"],
                "date": f["as_of"],
                "date_label": f["as_of_label"],
                "url": f["source_url"],
                "old": f["old"],
                "demo": f["is_demo"],
            }
        )
    reg = await registry.match_text(db, ws, text, with_contacts=False)
    if reg["status"] in ("authentic", "modified") and reg.get("communique"):
        c = reg["communique"]
        changed = [n for n in reg.get("changed_numbers") or [] if n.get("original")]
        stance = (
            "consistent"
            if reg["status"] == "authentic"
            else ("contradicted" if changed else "related")
        )
        day = dates.parse(c.get("issued_on"))
        evidence.append(
            {
                "type": "registry",
                "stance": stance,
                "title": c.get("title") or "",
                "source": c["issuer"],
                "number": c.get("number"),
                "changed": changed[:3],
                "date": c.get("issued_on"),
                "date_label": dates.fr(day) if day else "",
                "url": c.get("seal_url") or c.get("url"),
                "demo": bool(c.get("is_demo")),
            }
        )
    elif reg["status"] in ("not_found", "inconsistent"):
        evidence.append(
            {
                "type": "registry",
                "stance": "none",
                "status": reg["status"],
                "source": reg.get("issuer"),
                "number": reg.get("number"),
                "summary": reg.get("summary"),
            }
        )
    evidence += await signed_verdicts(db, ws, text)
    evidence.sort(key=lambda e: RANKING.get(e["stance"], 9))
    stances = {e["stance"] for e in evidence}
    kind = (
        "contradicted"
        if "contradicted" in stances
        else "consistent"
        if "consistent" in stances
        else "no_source"
    )
    return {"kind": kind, "evidence": evidence[:5], "checked_at": datetime.now(UTC).isoformat()}


async def _issuers(db: AsyncSession, ws: uuid.UUID) -> list[str]:
    from app.modules import registry

    registered = (
        await db.scalars(
            select(Communique.issuer)
            .where(Communique.workspace_id == ws, Communique.status == "original")
            .distinct()
        )
    ).all()
    return [*registered, *await registry.institution_names(db, ws), *registry.INSTITUTIONS]


async def _watched(db: AsyncSession, ws: uuid.UUID) -> list[str]:
    from app.core.models import Signal

    return list(
        (
            await db.scalars(
                select(Signal.word).where(Signal.workspace_id == ws, Signal.active.is_(True))
            )
        ).all()
    )


async def add_claim(
    db: AsyncSession,
    show: Show,
    text: str,
    at_s: float,
    *,
    origin: str,
    end_s: float | None = None,
    spotted: dict[str, Any] | None = None,
    speaker_id: str | None = None,
) -> ShowClaim:
    claim = ShowClaim(
        show_id=show.id,
        workspace_id=show.workspace_id,
        at_s=round(at_s, 2),
        end_s=round(end_s, 2) if end_s is not None else None,
        text=text.strip()[:600],
        speaker_id=speaker_id if speaker_id is not None else speaker_at(show, at_s),
        origin=origin,
        spotted=spotted or {},
        flag=await flag_for(db, show.workspace_id, text),
        status="pending",
    )
    db.add(claim)
    await db.flush()
    return claim


async def spot_claims(
    db: AsyncSession, show: Show, segments: list[dict[str, Any]]
) -> list[ShowClaim]:
    """The claims code finds in new segments, each at the second its segment starts."""
    issuers = await _issuers(db, show.workspace_id)
    watched = await _watched(db, show.workspace_id)
    made = []
    for seg in segments:
        for sentence in sentences(seg["text"]):
            why = spot(sentence, issuers, watched)
            if why is None:
                continue
            made.append(
                await add_claim(
                    db, show, sentence, seg["start"], origin="code", end_s=seg["end"], spotted=why
                )
            )
    return made


def _norm(s: str) -> str:
    from app.modules.quotes import _norm as norm

    return norm(s)


async def model_claims(show_id: uuid.UUID) -> None:
    """The one cheap model call (every 30 s of show at most): claims code missed, kept only when
    found verbatim in the window, then flagged by code like the others. Skipped when AI is off."""
    from app.modules.checker import _parse
    from app.modules.quotes import locate

    async with SessionLocal() as db:
        show = await db.get(Show, show_id, with_for_update=True)
        if show is None or show.language != "fr":
            return
        ws = await db.get(Workspace, show.workspace_id)
        if not _ai_enabled(ws):
            return
        settings = dict(show.settings or {})
        since = float(settings.get("model_until_s") or 0.0)
        window = [g for g in show.segments or [] if g["start"] >= since]
        if not window or window[-1]["end"] - since < MODEL_EVERY_S:
            return
        settings["model_until_s"] = window[-1]["end"]
        show.settings = settings
        await db.commit()
        known = {_norm(c.text) for c in await _claims(db, show.id)}
    lines = " ".join(g["text"] for g in window)[:4000]
    try:
        reply = await ai.complete(
            [
                {"role": "system", "content": EXTRACT_SYSTEM},
                {"role": "user", "content": lines},
            ],
            workspace_id=ws.id,
            temperature=0,
            max_tokens=400,
            response_format={"type": "json_object"},
        )
        raw = _parse(reply.content)
    except (ai.AiUnavailable, ValueError) as e:
        log.info("studio model call skipped: %s", e)
        return
    made = []
    async with SessionLocal() as db:
        show = await db.get(Show, show_id)
        for entry in (raw.get("claims") or [])[:3]:
            text = str((entry or {}).get("text") or "").strip().strip('«»"').strip()
            if len(text) < MIN_CLAIM_CHARS or _norm(text) in known:
                continue
            if any(_norm(text) in k or k in _norm(text) for k in known):
                continue
            start = locate(text, window)
            if start is None:  # not said verbatim: dropped
                continue
            made.append(
                await add_claim(
                    db, show, text, start, origin="model", spotted={"model": reply.model}
                )
            )
            known.add(_norm(text))
        await db.commit()
        for c in made:
            await emit(show.id, "studio.claim", claim_out(c, show).model_dump(mode="json"))


# --- routes: shows -----------------------------------------------------------------------------


@router.get("/workspaces/{ws}/studio")
async def list_shows(member: AnyMember, db: Db) -> list[ShowBrief]:
    shows = (
        await db.scalars(
            select(Show)
            .where(Show.workspace_id == member.workspace_id)
            .order_by(Show.created_at.desc())
            .limit(100)
        )
    ).all()
    out = []
    for show in shows:
        out.append(brief(show, await _claims(db, show.id)))
    return out


@router.post("/workspaces/{ws}/studio", status_code=201)
async def create_show(body: ShowIn, member: AnyMember, db: Db) -> ShowOut:
    if len({s.id for s in body.speakers}) != len(body.speakers):
        raise ApiError(422, "duplicate_speaker", "Speaker ids must be unique")
    show = Show(
        workspace_id=member.workspace_id,
        created_by=member.user.id,
        title=body.title.strip(),
        topics=[t.strip() for t in body.topics if t.strip()],
        language=body.language,
        status="draft",
        settings={
            "station": (body.station or "").strip() or None,
            "input": body.input,
            "mode": "prudent",
            "speakers": [s.model_dump() for s in body.speakers],
            "turns": [],
        },
        segments=[],
        chunks=[],
    )
    db.add(show)
    await db.flush()
    await record(db, member.workspace_id, member.user.id, "show", show.id, "create")
    await db.commit()
    await db.refresh(show)
    return await show_out(db, show)


@router.get("/workspaces/{ws}/studio/{show_id}")
async def get_show(show_id: uuid.UUID, member: AnyMember, db: Db) -> ShowOut:
    return await show_out(db, await _get_show(db, member, show_id))


@router.patch("/workspaces/{ws}/studio/{show_id}")
async def update_show(show_id: uuid.UUID, body: ShowPatch, member: AnyMember, db: Db) -> ShowOut:
    show = await _get_show(db, member, show_id)
    settings = dict(show.settings or {})
    if body.title is not None:
        show.title = body.title.strip()
    if body.topics is not None:
        show.topics = [t.strip() for t in body.topics if t.strip()]
    if body.station is not None:
        settings["station"] = body.station.strip() or None
    if body.input is not None:
        settings["input"] = body.input
    if body.speakers is not None:
        if len({s.id for s in body.speakers}) != len(body.speakers):
            raise ApiError(422, "duplicate_speaker", "Speaker ids must be unique")
        settings["speakers"] = [s.model_dump() for s in body.speakers]
    show.settings = settings
    await db.commit()
    await db.refresh(show)
    out = await show_out(db, show)
    await emit(show.id, "studio.show", out.model_dump(mode="json", exclude={"claim_list"}))
    return out


@router.delete("/workspaces/{ws}/studio/{show_id}", status_code=204)
async def delete_show(show_id: uuid.UUID, member: AnyMember, db: Db) -> None:
    show = await _get_show(db, member, show_id)
    keys = [c["key"] for c in show.chunks or [] if c.get("key")]
    await db.delete(show)
    await record(db, member.workspace_id, member.user.id, "show", show_id, "delete")
    await db.commit()
    for key in keys:
        try:
            await storage.delete(key)
        except Exception:  # noqa: BLE001 - an orphan object is harmless
            log.warning("could not delete %s", key)


@router.post("/workspaces/{ws}/studio/{show_id}/start")
async def start_show(show_id: uuid.UUID, member: AnyMember, db: Db) -> ShowOut:
    show = await _get_show(db, member, show_id)
    if show.status == "ended":
        raise ApiError(409, "show_ended", "This show has ended")
    if show.status == "draft":
        show.status = "live"
        show.started_at = datetime.now(UTC)
        await record(db, member.workspace_id, member.user.id, "show", show.id, "start")
        await db.commit()
        await db.refresh(show)
    out = await show_out(db, show)
    await emit(show.id, "studio.show", out.model_dump(mode="json", exclude={"claim_list"}))
    return out


@router.post("/workspaces/{ws}/studio/{show_id}/end")
async def end_show(show_id: uuid.UUID, member: AnyMember, db: Db) -> ShowOut:
    show = await _get_show(db, member, show_id)
    if show.status != "ended":
        show.status = "ended"
        show.ended_at = datetime.now(UTC)
        show.started_at = show.started_at or show.ended_at
        await record(db, member.workspace_id, member.user.id, "show", show.id, "end")
        await db.commit()
        await db.refresh(show)
    out = await show_out(db, show)
    await emit(show.id, "studio.show", out.model_dump(mode="json", exclude={"claim_list"}))
    return out


@router.post("/workspaces/{ws}/studio/{show_id}/speaker")
async def set_speaker(show_id: uuid.UUID, body: SpeakerIn, member: AnyMember, db: Db) -> ShowOut:
    """Mode débat: the producer marks who speaks from now on (None: nobody in particular)."""
    show = await db.get(Show, show_id, with_for_update=True)
    if show is None or show.workspace_id != member.workspace_id:
        raise ApiError(404, "not_found", "Show not found")
    settings = dict(show.settings or {})
    ids = {s["id"] for s in settings.get("speakers") or []}
    if body.speaker_id is not None and body.speaker_id not in ids:
        raise ApiError(422, "unknown_speaker", "Unknown speaker")
    at = body.at_s if body.at_s is not None else show_time(show)
    settings["turns"] = [
        *(settings.get("turns") or []),
        {"at_s": round(at, 2), "speaker_id": body.speaker_id},
    ][-500:]
    settings["current_speaker_id"] = body.speaker_id
    show.settings = settings
    await db.commit()
    await db.refresh(show)
    await emit(show.id, "studio.speaker", {"speaker_id": body.speaker_id, "at_s": at})
    return await show_out(db, show)


# --- routes: before the show (preload) ---------------------------------------------------------


def _about(topics: list[str], *texts: str) -> bool:
    if not topics:
        return True
    asked = set().union(*(words(t) for t in topics))
    return bool(asked & words(" ".join(t for t in texts if t)))


@router.get("/workspaces/{ws}/studio/{show_id}/pack")
async def pack(show_id: uuid.UUID, member: AnyMember, db: Db) -> dict[str, Any]:
    """What the browser keeps for the show (memory + IndexedDB): signed verdicts, official figures
    and registered originals on its topics, so a weak connection does not stop the producer."""
    from app.modules import figures, registry

    show = await _get_show(db, member, show_id)
    topics = list(show.topics or [])
    rows = (
        await db.execute(
            select(Item, Workspace)
            .join(Workspace, Workspace.id == Item.workspace_id)
            .where(
                or_(Item.workspace_id == member.workspace_id, Workspace.is_public.is_(True)),
                Item.type == "claim",
                Item.status == "published",
                Item.data["verdict"].astext.in_(["true", "misleading", "false", "unverifiable"]),
            )
            .order_by(Item.updated_at.desc())
            .limit(400)
        )
    ).all()
    verdicts = [
        {
            "id": str(i.id),
            "ref": (i.data or {}).get("ref"),
            "title": i.title,
            "verdict": (i.data or {}).get("verdict"),
            "reason": (i.data or {}).get("reason"),
            "newsroom": w.name,
            "own": i.workspace_id == member.workspace_id,
            "tags": i.tags or [],
            "date": i.updated_at.date().isoformat(),
        }
        for i, w in rows
        if not topics or set(i.tags or []) & set(topics) or _about(topics, i.title, i.body)
    ][:150]
    figs = (
        await db.scalars(
            select(Figure)
            .where(or_(Figure.workspace_id == member.workspace_id, Figure.workspace_id.is_(None)))
            .limit(500)
        )
    ).all()
    figure_rows = [
        figures.figure_brief(f) | {"keywords": f.keywords or []}
        for f in figs
        if not topics or f.topic in topics or _about(topics, f.label, " ".join(f.keywords or []))
    ][:200]
    # Originals linked to the chosen figures come with them; then the newest of the registry.
    linked = {f.communique_id for f in figs if f.communique_id}
    cutoff = (dates.today() - timedelta(days=180)).isoformat()
    originals = (
        await db.execute(
            registry._visible(member.workspace_id)
            .where(Communique.status == "original")
            .order_by(Communique.created_at.desc())
            .limit(300)
        )
    ).all()
    registry_rows = [
        {
            "id": str(c.id),
            "issuer": c.issuer,
            "number": c.number,
            "issued_on": c.issued_on,
            "title": c.title,
            "text": (c.text or "")[:1500],
            "newsroom": w.name,
            "demo": c.is_demo,
        }
        for c, w in originals
        if c.id in linked
        or (c.issued_on or "") >= cutoff
        or _about(topics, c.title, c.text, c.issuer)
    ][:100]
    return {
        "show_id": str(show.id),
        "topics": topics,
        "prepared_at": datetime.now(UTC).isoformat(),
        "verdicts": verdicts,
        "figures": figure_rows,
        "registry": registry_rows,
    }


# --- routes: during the show -------------------------------------------------------------------


def _ext(mime: str) -> str:
    return {"audio/ogg": "ogg", "audio/mp4": "m4a", "audio/mpeg": "mp3", "audio/wav": "wav"}.get(
        mime, "webm"
    )


async def _store_chunk(show: Show, seq: int, mime: str, raw: bytes) -> str | None:
    if not storage.configured():
        return None
    key = f"ws/{show.workspace_id}/studio/{show.id}/{seq:05d}.{_ext(mime)}"
    try:
        await asyncio.to_thread(
            storage.client().put_object,
            Bucket=get_settings().storage_bucket,
            Key=key,
            Body=raw,
            ContentType=mime,
        )
    except Exception as e:  # noqa: BLE001 - the show goes on without its clip
        log.warning("chunk %s not stored: %s", key, e)
        return None
    return key


@router.post("/workspaces/{ws}/studio/{show_id}/chunk")
async def post_chunk(
    show_id: uuid.UUID,
    request: Request,
    member: AnyMember,
    db: Db,
    background: BackgroundTasks,
    seq: int = Query(ge=0, le=100_000),
    start_s: float = Query(ge=0),
    duration_s: float = Query(default=10.0, gt=0, le=60),
) -> dict[str, Any]:
    """One 8–10 s piece of the show's sound (raw `audio/*` body). Stored for the bilan's clips;
    French is transcribed and its claims flagged at once; Malagasy is kept, never transcribed."""
    show = await _get_show(db, member, show_id)
    if show.status != "live":
        raise ApiError(409, "show_not_live", "Start the show before sending its sound")
    mime = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    if not mime.startswith("audio/"):
        raise ApiError(415, "unsupported_type", "Send the chunk as an audio/* body")
    raw = await request.body()
    if not raw:
        raise ApiError(422, "empty_chunk", "The chunk is empty")
    if len(raw) > CHUNK_MAX_BYTES:
        raise ApiError(413, "too_large", "A chunk is limited to 3 MB")
    key = await _store_chunk(show, seq, mime, raw)

    segments: list[dict[str, Any]] = []
    error = None
    if show.language == "fr":
        from app.modules.public import VOCABULARY

        try:
            heard = await stt.transcribe(
                raw, f"studio-{seq:05d}.{_ext(mime)}", mime, language="fr", prompt=VOCABULARY
            )
            segments = [
                {
                    "start": round(start_s + g["start"], 2),
                    "end": round(start_s + g["end"], 2),
                    "text": g["text"],
                    "chunk": seq,
                }
                for g in heard["segments"]
                if g["text"].strip()
            ]
            if not segments and heard["text"]:
                segments = [
                    {
                        "start": round(start_s, 2),
                        "end": round(start_s + duration_s, 2),
                        "text": heard["text"],
                        "chunk": seq,
                    }
                ]
        except stt.SttUnavailable as e:
            log.info("studio chunk %s not transcribed: %s", seq, e)
            error = "stt_unavailable"

    # The show row is locked while its lists grow: two chunks may land at once.
    show = await db.get(Show, show_id, with_for_update=True, populate_existing=True)
    file_id = None
    if key:
        f = File(
            workspace_id=show.workspace_id,
            uploaded_by=member.user.id,
            storage_key=key,
            filename=f"{show.title[:80]} {seq:05d}.{_ext(mime)}",
            mime=mime,
            size_bytes=len(raw),
            status="ready",
            meta={"studio": str(show.id), "start_s": start_s, "duration_s": duration_s},
        )
        db.add(f)
        await db.flush()
        file_id = str(f.id)
    entry = {
        "seq": seq,
        "start_s": round(start_s, 2),
        "duration_s": round(duration_s, 2),
        "key": key,
        "file_id": file_id,
        "mime": mime,
        "size": len(raw),
        "transcribed": show.language == "fr" and error is None,
    }
    show.chunks = [*(c for c in show.chunks or [] if c["seq"] != seq), entry]
    if segments:
        show.segments = sorted([*(show.segments or []), *segments], key=lambda g: g["start"])
    claims = await spot_claims(db, show, segments)
    await db.commit()
    await db.refresh(show)

    from app.modules import veille

    text = " ".join(g["text"] for g in segments)
    watched = await veille.match_signals(db, show.workspace_id, text, "studio") if text else []
    out_claims = [claim_out(c, show).model_dump(mode="json") for c in claims]
    if segments:
        await emit(show.id, "studio.segments", {"segments": segments, "watched": watched})
    for c in out_claims:
        await emit(show.id, "studio.claim", c)
    if segments and show.language == "fr":
        background.add_task(model_claims, show.id)
    return {
        "seq": seq,
        "stored": key is not None,
        "transcribed": entry["transcribed"],
        "error": error,
        "segments": segments,
        "watched": watched,
        "claims": out_claims,
    }


@router.post("/workspaces/{ws}/studio/{show_id}/claims", status_code=201)
async def type_claim(show_id: uuid.UUID, body: ClaimIn, member: AnyMember, db: Db) -> ClaimOut:
    """What the producer heard, typed or dictated in one sentence (a Malagasy show, or a sentence
    the transcription missed). Flagged like the others."""
    show = await _get_show(db, member, show_id)
    if show.status == "draft":
        raise ApiError(409, "show_not_live", "Start the show first")
    ids = {s["id"] for s in (show.settings or {}).get("speakers") or []}
    if body.speaker_id is not None and body.speaker_id not in ids:
        raise ApiError(422, "unknown_speaker", "Unknown speaker")
    at = body.at_s if body.at_s is not None else show_time(show)
    claim = await add_claim(
        db,
        show,
        body.text,
        at,
        origin="typed",
        spotted={"typed_by": member.user.id, "language": show.language},
        speaker_id=body.speaker_id,
    )
    await db.commit()
    await db.refresh(claim)
    out = claim_out(claim, show)
    await emit(show.id, "studio.claim", out.model_dump(mode="json"))
    return out


@router.patch("/workspaces/{ws}/studio/{show_id}/claims/{claim_id}")
async def update_claim(
    show_id: uuid.UUID, claim_id: uuid.UUID, body: ClaimPatch, member: AnyMember, db: Db
) -> ClaimOut:
    """Mode débat: give a claim to another speaker (or to nobody)."""
    show = await _get_show(db, member, show_id)
    claim = await _get_claim(db, show, claim_id)
    ids = {s["id"] for s in (show.settings or {}).get("speakers") or []}
    if body.speaker_id is not None and body.speaker_id not in ids:
        raise ApiError(422, "unknown_speaker", "Unknown speaker")
    claim.speaker_id = body.speaker_id
    await db.commit()
    await db.refresh(claim)
    out = claim_out(claim, show)
    await emit(show.id, "studio.claim", out.model_dump(mode="json"))
    return out


@router.post("/workspaces/{ws}/studio/{show_id}/claims/{claim_id}/send")
async def send_claim(
    show_id: uuid.UUID, claim_id: uuid.UUID, body: SendIn, member: AnyMember, db: Db
) -> ClaimOut:
    """« Envoyer au présentateur »: Mode prudent, only the producer's gesture reaches the screen."""
    show = await _get_show(db, member, show_id)
    claim = await _get_claim(db, show, claim_id)
    claim.status = "sent"
    claim.question = body.question.strip() or None
    claim.sent_at = datetime.now(UTC)
    claim.decided_by = member.user.id
    await record(
        db,
        member.workspace_id,
        member.user.id,
        "show",
        show.id,
        "flag_sent",
        {"claim": str(claim.id)},
    )
    await db.commit()
    await db.refresh(claim)
    out = claim_out(claim, show)
    await emit(show.id, "studio.claim", out.model_dump(mode="json"))
    await emit(show.id, "studio.sent", out.model_dump(mode="json"))
    return out


@router.post("/workspaces/{ws}/studio/{show_id}/claims/{claim_id}/dismiss")
async def dismiss_claim(
    show_id: uuid.UUID, claim_id: uuid.UUID, member: AnyMember, db: Db
) -> ClaimOut:
    """« Écarter »: the flag stays in the bilan, never on the presenter's screen."""
    show = await _get_show(db, member, show_id)
    claim = await _get_claim(db, show, claim_id)
    was_sent = claim.status == "sent"
    claim.status = "dismissed"
    claim.decided_by = member.user.id
    await db.commit()
    await db.refresh(claim)
    out = claim_out(claim, show)
    await emit(show.id, "studio.claim", out.model_dump(mode="json"))
    if was_sent:
        await emit(show.id, "studio.sent", out.model_dump(mode="json"))
    return out


@router.get("/workspaces/{ws}/studio/{show_id}/presenter")
async def presenter(show_id: uuid.UUID, member: AnyMember, db: Db) -> dict[str, Any]:
    """The presenter's screen: the last three flags the producer sent, newest first."""
    show = await _get_show(db, member, show_id)
    rows = (
        await db.scalars(
            select(ShowClaim)
            .where(ShowClaim.show_id == show.id, ShowClaim.status == "sent")
            .order_by(ShowClaim.sent_at.desc())
            .limit(PRESENTER_FLAGS)
        )
    ).all()
    speakers = (show.settings or {}).get("speakers") or []
    return {
        "show": {"id": str(show.id), "title": show.title, "status": show.status},
        "speakers": speakers,
        "flags": [claim_out(c).model_dump(mode="json") for c in rows],
    }


# --- routes: after the show --------------------------------------------------------------------


@router.get("/workspaces/{ws}/studio/{show_id}/bilan")
async def bilan(show_id: uuid.UUID, member: AnyMember, db: Db) -> ShowOut:
    """« Bilan de l'émission »: every claim with its clip at the second, its evidence and flag."""
    return await show_out(db, await _get_show(db, member, show_id), presign=True)


def _clock(at_s: float) -> str:
    s = int(at_s)
    return (
        f"{s // 3600:d}:{s // 60 % 60:02d}:{s % 60:02d}"
        if s >= 3600
        else f"{s // 60:d}:{s % 60:02d}"
    )


def _excerpt(show: Show, at_s: float, end_s: float | None) -> str:
    near = [
        g for g in show.segments or [] if g["end"] >= at_s - 8 and g["start"] <= (end_s or at_s) + 8
    ]
    return "\n".join(f"[{_clock(g['start'])}] {g['text']}" for g in near)


@router.post("/workspaces/{ws}/studio/{show_id}/claims/{claim_id}/follow", status_code=201)
async def follow(show_id: uuid.UUID, claim_id: uuid.UUID, member: AnyMember, db: Db) -> FollowOut:
    """« Suivre dans le desk »: a dossier through the ordinary item route, the clip as its first
    source, and a radio stop on Le trajet."""
    from app.modules import items, sources, trajet
    from app.modules.public import _next_ref

    show = await _get_show(db, member, show_id)
    claim = await _get_claim(db, show, claim_id)
    if claim.item_id is not None and await db.get(Item, claim.item_id) is not None:
        raise ApiError(409, "already_followed", "This claim is already followed in the desk")
    settings = show.settings or {}
    station = settings.get("station") or show.title
    heard_at = (show.started_at or show.created_at) + timedelta(seconds=claim.at_s)
    speaker = next(
        (s["name"] for s in settings.get("speakers") or [] if s["id"] == claim.speaker_id), None
    )
    ref = await _next_ref(db, member.workspace_id)
    who = f", {speaker}" if speaker else ""
    body = f"Entendu dans « {show.title} » ({station}) à {_clock(claim.at_s)}{who}."
    # A trusted server flow: the reference was allocated above, so the guarded route is bypassed.
    made = await items._create_item(
        items.ItemIn(
            title=claim.text[:300],
            body=body,
            tags=[t for t in show.topics or []][:6],
            data={
                "ref": ref,
                "first_seen_at": heard_at.isoformat(),
                "origin": "radio",
                "source_count": 0,
                "studio": {
                    "show_id": str(show.id),
                    "claim_id": str(claim.id),
                    "at_s": claim.at_s,
                    "flag": (claim.flag or {}).get("kind"),
                },
                **({"demo": True} if show.is_demo else {}),
            },
        ),
        member,
        db,
    )
    chunk = chunk_at(show, claim.at_s)
    excerpt = _excerpt(show, claim.at_s, claim.end_s)
    said = claim.text if show.language == "mg" or not excerpt else excerpt
    title = f"Studio · {show.title} · {_clock(claim.at_s)}"[:500]
    day = heard_at.astimezone(dates.EAT).date().isoformat()
    if chunk and chunk.get("file_id"):
        source = Source(
            workspace_id=member.workspace_id,
            item_id=made.id,
            file_id=uuid.UUID(chunk["file_id"]),
            created_by=member.user.id,
            kind="audio",
            status="ready",  # never re-transcribed: a Malagasy clip keeps the producer's sentence
            title=title,
            text=said,
            published_at=day,
        )
    else:
        source = Source(
            workspace_id=member.workspace_id,
            item_id=made.id,
            created_by=member.user.id,
            kind="text",
            status="ready",
            title=title,
            text=said,
            published_at=day,
        )
    db.add(source)
    await db.flush()
    await sources._created(db, member, source)
    offset = round(claim.at_s - chunk["start_s"], 2) if chunk else None
    await trajet.add_stop(
        db,
        member.workspace_id,
        made.id,
        side="rumour",
        channel="radio",
        place=station,
        proof={
            "source_id": str(source.id),
            "clip_at_s": offset,
            "show_id": str(show.id),
            "show_at_s": claim.at_s,
        },
        added_by=member.user.id,
        at=heard_at,
    )
    claim = await db.get(ShowClaim, claim_id)
    claim.item_id = made.id
    await db.commit()
    await db.refresh(claim)
    out = claim_out(claim, show)
    out.ref = ref
    await emit(show.id, "studio.claim", out.model_dump(mode="json"))
    return FollowOut(item_id=made.id, ref=ref, source_id=source.id)


# --- demo --------------------------------------------------------------------------------------

DEMO_TITLE = "Le Grand Débat du soir (démo)"
DEMO_STATION = "Radio Fanalana (démo)"
DEMO_SPEAKERS = [
    {"id": "a", "name": "Intervenant A (démo)", "camp": None},
    {"id": "b", "name": "Intervenante B (démo)", "camp": None},
]
# Fictional segments: (start, end, speaker, text). Three carry a checkable claim.
DEMO_SEGMENTS = [
    (0.0, 9.0, None, "Bonsoir et bienvenue, ce soir nous parlons de l'électricité à Antananarivo."),
    (
        9.0,
        21.0,
        "a",
        "Selon la JIRAMA, le délestage sera de 4 heures par jour dans chaque quartier.",
    ),
    (21.0, 30.0, None, "Merci. Votre réponse, madame ?"),
    (30.0, 41.0, "b", "Moi je vous dis que le tarif va augmenter de 40 % en décembre."),
    (41.0, 52.0, "b", "Les gens n'en peuvent plus, il faut que cela change."),
    (52.0, 64.0, "a", "Nous avons raccordé 3 000 ménages au réseau cette année."),
    (64.0, 75.0, None, "Nous marquons une courte pause, restez avec nous."),
]
DEMO_SECONDS = 80


def demo_audio(seconds: int = DEMO_SECONDS, rate: int = 8000) -> bytes:
    """A quiet two-tone placeholder (WAV, 8 kHz, 8-bit): the demo show has no real voice."""
    frames = bytearray()
    for i in range(seconds * rate):
        t = i / rate
        tone = 440.0 if int(t) % 4 < 2 else 330.0
        frames.append(128 + int(24 * math.sin(2 * math.pi * tone * t)))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(1)
        w.setframerate(rate)
        w.writeframes(bytes(frames))
    return buf.getvalue()


async def seed_demo(db: AsyncSession, workspace_id, user_id, items: dict[str, Item]) -> None:
    """« Le Grand Débat du soir (démo) »: an ended show with two fictional speakers, its seeded
    segments and three flags computed by code (one consistent with the JIRAMA figure 4 h/jour, one
    contradicted by the official +12 %, one with no source found)."""
    old = (
        await db.scalars(
            select(Show).where(Show.workspace_id == workspace_id, Show.is_demo.is_(True))
        )
    ).all()
    for s in old:
        for c in s.chunks or []:
            if c.get("file_id"):
                await db.execute(delete(File).where(File.id == uuid.UUID(c["file_id"])))
        await db.delete(s)
    await db.flush()
    ended = dates.now() - timedelta(hours=2)
    started = ended - timedelta(seconds=DEMO_SECONDS)
    show = Show(
        workspace_id=workspace_id,
        created_by=user_id,
        title=DEMO_TITLE,
        topics=["énergie", "économie"],
        language="fr",
        status="ended",
        started_at=started,
        ended_at=ended,
        settings={
            "station": DEMO_STATION,
            "input": "stream",
            "mode": "prudent",
            "speakers": DEMO_SPEAKERS,
            "turns": [
                {"at_s": 0.0, "speaker_id": None},
                {"at_s": 9.0, "speaker_id": "a"},
                {"at_s": 21.0, "speaker_id": None},
                {"at_s": 30.0, "speaker_id": "b"},
                {"at_s": 52.0, "speaker_id": "a"},
                {"at_s": 64.0, "speaker_id": None},
            ],
            "model_until_s": float(DEMO_SECONDS),
        },
        segments=[
            {"start": a, "end": b, "text": text, "chunk": 0} for a, b, _, text in DEMO_SEGMENTS
        ],
        chunks=[],
        is_demo=True,
    )
    db.add(show)
    await db.flush()
    if storage.configured():
        raw = demo_audio()
        key = await _store_chunk(show, 0, "audio/wav", raw)
        if key:
            f = File(
                workspace_id=workspace_id,
                uploaded_by=user_id,
                storage_key=key,
                filename="Le Grand Débat du soir (démo, exemple fictif).wav",
                mime="audio/wav",
                size_bytes=len(raw),
                status="ready",
                meta={"studio": str(show.id), "demo": True},
            )
            db.add(f)
            await db.flush()
            show.chunks = [
                {
                    "seq": 0,
                    "start_s": 0.0,
                    "duration_s": float(DEMO_SECONDS),
                    "key": key,
                    "file_id": str(f.id),
                    "mime": "audio/wav",
                    "size": len(raw),
                    "transcribed": True,
                }
            ]
    segments = [{"start": a, "end": b, "text": text} for a, b, _, text in DEMO_SEGMENTS]
    made = await spot_claims(db, show, segments)
    for c in made:
        if c.flag.get("kind") == "contradicted":
            c.status, c.sent_at, c.decided_by = (
                "sent",
                started + timedelta(seconds=c.at_s + 6),
                user_id,
            )
            c.question = "Le chiffre officiel est de +12 %. D'où vient votre chiffre de 40 % ?"
        elif c.flag.get("kind") == "consistent":
            c.status, c.sent_at, c.decided_by = (
                "sent",
                started + timedelta(seconds=c.at_s + 5),
                user_id,
            )
            c.question = "Ce chiffre est celui du communiqué : à partir de quand s'applique-t-il ?"
    await db.flush()
