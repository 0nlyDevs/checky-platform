"""F1 claim checker: the AI reads the claim's attached sources and suggests a verdict.

`POST …/items/{id}/analyze` queues `analyze_claim`. The result lands in `item.data`:
`verdict_suggested` (the UI's suggestion banner) and `analysis` (checkable facts, evidence with
quotes, reason, what is missing). The AI only suggests; a journalist confirms the verdict.
Every quote must appear word for word in its source, otherwise it is dropped.
"""

import json
import re
import unicodedata
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter
from sqlalchemy import select

from app.core import ai
from app.core.access import AnyMember, Db
from app.core.activity import broadcast, record
from app.core.db import SessionLocal
from app.core.errors import ApiError
from app.core.models import Item, Source
from app.workers.queue import JobContext, enqueue, handler, job_payload

router = APIRouter(tags=["checker"])

VERDICTS = ("true", "misleading", "false", "unverifiable")
STANCES = ("supports", "contradicts", "context")
MAX_SOURCES = 8
CHARS_PER_SOURCE = 6000

SYSTEM = """Tu es l'assistant de vérification d'une rédaction à Madagascar. Tu aides un journaliste \
à vérifier une affirmation qui circule (Facebook, WhatsApp, radio, presse).

Règles :
- Tu t'appuies UNIQUEMENT sur les sources fournies, numérotées [1], [2]… Jamais sur ta mémoire.
- Chaque élément de preuve cite une phrase recopiée MOT POUR MOT depuis sa source (champ "quote").
- Sans source qui permet de trancher, le verdict est "unverifiable" et tu dis ce qu'il faudrait chercher.
- "misleading" = en partie vrai mais trompeur (chiffre sorti du contexte, date fausse, exagération).
- Réponds en français, phrases courtes et factuelles.

Réponds avec un seul objet JSON, sans texte autour :
{
  "claims": [{"text": "fait vérifiable, une phrase", "who": "…", "what": "…", "when": "…", "figure": "…"}],
  "evidence": [{"source": 1, "stance": "supports|contradicts|context", "quote": "…", "explanation": "…"}],
  "verdict": "true|misleading|false|unverifiable",
  "reason": "une ou deux phrases",
  "missing": "ce qu'il reste à vérifier, ou une chaîne vide"
}"""


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).lower()
    s = s.replace("’", "'").replace("«", '"').replace("»", '"')
    return re.sub(r"\s+", " ", s).strip()


def _parse(content: str) -> dict[str, Any]:
    """The model's JSON, tolerating code fences or text around it."""
    m = re.search(r"\{.*\}", content, re.DOTALL)
    if not m:
        raise ValueError("The model did not return JSON")
    return json.loads(m.group(0))


def build_prompt(item: Item, sources: list[Source]) -> str:
    parts = [f"Affirmation : {item.title}"]
    if item.body:
        parts.append(f"Contexte : {item.body}")
    if not sources:
        parts.append("Sources : aucune source n'est jointe pour l'instant.")
    for i, s in enumerate(sources, 1):
        head = f"[{i}] {s.title}" + (f" ({s.url})" if s.url else "")
        parts.append(f"{head}\n{s.text[:CHARS_PER_SOURCE]}")
    return "\n\n".join(parts)


def clean(raw: dict[str, Any], sources: list[Source]) -> dict[str, Any]:
    """Keep only what the sources back: unknown sources and quotes not found verbatim go."""
    texts = {i: _norm(s.text) for i, s in enumerate(sources, 1)}
    evidence, dropped = [], 0
    for e in raw.get("evidence") or []:
        try:
            n = int(e.get("source"))
        except (TypeError, ValueError):
            dropped += 1
            continue
        quote = (e.get("quote") or "").strip()
        if n not in texts or not quote or _norm(quote) not in texts[n]:
            dropped += 1
            continue
        s = sources[n - 1]
        evidence.append(
            {
                "source_id": str(s.id),
                "source_title": s.title,
                "n": n,
                "stance": e.get("stance") if e.get("stance") in STANCES else "context",
                "quote": quote[:600],
                "explanation": (e.get("explanation") or "")[:400],
            }
        )
    verdict = raw.get("verdict") if raw.get("verdict") in VERDICTS else "unverifiable"
    if not evidence:
        # Nothing in the sources backs a conclusion.
        verdict = "unverifiable"
    claims = [
        {k: str(c.get(k) or "")[:300] for k in ("text", "who", "what", "when", "figure")}
        for c in (raw.get("claims") or [])
        if isinstance(c, dict) and c.get("text")
    ][:8]
    return {
        "claims": claims,
        "evidence": evidence[:12],
        "verdict": verdict,
        "reason": str(raw.get("reason") or "")[:600],
        "missing": str(raw.get("missing") or "")[:600],
        "dropped_quotes": dropped,
    }


@handler("analyze_claim")
async def analyze_claim(ctx: JobContext) -> dict[str, Any]:
    item_id = uuid.UUID(ctx.input["item_id"])
    async with SessionLocal() as db:
        item = await db.get(Item, item_id)
        if item is None:
            raise ValueError("The claim no longer exists")
        sources = list(
            await db.scalars(
                select(Source)
                .where(Source.item_id == item_id, Source.status == "ready", Source.text != "")
                .order_by(Source.created_at)
                .limit(MAX_SOURCES)
            )
        )
        prompt = build_prompt(item, sources)
    await ctx.progress(20)
    reply = await ai.complete(
        [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
        workspace_id=ctx.workspace_id,
        temperature=0.1,
        response_format={"type": "json_object"},
    )
    await ctx.progress(80)
    result = clean(_parse(reply.content), sources)
    analysis = {
        **result,
        "sources_used": len(sources),
        "provider": reply.provider,
        "model": reply.model,
        "at": datetime.now(UTC).isoformat(),
        "by": ctx.created_by,
    }
    async with SessionLocal() as db:
        item = await db.get(Item, item_id)
        item.data = {**item.data, "verdict_suggested": result["verdict"], "analysis": analysis}
        await record(
            db,
            item.workspace_id,
            ctx.created_by,
            "item",
            item.id,
            "analysis",
            {"verdict_suggested": result["verdict"]},
        )
        await db.commit()
        await db.refresh(item)
        from app.modules.items import ItemOut

        await broadcast(
            item.workspace_id, "item.updated", ItemOut.model_validate(item).model_dump(mode="json")
        )
    return {"item_id": str(item_id), "verdict_suggested": result["verdict"]}


@router.post("/workspaces/{ws}/items/{item_id}/analyze", status_code=202)
async def analyze(item_id: uuid.UUID, member: AnyMember, db: Db) -> dict:
    item = await db.get(Item, item_id)
    if item is None or item.workspace_id != member.workspace_id:
        raise ApiError(404, "not_found", "Item not found")
    job = await enqueue(
        db, member.workspace_id, member.user.id, "analyze_claim", {"item_id": str(item_id)}
    )
    return job_payload(job)
