"""RAG (M8): every ready source is split into passages and embedded; questions are answered
only from the passages found, each claim cited as [n].

`embed_source` runs after a source is ready (chained by the ingest jobs).
`POST …/search` returns the closest passages; `POST …/ask` streams an answer over SSE:
`citations` (the numbered passages), then `delta` ({text}) events, then `done` or `error`.
"""

import re
import uuid
from collections.abc import AsyncIterable
from typing import Any

from fastapi import APIRouter
from fastapi.sse import EventSourceResponse, ServerSentEvent
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import ai, embed
from app.core.access import AnyMember, Db
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.errors import ApiError
from app.core.models import Chunk, Source, Transcript
from app.workers.queue import JobContext, enqueue, handler

router = APIRouter(tags=["rag"])

CHUNK_CHARS = 2400  # about 600 tokens of French
OVERLAP_CHARS = 300


# --- splitting ---------------------------------------------------------------------------


def split_text(text: str) -> list[str]:
    """Paragraph-aware chunks of about CHUNK_CHARS, overlapping by OVERLAP_CHARS."""
    paras = [p.strip() for p in re.split(r"\n\s*\n|\n", text) if p.strip()]
    chunks: list[str] = []
    cur = ""
    for p in paras:
        while len(p) > CHUNK_CHARS:  # a very long paragraph is cut at a sentence end
            cut = p.rfind(". ", 0, CHUNK_CHARS)
            cut = cut + 1 if cut > CHUNK_CHARS // 2 else CHUNK_CHARS
            if cur:
                chunks.append(cur)
                cur = ""
            chunks.append(p[:cut].strip())
            p = p[cut - OVERLAP_CHARS if cut > OVERLAP_CHARS else cut :].strip()
        if len(cur) + len(p) + 1 > CHUNK_CHARS and cur:
            chunks.append(cur)
            cur = cur[-OVERLAP_CHARS:].split(" ", 1)[-1] + "\n" + p
        else:
            cur = f"{cur}\n{p}" if cur else p
    if cur:
        chunks.append(cur)
    return chunks


def split_segments(segments: list[dict[str, Any]]) -> list[tuple[str, float, float]]:
    """Transcript segments grouped into passages that keep their start and end times."""
    out: list[tuple[str, float, float]] = []
    text, start, end = "", None, None
    for g in segments:
        if text and len(text) + len(g["text"]) > CHUNK_CHARS:
            out.append((text, start, end))
            text, start = "", None
        start = g["start"] if start is None else start
        end = g["end"]
        text = f"{text} {g['text']}".strip()
    if text:
        out.append((text, start, end))
    return out


# --- indexing ----------------------------------------------------------------------------


async def queue_embedding(
    db: AsyncSession, ws: uuid.UUID, user_id: str, source_id: uuid.UUID
) -> None:
    if embed.configured():
        await enqueue(db, ws, user_id, "embed_source", {"source_id": str(source_id)})


@handler("embed_source")
async def embed_source(ctx: JobContext) -> dict[str, Any]:
    source_id = uuid.UUID(ctx.input["source_id"])
    async with SessionLocal() as db:
        source = await db.get(Source, source_id)
        if source is None or not source.text:
            return {"chunks": 0}
        tr = await db.scalar(select(Transcript).where(Transcript.source_id == source_id))
        if tr is not None and tr.segments:
            parts = split_segments(tr.segments)
        else:
            parts = [(t, None, None) for t in split_text(source.text)]
        ws = source.workspace_id
        # The title rides along so a passage keeps its context ("Rapport INSTAT: …").
        inputs = [f"{source.title}\n{t}" for t, _, _ in parts]
    vectors = await embed.embed(inputs)
    await ctx.progress(80)
    model = get_settings().embed_model
    async with SessionLocal() as db:
        await db.execute(delete(Chunk).where(Chunk.source_id == source_id))
        for i, ((t, start, end), v) in enumerate(zip(parts, vectors, strict=True)):
            db.add(
                Chunk(
                    source_id=source_id,
                    workspace_id=ws,
                    ord=i,
                    text=t,
                    start_s=start,
                    end_s=end,
                    embedding=v,
                    embed_model=model,
                )
            )
        await db.commit()
    return {"chunks": len(parts)}


# --- search ------------------------------------------------------------------------------


class SearchIn(BaseModel):
    query: str = Field(min_length=2, max_length=2000)
    k: int = Field(default=6, ge=1, le=20)
    item_id: uuid.UUID | None = None


class Passage(BaseModel):
    n: int
    chunk_id: uuid.UUID
    source_id: uuid.UUID
    title: str
    kind: str
    url: str | None
    text: str
    start_s: float | None
    end_s: float | None
    score: float


async def search(
    db: AsyncSession, ws: uuid.UUID, query: str, k: int, item_id: uuid.UUID | None = None
) -> list[Passage]:
    [qv] = await embed.embed([query])
    distance = Chunk.embedding.cosine_distance(qv)
    stmt = (
        select(Chunk, Source, distance.label("d"))
        .join(Source, Source.id == Chunk.source_id)
        .where(Chunk.workspace_id == ws, Chunk.embed_model == get_settings().embed_model)
        .order_by(distance)
        .limit(k)
    )
    if item_id:
        stmt = stmt.where(Source.item_id == item_id)
    rows = (await db.execute(stmt)).all()
    return [
        Passage(
            n=i,
            chunk_id=c.id,
            source_id=s.id,
            title=s.title,
            kind=s.kind,
            url=s.url,
            text=c.text,
            start_s=c.start_s,
            end_s=c.end_s,
            score=round(1 - d, 4),
        )
        for i, (c, s, d) in enumerate(rows, 1)
    ]


def _require_embeddings() -> None:
    if not embed.configured():
        raise ApiError(503, "embeddings_unavailable", "No embedding provider is configured")


@router.post("/workspaces/{ws}/search")
async def search_route(body: SearchIn, member: AnyMember, db: Db) -> list[Passage]:
    _require_embeddings()
    try:
        return await search(db, member.workspace_id, body.query, body.k, body.item_id)
    except embed.EmbedUnavailable as e:
        raise ApiError(503, "embeddings_unavailable", str(e)) from e


# --- ask ---------------------------------------------------------------------------------

ASK_SYSTEM = """Tu réponds aux questions d'un journaliste à partir des passages numérotés fournis, \
et UNIQUEMENT à partir d'eux.
- Après chaque phrase, cite le ou les passages qui la justifient : [1], [2]…
- Si les passages ne permettent pas de répondre, dis-le clairement en une phrase \
("Les sources réunies ne permettent pas de répondre.") et n'invente rien.
- Réponds dans la langue de la question (français ou malgache), en 3 à 6 phrases courtes."""


class AskIn(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
    k: int = Field(default=6, ge=1, le=12)
    item_id: uuid.UUID | None = None


@router.post("/workspaces/{ws}/ask", response_class=EventSourceResponse)
async def ask(body: AskIn, member: AnyMember) -> AsyncIterable[ServerSentEvent]:
    _require_embeddings()
    try:
        async with SessionLocal() as db:
            passages = await search(db, member.workspace_id, body.question, body.k, body.item_id)
    except embed.EmbedUnavailable as e:
        yield ServerSentEvent(
            data={"code": "embeddings_unavailable", "message": str(e)}, event="error"
        )
        return
    except Exception as e:  # noqa: BLE001 - never end the stream without telling the client
        yield ServerSentEvent(
            data={"code": "search_failed", "message": type(e).__name__}, event="error"
        )
        return
    yield ServerSentEvent(data=[p.model_dump(mode="json") for p in passages], event="citations")
    context = "\n\n".join(f"[{p.n}] {p.title}\n{p.text}" for p in passages) or "(aucun passage)"
    stream = ai.complete(
        [
            {"role": "system", "content": ASK_SYSTEM},
            {"role": "user", "content": f"Passages :\n\n{context}\n\nQuestion : {body.question}"},
        ],
        stream=True,
        workspace_id=member.workspace_id,
        temperature=0.1,
    )
    try:
        async for text in stream:
            yield ServerSentEvent(data={"text": text}, event="delta")
    except ai.AiUnavailable as e:
        yield ServerSentEvent(data={"code": "ai_unavailable", "message": str(e)}, event="error")
        return
    except Exception as e:  # noqa: BLE001 - the stream broke after it started
        yield ServerSentEvent(data={"code": "ai_stream_failed", "message": str(e)}, event="error")
        return
    c = stream.completion
    yield ServerSentEvent(data={"provider": c.provider, "model": c.model}, event="done")
