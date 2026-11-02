"""F1 claim checker: the AI reads the claim's attached sources and suggests a verdict.

`POST …/items/{id}/analyze` queues `analyze_claim`. The result lands in `item.data`:
`verdict_suggested` (the UI's suggestion banner) and `analysis` (checkable facts, evidence with
quotes, reason, what is missing). The AI only suggests; a journalist confirms the verdict.
Every quote must appear word for word in its source, otherwise it is dropped.
Beyond the attached sources, the checker also reads the newsroom's other sources whose passages
are close enough to the claim (other claims' files, unattached sources), marked as such.
Dates are worked out in code (`app/core/dates.py`): the prompt states today's date, when the
rumour was first seen and how old each source is; afterwards, a "true" resting only on sources
from well before the rumour becomes "unverifiable" (`date_check`).
How solid the reading is comes from code too (`app/core/confidence.py`, `analysis.confidence`):
how many sources back it, how official and recent they are, never the model's own confidence.
"""

import json
import logging
import re
import unicodedata
import uuid
from datetime import UTC, date, datetime
from typing import Any

from fastapi import APIRouter
from sqlalchemy import select

from app.core import ai, confidence, credibility, dates
from app.core.access import AnyMember, Db
from app.core.activity import broadcast, record
from app.core.db import SessionLocal
from app.core.errors import ApiError
from app.core.models import Item, Source
from app.workers.queue import JobContext, enqueue, handler, job_payload

log = logging.getLogger("fanilo.checker")
router = APIRouter(tags=["checker"])

VERDICTS = ("true", "misleading", "false", "unverifiable")
STANCES = ("supports", "contradicts", "context")
MAX_SOURCES = 8
# The prompt stays near 5 000 tokens so it fits Groq's free 8 000 tokens per minute: the best
# passages of each source (RAG) when it is indexed, else the start of its text.
CHARS_PER_SOURCE = 2500
TOTAL_CHARS = 14_000
# Other sources of the newsroom read alongside the attached ones. Measured on gemini-embedding-2
# with the demo files: a source about the claim scores 0.82 to 0.91, an unrelated one at most 0.76.
MAX_RELATED = 3
RELATED_MIN_SCORE = 0.78

SYSTEM = """Tu es l'assistant de vérification d'une rédaction à Madagascar. Tu aides un journaliste \
à vérifier une affirmation qui circule (Facebook, WhatsApp, radio, presse).

Règles :
- Tu t'appuies UNIQUEMENT sur les sources fournies, numérotées [1], [2]… Jamais sur ta mémoire.
- Les dates (aujourd'hui, première apparition de la rumeur, date de chaque source et son écart \
avec la rumeur) sont calculées pour toi : sers-t'en telles quelles, ne devine jamais une date.
- Une source publiée bien avant la rumeur ne confirme pas un fait récent : elle peut seulement \
montrer qu'un contenu est ancien ou recyclé, ou donner du contexte. Une source de date inconnue \
ne permet pas de dater un fait.
- Les sources marquées « autre dossier de la rédaction » n'ont pas été jointes par le journaliste : \
ne les cite que si elles parlent vraiment de cette affirmation.
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


def first_seen(item: Item) -> datetime:
    """When the rumour was first seen, in Madagascar time (or when it was entered)."""
    return dates.parse_moment((item.data or {}).get("first_seen_at")) or dates.parse_moment(
        item.created_at
    )


def dating(source: Source, seen: date) -> dict[str, Any]:
    """How old a source is against the rumour: its publication date when known; otherwise the day
    it entered the newsroom, when that was before the rumour (it was published by then)."""
    published = dates.parse(source.published_at)
    if published:
        return {"date": published, "basis": "published", "days_before": (seen - published).days}
    added = dates.parse(source.created_at)
    if added and added < seen:
        return {"date": added, "basis": "added", "days_before": (seen - added).days}
    return {"date": None, "basis": None, "days_before": None}


def date_line(d: dict[str, Any], seen: date) -> str:
    if d["basis"] == "published":
        return f"publiée le {dates.fr(d['date'])}, {dates.gap(d['date'], seen)}"
    if d["basis"] == "added":
        return (
            f"date de publication inconnue, déjà dans la rédaction le {dates.fr(d['date'])}, "
            f"{dates.gap(d['date'], seen)}"
        )
    return "date de publication inconnue"


def build_prompt(
    item: Item, sources: list[Source], excerpts: dict[uuid.UUID, str] | None = None
) -> str:
    """Numbered sources; each shows its relevant passages (`excerpts`) or the start of its text.
    Sources not attached to this claim are marked as coming from another file."""
    seen = first_seen(item)
    parts = [
        dates.today_line(),
        f"Rumeur vue pour la première fois le {dates.fr_moment(seen)}.",
        f"Affirmation : {item.title}",
    ]
    if item.body:
        parts.append(f"Contexte : {item.body}")
    if not sources:
        parts.append("Sources : aucune source n'est jointe pour l'instant.")
    budget = max(1000, TOTAL_CHARS // max(1, len(sources)))
    for i, s in enumerate(sources, 1):
        head = f"[{i}] {s.title}" + (f" ({s.url})" if s.url else "")
        if s.item_id != item.id:
            head += " · autre dossier de la rédaction"
        head += f" · {date_line(dating(s, seen.date()), seen.date())}"
        body = (excerpts or {}).get(s.id) or s.text
        parts.append(f"{head}\n{body[: min(CHARS_PER_SOURCE, budget)]}")
    return "\n\n".join(parts)


async def relevant_excerpts(db, item: Item) -> dict[uuid.UUID, str]:
    """The claim's closest passages per attached source, when the sources are indexed."""
    from app.core import embed
    from app.modules.rag import search

    if not embed.configured():
        return {}
    try:
        passages = await search(db, item.workspace_id, f"{item.title}\n{item.body}", 8, item.id)
    except Exception:  # noqa: BLE001 - no excerpts just means the start of each text is used
        log.warning("passage search failed for %s", item.id)
        return {}
    by_source: dict[uuid.UUID, list[str]] = {}
    for p in passages:
        by_source.setdefault(p.source_id, []).append(p.text)
    return {sid: "\n[…]\n".join(texts[:2]) for sid, texts in by_source.items()}


async def related_sources(
    db, item: Item, attached: list[Source]
) -> tuple[list[Source], dict[uuid.UUID, str]]:
    """The newsroom's other sources close to the claim, with their closest passages."""
    from app.core import embed
    from app.modules.rag import search

    if not embed.configured():
        return [], {}
    try:
        passages = await search(db, item.workspace_id, f"{item.title}\n{item.body}", 24)
    except Exception:  # noqa: BLE001 - the attached sources alone still make an analysis
        log.warning("newsroom search failed for %s", item.id)
        return [], {}
    skip = {s.id for s in attached}
    by_source: dict[uuid.UUID, list[str]] = {}
    for p in passages:
        if p.source_id in skip or p.score < RELATED_MIN_SCORE:
            continue
        if p.source_id in by_source or len(by_source) < MAX_RELATED:
            by_source.setdefault(p.source_id, []).append(p.text)
    if not by_source:
        return [], {}
    found = {
        s.id: s
        for s in await db.scalars(
            select(Source).where(Source.id.in_(by_source), Source.status == "ready")
        )
    }
    ordered = [found[sid] for sid in by_source if sid in found]
    return ordered, {sid: "\n[…]\n".join(texts[:2]) for sid, texts in by_source.items()}


def clean(raw: dict[str, Any], sources: list[Source], item: Item) -> dict[str, Any]:
    """Keep only what the sources back: unknown sources and quotes not found verbatim go.
    Each piece of evidence carries its source's date; a "true" whose supporting passages all come
    from well before the rumour becomes "unverifiable"."""
    seen = first_seen(item).date()
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
        when = dating(s, seen)
        evidence.append(
            {
                "source_id": str(s.id),
                "source_title": s.title,
                "n": n,
                # Not attached = read from another file of the newsroom (its claim, if any).
                "attached": s.item_id == item.id,
                "item_id": str(s.item_id) if s.item_id else None,
                "stance": e.get("stance") if e.get("stance") in STANCES else "context",
                "quote": quote[:600],
                "explanation": (e.get("explanation") or "")[:400],
                "source_date": when["date"].isoformat() if when["date"] else None,
                "date_basis": when["basis"],
                "days_before": when["days_before"],
            }
        )
    verdict = raw.get("verdict") if raw.get("verdict") in VERDICTS else "unverifiable"
    if not evidence:
        # Nothing in the sources backs a conclusion.
        verdict = "unverifiable"

    def old(e: dict[str, Any]) -> bool:
        return e["days_before"] is not None and e["days_before"] > dates.STALE_DAYS

    supports = [e for e in evidence if e["stance"] == "supports"]
    backing = [e for e in evidence if e["stance"] != "context"]
    date_check = None
    if verdict == "true" and supports and all(old(e) for e in supports):
        # An old page cannot confirm what is said to happen now; the journalist can still decide.
        verdict, date_check = "unverifiable", "downgraded"
    elif backing and all(old(e) for e in backing):
        date_check = "old_evidence"
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
        "date_check": date_check,
        "first_seen": first_seen(item).isoformat(),
    }


async def official_hosts(db, workspace_id: uuid.UUID) -> set[str]:
    """Official sites the newsroom declared in its Annuaire, once that module exists."""
    try:
        from app.modules.directory import official_hosts as declared
    except (ImportError, AttributeError):
        return set()
    try:
        return set(await declared(db, workspace_id))
    except Exception as exc:  # noqa: BLE001 - no declared site only means none is recognised
        log.info("official hosts unavailable: %s", type(exc).__name__)
        await db.rollback()
        return set()


def strength(
    result: dict[str, Any], sources: list[Source], item: Item, official: set[str]
) -> dict[str, Any]:
    """`confidence.compute` over the evidence kept by `clean`. Every source read here is held by
    the newsroom (joined to the dossier or among its other files), so all count as kept."""
    seen = first_seen(item)
    listed = []
    for n, s in enumerate(sources, 1):
        host = credibility.registrable(credibility.host_of(s.url)) if s.url else ""
        listed.append(
            {
                "n": n,
                "kind": "web" if s.url else "file",
                "url": s.url,
                "date": dating(s, seen.date())["date"],
                "title": s.title,
                "press": host in credibility.PRESS_HOSTS,
            }
        )
    return confidence.compute(
        result["evidence"],
        listed,
        seen,
        [n for n, _ in enumerate(sources, 1)],
        official_hosts=official,
    )


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
        excerpts = await relevant_excerpts(db, item)
        related, related_excerpts = await related_sources(db, item, sources)
        prompt = build_prompt(item, sources + related, {**excerpts, **related_excerpts})
        official = await official_hosts(db, item.workspace_id)
    await ctx.progress(20)
    reply = await ai.complete(
        [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
        workspace_id=ctx.workspace_id,
        temperature=0.1,
        response_format={"type": "json_object"},
    )
    await ctx.progress(80)
    result = clean(_parse(reply.content), sources + related, item)
    analysis = {
        **result,
        "sources_used": len(sources),
        "related_used": len(related),
        "confidence": strength(result, sources + related, item, official),
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
