"""Public features, no account: the archive of published verdicts, "is it already checked?", tips and
their follow-up. Only newsrooms that opted in (`workspace.is_public`) are visible, and only claims a
journalist confirmed and moved to `published` leave the newsroom."""

import hashlib
import re
import secrets
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime
from typing import Literal

import httpx
from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy import func, select

from app.core import ai, keys, stt
from app.core.access import Db
from app.core.activity import broadcast, record
from app.core.config import get_settings
from app.core.errors import ApiError
from app.core.models import Item, Source, Workspace
from app.core.words import words

router = APIRouter(prefix="/public", tags=["public"])

PUBLIC_AUTHOR = "public"  # author_id of a tip; not a Better Auth user
Origin = Literal["facebook", "whatsapp", "tiktok", "radio", "press", "other"]


class NewsroomOut(BaseModel):
    slug: str
    name: str


class VerdictOut(BaseModel):
    id: uuid.UUID
    ref: str | None
    title: str
    verdict: str
    reason: str | None
    post: str | None
    sources: list[str]
    origin: str | None
    first_seen_at: str | None
    published_at: datetime
    newsroom: NewsroomOut


class VerdictPage(BaseModel):
    items: list[VerdictOut]
    total: int


class MatchIn(BaseModel):
    text: str = Field(min_length=3, max_length=4000)


class MatchOut(BaseModel):
    score: float
    verdict: VerdictOut


class TipIn(BaseModel):
    newsroom: str = Field(min_length=1, max_length=140)
    text: str = Field(min_length=5, max_length=4000)
    url: HttpUrl | None = None
    origin: Origin = "other"


class TipOut(BaseModel):
    token: str
    ref: str


class TipStatusOut(BaseModel):
    ref: str | None
    title: str
    status: str
    received_at: datetime
    newsroom: NewsroomOut
    verdict: VerdictOut | None


# --- a small per-address limit on tips, enough for a public form without accounts
_TIPS: dict[str, deque[float]] = defaultdict(deque)
TIP_LIMIT, TIP_WINDOW = 5, 600.0


def _allow_tip(addr: str) -> bool:
    now, q = time.monotonic(), _TIPS[addr]
    while q and now - q[0] > TIP_WINDOW:
        q.popleft()
    if len(q) >= TIP_LIMIT:
        return False
    q.append(now)
    return True


def _published():
    return (
        select(Item, Workspace)
        .join(Workspace, Workspace.id == Item.workspace_id)
        .where(
            Workspace.is_public.is_(True),
            Item.type == "claim",
            Item.status == "published",
            Item.data["verdict"].astext.in_(["true", "misleading", "false", "unverifiable"]),
        )
    )


async def _verdict(db: Db, item: Item, ws: Workspace) -> VerdictOut:
    d = item.data or {}
    titles = (await db.scalars(select(Source.title).where(Source.item_id == item.id))).all()
    posts = d.get("posts") or {}
    post = posts.get("fr") if isinstance(posts, dict) else None
    analysis = d.get("analysis") if isinstance(d.get("analysis"), dict) else {}
    return VerdictOut(
        id=item.id,
        ref=d.get("ref"),
        title=item.title,
        verdict=d["verdict"],
        reason=d.get("reason") or analysis.get("reason"),
        post=post.get("text") if isinstance(post, dict) else post,
        sources=[t for t in titles if t],
        origin=d.get("origin"),
        first_seen_at=d.get("first_seen_at"),
        published_at=item.updated_at,
        newsroom=NewsroomOut(slug=ws.slug, name=ws.name),
    )


@router.get("/newsrooms")
async def newsrooms(db: Db) -> list[NewsroomOut]:
    rows = await db.scalars(
        select(Workspace).where(Workspace.is_public.is_(True)).order_by(Workspace.name)
    )
    return [NewsroomOut(slug=w.slug, name=w.name) for w in rows]


@router.get("/verdicts")
async def list_verdicts(
    db: Db, q: str | None = None, newsroom: str | None = None, limit: int = 20, offset: int = 0
) -> VerdictPage:
    query = _published()
    if newsroom:
        query = query.where(Workspace.slug == newsroom)
    if q:
        like = f"%{q.strip()}%"
        query = query.where(Item.title.ilike(like) | Item.body.ilike(like))
    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    rows = (
        await db.execute(
            query.order_by(Item.updated_at.desc()).limit(min(limit, 50)).offset(offset)
        )
    ).all()
    return VerdictPage(items=[await _verdict(db, i, w) for i, w in rows], total=total or 0)


@router.get("/verdicts/{item_id}")
async def get_verdict(item_id: uuid.UUID, db: Db) -> VerdictOut:
    row = (await db.execute(_published().where(Item.id == item_id))).first()
    if row is None:
        raise ApiError(404, "not_found", "Verdict not found")
    return await _verdict(db, *row)


# --- "is it already checked?": word overlap on accent-free text (no AI verdict is ever made here)
@router.post("/match")
async def match(body: MatchIn, db: Db) -> list[MatchOut]:
    asked = words(body.text)
    if not asked:
        return []
    scored = []
    for item, ws in (await db.execute(_published().limit(500))).all():
        known = words(f"{item.title} {item.body}")
        if not known:
            continue
        score = len(asked & known) / min(len(asked), len(known))
        if score >= 0.4:
            scored.append((score, item, ws))
    scored.sort(key=lambda r: r[0], reverse=True)
    return [MatchOut(score=round(s, 2), verdict=await _verdict(db, i, w)) for s, i, w in scored[:3]]


async def _next_ref(db: Db, ws: uuid.UUID) -> str:
    refs = await db.scalars(select(Item.data["ref"].astext).where(Item.workspace_id == ws))
    nums = [int(m.group(1)) for r in refs if r and (m := re.match(r"FAN-(\d+)$", r))]
    return f"FAN-{(max(nums) + 1) if nums else 1:04d}"


@router.post("/tips", status_code=201)
async def create_tip(body: TipIn, request: Request, db: Db) -> TipOut:
    if not _allow_tip(request.client.host if request.client else "unknown"):
        raise ApiError(429, "too_many_tips", "Too many tips, try again in a few minutes")
    ws = await db.scalar(
        select(Workspace).where(Workspace.slug == body.newsroom, Workspace.is_public.is_(True))
    )
    if ws is None:
        raise ApiError(404, "not_found", "Newsroom not found")
    text = body.text.strip()
    token = secrets.token_urlsafe(18)
    ref = await _next_ref(db, ws.id)
    item = Item(
        workspace_id=ws.id,
        author_id=PUBLIC_AUTHOR,
        type="claim",
        title=text.splitlines()[0][:300],
        body="\n\n".join(p for p in [text, str(body.url) if body.url else ""] if p),
        status="to_check",
        tags=["signalement"],
        data={
            "ref": ref,
            "first_seen_at": datetime.now().astimezone().isoformat(),
            "origin": body.origin,
            "source_count": 0,
            "public_tip": True,
            "tip_token": token,
            "tip_url": str(body.url) if body.url else None,
        },
    )
    db.add(item)
    await db.flush()
    await record(db, ws.id, PUBLIC_AUTHOR, "item", item.id, "create")
    await db.commit()
    await db.refresh(item)
    from app.modules.items import _out  # the desk's live grid shows the tip at once

    await broadcast(ws.id, "item.created", _out(item))
    return TipOut(token=token, ref=ref)


@router.get("/tips/{token}")
async def tip_status(token: str, db: Db) -> TipStatusOut:
    row = (
        await db.execute(
            select(Item, Workspace)
            .join(Workspace, Workspace.id == Item.workspace_id)
            .where(Item.data["tip_token"].astext == token, Workspace.is_public.is_(True))
        )
    ).first()
    if row is None:
        raise ApiError(404, "not_found", "Tip not found")
    item, ws = row
    published = item.status == "published" and (item.data or {}).get("verdict")
    return TipStatusOut(
        ref=(item.data or {}).get("ref"),
        title=item.title,
        status=item.status,
        received_at=item.created_at,
        newsroom=NewsroomOut(slug=ws.slug, name=ws.name),
        verdict=await _verdict(db, item, ws) if published else None,
    )


# --- the public assistant: answers only from published, journalist-confirmed verdicts, with citations
ASK_SYSTEM = (
    "Tu es l'assistant public de FANILO, un outil de vérification des rédactions de Madagascar. "
    "Tu réponds UNIQUEMENT à partir des dossiers numérotés fournis : ce sont des verdicts confirmés et "
    "publiés par des journalistes. Cite chaque dossier utilisé sous la forme [n]. Si aucun dossier ne "
    "répond à la question, dis clairement que cette information n'a pas encore été vérifiée par une "
    "rédaction et invite à la signaler. N'invente jamais de verdict, de fait ni de source. Réponds en "
    "deux à quatre phrases, dans la langue de la question (français ou malagasy)."
)
_ASKS: dict[str, deque[float]] = defaultdict(deque)
ASK_LIMIT, ASK_WINDOW = 10, 600.0


class AskIn(BaseModel):
    question: str = Field(min_length=3, max_length=600)


class AskOut(BaseModel):
    answer: str | None
    verdicts: list[VerdictOut]
    checked: bool  # False: nothing published matches, the visitor is invited to send a tip


def _allow(store: dict[str, deque[float]], addr: str, limit: int, window: float) -> bool:
    now, q = time.monotonic(), store[addr]
    while q and now - q[0] > window:
        q.popleft()
    if len(q) >= limit:
        return False
    q.append(now)
    return True


async def find_published(db: Db, text: str, k: int = 5) -> list[VerdictOut]:
    """Published verdicts sharing enough words with the text (accent-free), best first."""
    asked = words(text)
    scored = []
    for item, ws in (await db.execute(_published().limit(500))).all():
        known = words(f"{item.title} {item.body} {(item.data or {}).get('reason', '')}")
        if asked and known and (hit := len(asked & known)):
            scored.append((hit / len(asked), item, ws))
    scored.sort(key=lambda r: r[0], reverse=True)
    return [await _verdict(db, i, w) for s, i, w in scored[:k] if s >= 0.2]


@router.post("/ask")
async def ask(body: AskIn, request: Request, db: Db) -> AskOut:
    if not _allow(
        _ASKS, request.client.host if request.client else "unknown", ASK_LIMIT, ASK_WINDOW
    ):
        raise ApiError(429, "too_many_questions", "Too many questions, try again in a few minutes")
    files = await find_published(db, body.question)
    if not files:  # nothing published to answer from: no AI call, no invented answer
        return AskOut(answer=None, verdicts=[], checked=False)
    label = {
        "true": "Vrai",
        "misleading": "Trompeur",
        "false": "Faux",
        "unverifiable": "Invérifiable",
    }
    context = "\n\n".join(
        f"[{n}] {v.ref} · {v.newsroom.name} · verdict : {label[v.verdict]}\n"
        f"Affirmation : {v.title}\nRaison : {v.reason or '—'}\nSources : {', '.join(v.sources) or '—'}"
        for n, v in enumerate(files, 1)
    )
    try:
        out = await ai.complete(
            [
                {"role": "system", "content": ASK_SYSTEM},
                {
                    "role": "user",
                    "content": f"Dossiers :\n\n{context}\n\nQuestion : {body.question}",
                },
            ],
            temperature=0.1,
            max_tokens=400,
        )
        answer = out.content.strip()
    except ai.AiUnavailable:
        answer = None  # the matching files still show; the page says the assistant is busy
    return AskOut(answer=answer, verdicts=files, checked=True)


# --- dictation: a short voice recording becomes text (Groq Whisper, French or Malagasy); nothing is kept
_VOICE: dict[str, deque[float]] = defaultdict(deque)
VOICE_LIMIT, VOICE_WINDOW, VOICE_MAX_BYTES = 20, 600.0, 3_000_000
VOCABULARY = (
    "Madagascar, Antananarivo, Tana, Analakely, Mahamasina, Anosy, Andohalo, Ambohijatovo, Isotry, "
    "Toamasina, Mahajanga, Fianarantsoa, Toliara, Antsiranana, Ambositra, Rova, JIRAMA, ariary, vary gasy, "
    "fokontany, taxi-be, WhatsApp, Facebook, TikTok, FANILO."
)


class DictationOut(BaseModel):
    text: str
    language: str | None


@router.post("/transcribe")
async def transcribe_voice(
    request: Request, lang: Literal["fr", "mg"] | None = None
) -> DictationOut:
    if not _allow(
        _VOICE, request.client.host if request.client else "unknown", VOICE_LIMIT, VOICE_WINDOW
    ):
        raise ApiError(
            429, "too_many_recordings", "Too many recordings, try again in a few minutes"
        )
    mime = (request.headers.get("content-type") or "").split(";")[0].strip()
    if not mime.startswith("audio/"):
        raise ApiError(415, "unsupported_media", "Send the recording as audio/*")
    raw = await request.body()
    if not raw or len(raw) > VOICE_MAX_BYTES:
        raise ApiError(413, "too_large", "Recordings are limited to about one minute")
    ext = {
        "audio/webm": "webm",
        "audio/ogg": "ogg",
        "audio/mp4": "m4a",
        "audio/mpeg": "mp3",
        "audio/wav": "wav",
    }.get(mime, "webm")
    try:
        out = await stt.transcribe(raw, f"dictation.{ext}", mime, language=lang, prompt=VOCABULARY)
    except stt.SttUnavailable as e:
        raise ApiError(503, "stt_unavailable", "Dictation is unavailable right now") from e
    return DictationOut(text=out["text"], language=out.get("language"))


# --- the assistant's voice (ElevenLabs when a key is set; otherwise the browser reads the answer)
_SPEAKS: dict[str, deque[float]] = defaultdict(deque)
SPEAK_LIMIT, SPEAK_WINDOW = 20, 600.0
_AUDIO: dict[
    str, bytes
] = {}  # recent answers already spoken: the same answer costs no credits twice
_AUDIO_MAX = 64
TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice}"
_tts_transport: httpx.AsyncBaseTransport | None = None  # tests swap in a mock


class SpeakIn(BaseModel):
    text: str = Field(min_length=1, max_length=900)
    lang: Literal["fr", "mg"] = "fr"


async def _tts(text: str, lang: str) -> bytes:
    """ElevenLabs over its keys in turn: a used-up (401/402) or busy (429) key gives way to the next."""
    s = get_settings()
    status = 0
    for api_key in keys.rotation("elevenlabs", keys.split(s.elevenlabs_api_key)):
        try:
            async with httpx.AsyncClient(transport=_tts_transport, timeout=30) as http:
                r = await http.post(
                    TTS_URL.format(voice=s.elevenlabs_voice_id),
                    params={"output_format": "mp3_44100_64"},
                    headers={"xi-api-key": api_key, "accept": "audio/mpeg"},
                    json={"text": text, "model_id": s.elevenlabs_model_mg, "language_code": None}
                    if lang == "mg"
                    else {"text": text, "model_id": s.elevenlabs_model, "language_code": "fr"},
                )
        except httpx.HTTPError:
            keys.set_aside("elevenlabs", api_key, s.ai_cooldown)
            continue
        if r.status_code == 200:
            return r.content
        status = r.status_code
        if status in (401, 402, 429):
            # a key out of credits stays aside for an hour; a busy one for the usual cooldown
            wait = 3600.0 if status in (401, 402) else keys.retry_after(r.headers, s.ai_cooldown)
            keys.set_aside("elevenlabs", api_key, wait)
            continue
        break
    suffix = f" ({status})" if status else ""
    raise ApiError(503, "tts_unavailable", f"The voice is unavailable right now{suffix}")


@router.post("/speak", response_class=Response, responses={200: {"content": {"audio/mpeg": {}}}})
async def speak(body: SpeakIn, request: Request) -> Response:
    s = get_settings()
    if not keys.split(s.elevenlabs_api_key):
        raise ApiError(501, "tts_not_configured", "No voice configured; the browser reads instead")
    text = re.sub(r"\[\d+\]|【[^】]*】|\*\*", "", body.text)
    text = re.sub(r"\s+([.,;:!?])", r"\1", re.sub(r"\s+", " ", text)).strip()
    key = hashlib.sha256(f"{s.elevenlabs_voice_id}|{body.lang}|{text}".encode()).hexdigest()
    if key not in _AUDIO:
        if not _allow(
            _SPEAKS, request.client.host if request.client else "unknown", SPEAK_LIMIT, SPEAK_WINDOW
        ):
            raise ApiError(
                429, "too_many_voices", "Too many spoken answers, try again in a few minutes"
            )
        audio = await _tts(text, body.lang)
        if len(_AUDIO) >= _AUDIO_MAX:
            _AUDIO.pop(next(iter(_AUDIO)))
        _AUDIO[key] = audio
    return Response(
        _AUDIO[key], media_type="audio/mpeg", headers={"Cache-Control": "private, max-age=3600"}
    )
