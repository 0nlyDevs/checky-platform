"""The site agent for visitors without an account: it explains Checky, finds published verdicts,
prepares a tip, follows the visitor's own tips and opens the right page.

`POST /public/agent` SSE, same events as the desk agent (`step`, `answer` {text, citations,
actions}, `done`|`error`). It never writes anything: a tip comes back as a `tip` action that the
visitor sends with the ordinary `POST /public/tips` after reading it; `navigate` actions are opened by
the widget. Citations are published verdicts ({n, id, title, verdict, url, text}).
"""

import re
import uuid
from collections import defaultdict, deque
from collections.abc import AsyncIterable
from dataclasses import dataclass, field
from typing import Any, Literal

from fastapi import APIRouter, Depends, Request
from fastapi.sse import EventSourceResponse, ServerSentEvent
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select

from app.core import dates
from app.core.db import SessionLocal
from app.core.errors import ApiError
from app.core.models import Item, Workspace
from app.modules.agent import AgentContext, Tools, tool_loop
from app.modules.guard import SCOPE, Guard
from app.modules.public import _allow, find_published

router = APIRouter(prefix="/public", tags=["public"])

GUIDE_STEPS = 4  # model turns per question: the free Groq tier counts tokens per minute
_GUIDES: dict[str, deque[float]] = defaultdict(deque)
GUIDE_LIMIT, GUIDE_WINDOW = 12, 600.0

VERDICT_FR = {
    "true": "Vrai",
    "misleading": "Trompeur",
    "false": "Faux",
    "unverifiable": "Invérifiable",
}
STATUS_FR = {
    "to_check": "reçu, pas encore pris en charge par un journaliste",
    "in_progress": "en cours de vérification",
    "verified": "vérifié, publication en préparation",
    "published": "verdict publié",
}
PAGES = {
    "accueil": ("/home", "Vérifier un message (accueil)"),
    "verifies": ("/verdicts", "Les verdicts"),
    "signaler": ("/report", "Signaler une rumeur"),
    "connexion": ("/sign-in", "Se connecter"),
    "inscription": ("/sign-up", "Inscrire sa rédaction"),
}

GUIDE_SYSTEM = (
    """Tu es le guide du site Checky, à Madagascar. Tu aides les visiteurs, sans compte.

Ce qu'est Checky : un outil de vérification pour les rédactions. Les journalistes suivent les rumeurs \
de la nuit (Facebook, WhatsApp, TikTok, radio), joignent leurs sources, une IA propose un verdict et \
un journaliste le confirme toujours. Les verdicts publiés (Vrai, Trompeur, Faux, Invérifiable) sont \
publics sur la page « Les verdicts ». N'importe qui peut signaler un message douteux à une rédaction, \
sans compte ni donnée personnelle, et suivre la vérification avec un lien. Une rédaction crée son \
espace gratuitement (page inscription) puis invite ses journalistes.

Règles :
- Un fait, une rumeur, « est-ce vrai ? » : cherche avec search_verdicts. Ne réponds que d'après les \
verdicts trouvés et cite-les [n]. Sans verdict, dis que ce n'est pas encore vérifié et propose de le \
signaler. Tu ne donnes jamais ton propre verdict.
- Signaler : appelle draft_tip tout de suite avec ce que le visiteur a dit (le message ou la rumeur, \
le lien s'il y en a un, l'origine). Ne demande pas plus de détails : il peut corriger le texte dans le \
brouillon. Il n'est PAS envoyé : le visiteur le relit et appuie sur « Envoyer ». Dis-le en une phrase.
- « Où en est mon signalement ? » : my_tips.
- « Montre-moi », « emmène-moi », une page : open_page.
- N'écris jamais d'adresse web ni de lien inventé : open_page ouvre la page tout seul.
- Réponds en deux à quatre phrases courtes, simples, dans la langue demandée.

"""
    + SCOPE
)


GUIDE_REFUSAL = {
    "fr": "Ce n'est pas mon rôle : je suis le guide de Checky. Je peux chercher si une rumeur a "
    "déjà été vérifiée par une rédaction, préparer un signalement ou vous dire où en sont les vôtres.",
    "mg": "Tsy anjarako izany : mpitari-dalana ao amin'ny Checky aho. Afaka mijery aho raha efa "
    "nohamarinin'ny mpanao gazety ny tsaho iray, na manomana fitarainana ho anao.",
}
GUIDE_NO_VERDICT = {
    "fr": "Aucune rédaction n'a encore publié de verdict sur ce sujet : il n'est pas vérifié. "
    "Vous pouvez le signaler pour qu'une rédaction le vérifie.",
    "mg": "Mbola tsy misy mpanao gazety namoaka valiny momba izany : tsy voamarina izy io. "
    "Azonao atao ny mitatitra azy.",
}


@dataclass
class GuideContext(AgentContext):
    tips: list[str] = field(default_factory=list)


async def search_verdicts(ctx: GuideContext, query: str) -> tuple[str, str]:
    async with SessionLocal() as db:
        files = await find_published(db, query)
    lines = []
    for v in files:
        n = len(ctx.cited) + 1
        ctx.cited.append(
            {
                "n": n,
                "id": str(v.id),
                "title": v.title,
                "verdict": v.verdict,
                "url": f"/verdicts/{v.id}",
                "text": (v.reason or "")[:400],
            }
        )
        lines.append(
            f"[{n}] {v.ref} · {v.newsroom.name} · verdict : {VERDICT_FR[v.verdict]}\n"
            f"Affirmation : {v.title}\nRaison : {v.reason or '—'}"
        )
    summary = f"{len(files)} verdicts publiés" if files else "aucun verdict publié"
    return summary, "\n\n".join(lines) or "No published verdict matches."


async def _newsrooms() -> list[Workspace]:
    async with SessionLocal() as db:
        rows = await db.scalars(
            select(Workspace).where(Workspace.publishes).order_by(Workspace.name)
        )
        return list(rows)


async def list_newsrooms(ctx: GuideContext) -> tuple[str, str]:
    rooms = await _newsrooms()
    return f"{len(rooms)} rédactions", "\n".join(f"{w.slug}: {w.name}" for w in rooms) or "None."


async def draft_tip(
    ctx: GuideContext,
    text: str,
    url: str | None = None,
    origin: str | None = None,
    newsroom: str | None = None,
) -> tuple[str, str]:
    rooms = await _newsrooms()
    if not rooms:
        return "aucune rédaction", "No newsroom receives tips yet. Tell the visitor."
    room = next((w for w in rooms if newsroom in (w.slug, w.name)), rooms[0])
    if origin not in {"facebook", "whatsapp", "tiktok", "radio", "press", "other"}:
        origin = "other"
    url = url if url and re.match(r"https?://", url) else None
    ctx.propose(
        "tip",
        newsroom=room.slug,
        newsroom_name=room.name,
        newsrooms=[{"slug": w.slug, "name": w.name} for w in rooms],  # the visitor may change it
        text=text.strip()[:4000],
        url=url,
        origin=origin,
    )
    return (
        f"signalement prêt pour {room.name}",
        (
            "The draft is shown to the visitor with Envoyer / Annuler buttons. It is NOT sent yet: ask "
            "them to check it and press Envoyer. Never say it was sent."
        ),
    )


async def my_tips(ctx: GuideContext) -> tuple[str, str]:
    if not ctx.tips:
        return "aucun signalement", "This device has sent no tip (none remembered)."
    async with SessionLocal() as db:
        items = list(
            await db.scalars(select(Item).where(Item.data["tip_token"].astext.in_(ctx.tips)))
        )
    lines = []
    for i in items:
        d = i.data or {}
        verdict = d.get("verdict") if i.status == "published" else None
        lines.append(
            f"{d.get('ref')} « {i.title} » : {STATUS_FR.get(i.status, i.status)}"
            + (f", verdict {VERDICT_FR.get(verdict, verdict)}" if verdict else "")
            + f" (suivi : /track/{d.get('tip_token')})"
        )
    return f"{len(items)} signalements", "\n".join(lines) or "No tip found for these links."


async def open_page(ctx: GuideContext, page: str, id: str | None = None) -> tuple[str, str]:
    if page == "verdict" and id:
        try:
            href, label = f"/verdicts/{uuid.UUID(id)}", "Le dossier"
        except ValueError:
            return "dossier inconnu", "Unknown verdict id."
    elif page == "suivi" and id and id in ctx.tips:
        href, label = f"/track/{id}", "Le suivi du signalement"
    elif page in PAGES:
        href, label = PAGES[page]
    else:
        return "page inconnue", f"Unknown page. Pages: {', '.join(PAGES)}, verdict, suivi."
    ctx.propose("navigate", href=href, label=label)
    return f"ouvre « {label} »", f"The page {href} opens for the visitor."


GUIDE_TOOLS: Tools = {
    "search_verdicts": (
        search_verdicts,
        "Find verdicts published by newsrooms about a claim or topic. Returns numbered files.",
        {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
    ),
    "list_newsrooms": (
        list_newsrooms,
        "List the newsrooms that publish verdicts and receive tips.",
        {"type": "object", "properties": {}},
    ),
    "draft_tip": (
        draft_tip,
        "Prepare a tip (a doubtful message to verify) for the visitor to check and send. Never sends.",
        {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "The message or rumour, as received"},
                "url": {"type": "string", "description": "Link to the post, if any"},
                "origin": {
                    "type": "string",
                    "enum": ["facebook", "whatsapp", "tiktok", "radio", "press", "other"],
                },
                "newsroom": {
                    "type": "string",
                    "description": "Newsroom slug, if the visitor chose",
                },
            },
            "required": ["text"],
        },
    ),
    "my_tips": (
        my_tips,
        "Status of the tips this visitor sent from this device.",
        {"type": "object", "properties": {}},
    ),
    "open_page": (
        open_page,
        "Open a page of the site for the visitor.",
        {
            "type": "object",
            "properties": {
                "page": {"type": "string", "enum": [*PAGES, "verdict", "suivi"]},
                "id": {"type": "string", "description": "Verdict id, or tip token for suivi"},
            },
            "required": ["page"],
        },
    ),
}


class Turn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=2000)


class GuideIn(BaseModel):
    # The conversation so far, last message from the visitor; the widget sends the last few turns.
    messages: list[Turn] = Field(min_length=1, max_length=12)

    @model_validator(mode="after")
    def ends_with_question(self):
        if self.messages[-1].role != "user":
            raise ValueError("the last message must be the visitor's")
        return self

    lang: Literal["fr", "mg"] = "fr"
    page: str = Field(default="/", max_length=300)
    tips: list[str] = Field(default=[], max_length=20)
    # Voice mode: the answer is read aloud, so it is kept short and plain.
    voice: bool = False


VOICE = (
    " Mode voix : ta réponse sera lue à voix haute. Réponds en deux ou trois phrases courtes, "
    "sans liste, sans titre, sans gras ni lien écrit ; les citations [n] restent."
)


def conversation(system: str, body: GuideIn, context: str = "") -> list[dict[str, Any]]:
    lang = "malagasy" if body.lang == "mg" else "français"
    head = (
        f"{system}\n\n{dates.today_line()} Langue de réponse : {lang}. "
        f"Page actuelle : {body.page}.{VOICE if body.voice else ''}{context}"
    )
    return [{"role": "system", "content": head}, *(t.model_dump() for t in body.messages[-8:])]


def _limited(request: Request) -> None:
    # A dependency, so it answers 429 before the event stream starts.
    addr = request.client.host if request.client else "unknown"
    if not _allow(_GUIDES, addr, GUIDE_LIMIT, GUIDE_WINDOW):
        raise ApiError(429, "too_many_questions", "Too many questions, try again in a few minutes")


@router.post("/agent", response_class=EventSourceResponse, dependencies=[Depends(_limited)])
async def guide(body: GuideIn) -> AsyncIterable[ServerSentEvent]:
    ctx = GuideContext(None, tips=[t for t in body.tips if re.fullmatch(r"[\w-]{10,64}", t)])
    async for event in tool_loop(
        ctx,
        conversation(GUIDE_SYSTEM, body),
        GUIDE_TOOLS,
        GUIDE_STEPS,
        guard=Guard(
            refusal=GUIDE_REFUSAL[body.lang],
            verdict_needs_cites=True,
            no_verdict=GUIDE_NO_VERDICT[body.lang],
        ),
        max_tokens=1500,  # gpt-oss reasons inside this budget
    ):
        yield event
