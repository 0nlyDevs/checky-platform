"""F3 interview to quotes: pick the key quotes and checkable claims out of a transcript.

`POST …/sources/{id}/quotes` queues `extract_quotes`; the result lands in
`transcript.highlights` ({quotes, claims, model, at}) and a `source.updated` event goes out.
Every quote must be found in the transcript, and takes the timestamp of the segment it starts in.
"""

import re
import unicodedata
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter
from sqlalchemy import select

from app.core import ai
from app.core.access import AnyMember, Db
from app.core.db import SessionLocal
from app.core.errors import ApiError
from app.core.models import Source, Transcript
from app.modules.checker import _parse
from app.workers.queue import JobContext, enqueue, handler, job_payload

router = APIRouter(tags=["quotes"])

MAX_TRANSCRIPT_CHARS = 30_000

SYSTEM = """Tu aides un journaliste à exploiter un entretien enregistré (français ou malgache).
À partir de la transcription horodatée, relève :
- "quotes" : les 3 à 8 citations les plus fortes, recopiées MOT POUR MOT depuis la transcription ;
- "claims" : les affirmations vérifiables (chiffres, faits, dates, accusations), reformulées en une phrase \
claire, avec le passage exact de la transcription dont elles viennent ("from").
Ne recopie jamais l'horodatage dans le texte. Réponds avec un seul objet JSON :
{"quotes": [{"text": "…"}], "claims": [{"text": "…", "from": "…"}]}"""


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).lower().replace("’", "'")
    return re.sub(r"[^\w']+", " ", s).strip()


def locate(passage: str, segments: list[dict[str, Any]]) -> float | None:
    """Start time of the segment where `passage` begins, or None if it is not in the transcript."""
    target = _norm(passage)
    if not target:
        return None
    full, starts = "", []
    for g in segments:
        starts.append((len(full), g["start"]))
        full += _norm(g["text"]) + " "
    at = full.find(target)
    if at < 0:
        return None
    start = segments[0]["start"]
    for offset, t in starts:
        if offset <= at:
            start = t
    return start


@handler("extract_quotes")
async def extract_quotes(ctx: JobContext) -> dict[str, Any]:
    source_id = uuid.UUID(ctx.input["source_id"])
    async with SessionLocal() as db:
        tr = await db.scalar(select(Transcript).where(Transcript.source_id == source_id))
        if tr is None or not tr.segments:
            raise ValueError("No transcript to read")
        segments = tr.segments
    lines = "\n".join(f"[{g['start']:.0f}s] {g['text']}" for g in segments)[:MAX_TRANSCRIPT_CHARS]
    reply = await ai.complete(
        [{"role": "system", "content": SYSTEM}, {"role": "user", "content": lines}],
        workspace_id=ctx.workspace_id,
        temperature=0.1,
        response_format={"type": "json_object"},
    )
    await ctx.progress(80)
    raw = _parse(reply.content)
    quotes, claims, dropped = [], [], 0
    for q in raw.get("quotes") or []:
        text = str((q or {}).get("text") or "").strip().strip('«»"').strip()
        start = locate(text, segments)
        if start is None:
            dropped += 1
            continue
        quotes.append({"text": text[:600], "start": start})
    for c in raw.get("claims") or []:
        text = str((c or {}).get("text") or "").strip()
        if not text:
            continue
        start = locate(str(c.get("from") or ""), segments)
        claims.append({"text": text[:400], "start": start})
    highlights = {
        "quotes": quotes[:8],
        "claims": claims[:10],
        "dropped_quotes": dropped,
        "model": reply.model,
        "at": datetime.now(UTC).isoformat(),
    }
    async with SessionLocal() as db:
        tr = await db.scalar(select(Transcript).where(Transcript.source_id == source_id))
        tr.highlights = highlights
        await db.commit()
        source = await db.get(Source, source_id)
        from app.modules.sources import source_payload
        from app.realtime.server import emit

        await emit(ctx.workspace_id, "source.updated", await source_payload(db, source))
    return {"quotes": len(quotes), "claims": len(claims)}


@router.post("/workspaces/{ws}/sources/{source_id}/quotes", status_code=202)
async def queue_quotes(source_id: uuid.UUID, member: AnyMember, db: Db) -> dict:
    s = await db.get(Source, source_id)
    if s is None or s.workspace_id != member.workspace_id:
        raise ApiError(404, "not_found", "Source not found")
    tr = await db.scalar(select(Transcript).where(Transcript.source_id == source_id))
    if tr is None or not tr.segments:
        raise ApiError(409, "no_transcript", "This source has no transcript yet")
    job = await enqueue(
        db, member.workspace_id, member.user.id, "extract_quotes", {"source_id": str(source_id)}
    )
    return job_payload(job)
