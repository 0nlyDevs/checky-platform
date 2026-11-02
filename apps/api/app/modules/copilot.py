"""The desk copilot: the site agent inside a workspace. It reads the desk (what has circulated
longest, the night in brief, claims without sources, the sources themselves) and proposes changes:
create a claim, attach a link, run the analysis, move a status, open a claim.

`POST /workspaces/{ws}/copilot` SSE, same events as the agent. Write tools only *propose*: each comes
back in `answer.actions`, and the journalist confirms it, which calls `POST …/copilot/act`. That route
runs the change with the journalist's own rights. The copilot never confirms a verdict and never
publishes: `published` is not a status it can set and the verdict is not a field it can touch.
"""

import re
import uuid
from collections.abc import AsyncIterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter
from fastapi.sse import EventSourceResponse, ServerSentEvent
from pydantic import BaseModel, Field
from sqlalchemy import or_, select

from app.core.access import AnyMember, Db
from app.core.db import SessionLocal
from app.core.errors import ApiError
from app.core.models import Item
from app.modules.agent import AgentContext, Tools, find_claims, search_sources, tool_loop
from app.modules.guide import STATUS_FR, VERDICT_FR, GuideIn, conversation

router = APIRouter(tags=["agent"])

COPILOT_STEPS = 4
OPEN = ("to_check", "in_progress")
MOVABLE = ("to_check", "in_progress", "verified")  # never "published": a journalist publishes

COPILOT_SYSTEM = """Tu es le copilote de la rédaction dans FANILO, à Madagascar. Tu aides les \
journalistes à travailler : lire l'état du desk, chercher dans les sources, préparer des actions.

- Pour l'état du desk (ce qui circule depuis le plus longtemps, résumé de la nuit, affirmations sans \
source, signalements du public) : desk_overview.
- Pour une affirmation précise : find_claims. Pour un fait dans les sources : search_sources, et cite [n].
- Pour agir (créer une affirmation, joindre un lien, lancer l'analyse, changer le statut, ouvrir une \
affirmation) utilise les outils propose_* et open_claim. Rien n'est fait tant que le journaliste n'a \
pas appuyé sur « Confirmer » : dis-le simplement, ne prétends jamais que c'est fait.
- Tu ne confirmes jamais un verdict et tu ne publies jamais : c'est le travail du journaliste, sur la \
fiche de l'affirmation. Une suggestion de l'IA n'est pas un verdict. Si on te le demande, dis que tu \
ne peux pas le proposer et ouvre la fiche avec open_claim.
- Statuts, toujours en français : to_check = « à vérifier », in_progress = « en cours » (de \
vérification), verified = « vérifié », published = « publié ». N'écris jamais les noms anglais.
- Cite [n] uniquement pour les passages renvoyés par search_sources. Désigne une affirmation par sa \
référence (FAN-0139), sans crochets.
- Réponds en deux à cinq phrases courtes, dans la langue demandée."""


@dataclass
class DeskContext(AgentContext):
    page_claim: uuid.UUID | None = None


def _hours(item: Item) -> float:
    seen = (item.data or {}).get("first_seen_at")
    try:
        start = datetime.fromisoformat(seen) if seen else item.created_at
    except ValueError:
        start = item.created_at
    if start.tzinfo is None:
        start = start.replace(tzinfo=UTC)
    return max(0.0, (datetime.now(UTC) - start).total_seconds() / 3600)


def _line(item: Item) -> str:
    d = item.data or {}
    parts = [
        f"{d.get('ref') or '—'} « {item.title} »",
        STATUS_FR.get(item.status, item.status),
        f"circule depuis {_hours(item):.0f} h",
        f"{d.get('source_count') or 0} source(s)",
    ]
    if d.get("verdict"):
        parts.append(f"verdict {VERDICT_FR.get(d['verdict'], d['verdict'])}")
    elif d.get("verdict_suggested"):
        parts.append(f"suggestion IA {VERDICT_FR.get(d['verdict_suggested'], '?')} (à confirmer)")
    if "signalement" in (item.tags or []):
        parts.append("signalement du public")
    return f"{' · '.join(parts)} (id {item.id})"


async def desk_overview(ctx: DeskContext) -> tuple[str, str]:
    async with SessionLocal() as db:
        items = list(
            await db.scalars(
                select(Item).where(Item.workspace_id == ctx.workspace_id, Item.type == "claim")
            )
        )
    if not items:
        return "desk vide", "No claim in this workspace yet."
    counts = {s: sum(i.status == s for i in items) for s in STATUS_FR}
    open_ = sorted((i for i in items if i.status in OPEN), key=_hours, reverse=True)
    bare = [i for i in open_ if not (i.data or {}).get("source_count")]
    tips = [i for i in open_ if "signalement" in (i.tags or [])]
    night = [i for i in items if _hours(i) <= 12]
    out = [
        "Statuts : " + ", ".join(f"{STATUS_FR[s]} {n}" for s, n in counts.items()),
        f"Vues ces 12 dernières heures : {len(night)}",
        "Ouvertes, de la plus ancienne :",
        *(_line(i) for i in open_[:6]),
        f"Ouvertes sans aucune source : {len(bare)}",
        *(_line(i) for i in bare[:4]),
        f"Signalements du public à vérifier : {len(tips)}",
        *(_line(i) for i in tips[:3]),
    ]
    return f"{len(items)} affirmations, {len(open_)} ouvertes", "\n".join(out)


async def _claim(ctx: DeskContext, claim: str | None) -> Item | None:
    """A claim by id, FAN ref or words of its title; this page's claim when none is named."""
    async with SessionLocal() as db:
        base = select(Item).where(Item.workspace_id == ctx.workspace_id, Item.type == "claim")
        if not claim:
            return await db.get(Item, ctx.page_claim) if ctx.page_claim else None
        try:
            return await db.scalar(base.where(Item.id == uuid.UUID(claim)))
        except ValueError:
            pass
        if m := re.search(r"FAN-?\s*(\d+)", claim, re.IGNORECASE):
            return await db.scalar(base.where(Item.data["ref"].astext == f"FAN-{int(m[1]):04d}"))
        like = f"%{claim.strip()}%"
        return await db.scalar(
            base.where(or_(Item.title.ilike(like), Item.body.ilike(like)))
            .order_by(Item.created_at.desc())
            .limit(1)
        )


def _target(item: Item) -> dict:
    return {"item_id": str(item.id), "ref": (item.data or {}).get("ref"), "title": item.title}


async def propose_create_claim(
    ctx: DeskContext, title: str, body: str | None = None, origin: str | None = None
) -> tuple[str, str]:
    if origin not in {"facebook", "whatsapp", "tiktok", "radio", "press", "other"}:
        origin = "other"
    ctx.propose(
        "create_claim", title=title.strip()[:300], body=(body or "").strip()[:4000], origin=origin
    )
    return "création proposée", "Proposed; the journalist must press Confirmer. Not created yet."


async def propose_attach_link(
    ctx: DeskContext, url: str, claim: str | None = None
) -> tuple[str, str]:
    if not re.match(r"https?://", url or ""):
        return "lien invalide", "The link must start with http:// or https://."
    item = await _claim(ctx, claim)
    if item is None:
        return "affirmation introuvable", "No such claim; ask which one."
    ctx.propose("attach_link", url=url, **_target(item))
    return f"lien proposé pour {_target(item)['ref']}", "Proposed; waiting for Confirmer."


async def propose_analysis(ctx: DeskContext, claim: str | None = None) -> tuple[str, str]:
    item = await _claim(ctx, claim)
    if item is None:
        return "affirmation introuvable", "No such claim; ask which one."
    note = "" if (item.data or {}).get("source_count") else " It has no source yet: say so."
    ctx.propose("analyze", **_target(item))
    return (
        f"analyse proposée pour {_target(item)['ref']}",
        "Proposed; waiting for Confirmer." + note,
    )


async def propose_status(
    ctx: DeskContext, status: str, claim: str | None = None
) -> tuple[str, str]:
    if status not in MOVABLE:
        return (
            "statut refusé",
            "Only to_check, in_progress or verified. Publishing is the journalist's.",
        )
    item = await _claim(ctx, claim)
    if item is None:
        return "affirmation introuvable", "No such claim; ask which one."
    ctx.propose("set_status", status=status, status_label=STATUS_FR[status], **_target(item))
    return f"{_target(item)['ref']} → {STATUS_FR[status]}", "Proposed; waiting for Confirmer."


async def open_claim(ctx: DeskContext, claim: str) -> tuple[str, str]:
    item = await _claim(ctx, claim)
    if item is None:
        return "affirmation introuvable", "No such claim."
    href = f"/w/{ctx.workspace_id}/affirmations/{item.id}"
    ctx.propose("navigate", href=href, label=f"{_target(item)['ref']} · {item.title}")
    return f"ouvre {_target(item)['ref']}", f"The claim opens ({href})."


CLAIM = {"type": "string", "description": "FAN ref, id or words of the title; empty = this page's"}
COPILOT_TOOLS: Tools = {
    "desk_overview": (
        desk_overview,
        (
            "The desk at a glance: counts by status, open claims oldest first, claims without sources, "
            "public tips, how many were seen in the last 12 hours."
        ),
        {"type": "object", "properties": {}},
    ),
    "find_claims": (
        find_claims,
        "Find tracked claims whose title or context contains the words.",
        {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
    ),
    "search_sources": (
        search_sources,
        "Search the workspace's sources and return numbered passages to cite.",
        {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
    ),
    "propose_create_claim": (
        propose_create_claim,
        "Propose tracking a new claim. The journalist confirms.",
        {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "The claim, one sentence"},
                "body": {"type": "string", "description": "Context: where, who, the message"},
                "origin": {
                    "type": "string",
                    "enum": ["facebook", "whatsapp", "tiktok", "radio", "press", "other"],
                },
            },
            "required": ["title"],
        },
    ),
    "propose_attach_link": (
        propose_attach_link,
        "Propose attaching a web link as a source of a claim. The journalist confirms.",
        {
            "type": "object",
            "properties": {"url": {"type": "string"}, "claim": CLAIM},
            "required": ["url"],
        },
    ),
    "propose_analysis": (
        propose_analysis,
        "Propose running the AI analysis of a claim against its sources. The journalist confirms.",
        {"type": "object", "properties": {"claim": CLAIM}},
    ),
    "propose_status": (
        propose_status,
        "Propose moving a claim to another status (not published). The journalist confirms.",
        {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": list(MOVABLE),
                    "description": "to_check = à vérifier, in_progress = en cours de vérification, "
                    "verified = vérifié",
                },
                "claim": CLAIM,
            },
            "required": ["status"],
        },
    ),
    "open_claim": (
        open_claim,
        "Open a claim's page for the journalist.",
        {"type": "object", "properties": {"claim": CLAIM}, "required": ["claim"]},
    ),
}


@router.post("/workspaces/{ws}/copilot", response_class=EventSourceResponse)
async def copilot(body: GuideIn, member: AnyMember) -> AsyncIterable[ServerSentEvent]:
    ctx = DeskContext(member.workspace_id)
    context = ""
    if m := re.search(r"/affirmations/([0-9a-f-]{36})", body.page):
        ctx.page_claim = uuid.UUID(m[1])
        if item := await _claim(ctx, None):
            context = f" Le journaliste regarde l'affirmation : {_line(item)}."
    async for event in tool_loop(
        ctx,
        conversation(COPILOT_SYSTEM, body, context),
        COPILOT_TOOLS,
        COPILOT_STEPS,
        max_tokens=600,
    ):
        yield event


class ActIn(BaseModel):
    kind: Literal["create_claim", "attach_link", "analyze", "set_status"]
    item_id: uuid.UUID | None = None
    title: str | None = Field(default=None, max_length=300)
    body: str = Field(default="", max_length=4000)
    origin: Literal["facebook", "whatsapp", "tiktok", "radio", "press", "other"] = "other"
    url: str | None = Field(default=None, max_length=2000)
    status: Literal["to_check", "in_progress", "verified"] | None = None


class ActOut(BaseModel):
    kind: str
    item_id: uuid.UUID
    ref: str | None


@router.post("/workspaces/{ws}/copilot/act")
async def act(body: ActIn, member: AnyMember, db: Db) -> ActOut:
    """Runs one confirmed proposal through the ordinary routes, with the journalist's rights."""
    from app.modules import checker, items, sources
    from app.modules.public import _next_ref

    if body.kind == "create_claim":
        if not body.title:
            raise ApiError(422, "bad_request", "A claim needs a title")
        data = {
            "ref": await _next_ref(db, member.workspace_id),
            "first_seen_at": datetime.now(UTC).isoformat(),
            "origin": body.origin,
            "source_count": 0,
        }
        made = await items.create_item(
            items.ItemIn(title=body.title, body=body.body, data=data), member, db
        )
        return ActOut(kind=body.kind, item_id=made.id, ref=data["ref"])
    if body.item_id is None:
        raise ApiError(422, "bad_request", "This action needs a claim")
    item = await db.get(Item, body.item_id)
    if item is None or item.workspace_id != member.workspace_id:
        raise ApiError(404, "not_found", "Item not found")
    ref = (item.data or {}).get("ref")
    if body.kind == "attach_link":
        if not body.url:
            raise ApiError(422, "bad_request", "A link is needed")
        await sources.add_source(sources.SourceIn(item_id=item.id, url=body.url), member, db)
    elif body.kind == "analyze":
        await checker.analyze(item.id, member, db)
    else:
        if body.status is None:
            raise ApiError(422, "bad_request", "A status is needed")
        await items.update_item(item.id, items.ItemPatch(status=body.status), member, db)
    return ActOut(kind=body.kind, item_id=item.id, ref=ref)
