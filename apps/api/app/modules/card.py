"""F5 verdict card: a short shareable post for a claim whose verdict a journalist confirmed.

`POST …/items/{id}/post {language: fr|mg}` writes 2-3 sentences from the claim, the confirmed
verdict, the analysis reason and the sources, and keeps it in `item.data.posts[language]`.
The image card itself is drawn in the browser (apps/web/components/claims/verdict-card.tsx).
"""

import uuid
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from app.core import ai
from app.core.access import AnyMember, Db
from app.core.activity import broadcast
from app.core.errors import ApiError
from app.core.models import Item, Source

router = APIRouter(tags=["card"])

VERDICT_WORDS = {
    "fr": {
        "true": "VRAI",
        "misleading": "TROMPEUR",
        "false": "FAUX",
        "unverifiable": "INVÉRIFIABLE",
    },
    "mg": {
        "true": "MARINA",
        "misleading": "MAMITAKA",
        "false": "DISO",
        "unverifiable": "TSY VOAMARINA",
    },
}
LANGUAGE = {"fr": "français", "mg": "malgache (teny malagasy)"}

SYSTEM = """Tu rédiges le texte qui accompagne une carte de vérification publiée sur Facebook et \
WhatsApp par une rédaction malgache. 2 à 3 phrases, ton calme et factuel, sans emoji ni hashtag. \
Commence par le verdict en majuscules suivi de deux-points. Résume pourquoi, en citant la source \
principale par son nom. N'ajoute aucun fait absent des éléments fournis."""


class PostIn(BaseModel):
    language: Literal["fr", "mg"] = "fr"


class PostOut(BaseModel):
    language: str
    text: str


@router.post("/workspaces/{ws}/items/{item_id}/post")
async def write_post(item_id: uuid.UUID, body: PostIn, member: AnyMember, db: Db) -> PostOut:
    item = await db.get(Item, item_id)
    if item is None or item.workspace_id != member.workspace_id:
        raise ApiError(404, "not_found", "Item not found")
    verdict = item.data.get("verdict")
    if verdict not in VERDICT_WORDS["fr"]:
        raise ApiError(409, "no_verdict", "Confirm a verdict before writing the post")
    sources = list(
        await db.scalars(
            select(Source).where(Source.item_id == item_id).order_by(Source.created_at).limit(5)
        )
    )
    reason = (item.data.get("analysis") or {}).get("reason") or ""
    facts = "\n".join(
        [
            f"Affirmation : {item.title}",
            f"Verdict confirmé par la rédaction : {VERDICT_WORDS[body.language][verdict]}",
            f"Raison : {reason or '(non précisée)'}",
            "Sources : " + ("; ".join(s.title for s in sources) or "(aucune)"),
            f"Langue du texte : {LANGUAGE[body.language]}",
        ]
    )
    try:
        reply = await ai.complete(
            [{"role": "system", "content": SYSTEM}, {"role": "user", "content": facts}],
            workspace_id=member.workspace_id,
            temperature=0.3,
            max_tokens=400,
        )
    except ai.AiUnavailable as e:
        raise ApiError(503, "ai_unavailable", str(e)) from e
    text = reply.content.strip()
    item.data = {**item.data, "posts": {**(item.data.get("posts") or {}), body.language: text}}
    await db.commit()
    await db.refresh(item)
    from app.modules.items import ItemOut

    await broadcast(
        member.workspace_id, "item.updated", ItemOut.model_validate(item).model_dump(mode="json")
    )
    return PostOut(language=body.language, text=text)
