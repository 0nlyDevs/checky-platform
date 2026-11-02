"""Demo data for the pitch: plausible public claims, clearly synthetic (M12)."""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter
from sqlalchemy import delete

from app.core.access import Admin, Db
from app.core.activity import broadcast
from app.core.models import Item

router = APIRouter(tags=["demo"])

# (minutes ago first seen, title, status, verdict, suggested verdict, origin, source count, tags)
DEMO_CLAIMS = [
    (
        365,
        "Le ministère de la Santé confirme 3 cas de peste à Ambositra",
        "published",
        "true",
        None,
        "press",
        5,
        ["santé"],
    ),
    (
        320,
        "Une vidéo montre l'inondation d'Analakely ce matin",
        "verified",
        "false",
        None,
        "whatsapp",
        3,
        ["météo", "vidéo"],
    ),
    (
        275,
        "Le prix du riz vary gasy a doublé à Antananarivo depuis septembre",
        "in_progress",
        None,
        "misleading",
        "facebook",
        4,
        ["économie"],
    ),
    (
        190,
        "Le bac 2026 serait reporté au 15 décembre",
        "in_progress",
        None,
        "unverifiable",
        "whatsapp",
        1,
        ["éducation"],
    ),
    (
        115,
        "La JIRAMA annonce 12 h de délestage par jour à Toamasina",
        "to_check",
        None,
        None,
        "facebook",
        0,
        ["énergie"],
    ),
    (
        45,
        "Un audio WhatsApp attribue des propos au maire de Mahajanga",
        "in_progress",
        None,
        None,
        "whatsapp",
        0,
        ["politique", "audio"],
    ),
    (
        20,
        "Le pont de Mangasoavina serait fermé jusqu'à lundi",
        "to_check",
        None,
        None,
        "radio",
        0,
        ["transport"],
    ),
    (
        1500,
        "Un nouveau billet de 20 000 ariary entre en circulation",
        "verified",
        "false",
        None,
        "tiktok",
        2,
        ["économie"],
    ),
]


@router.post("/workspaces/{ws}/demo/reset")
async def reset_demo(admin: Admin, db: Db) -> dict:
    await db.execute(delete(Item).where(Item.workspace_id == admin.workspace_id))
    now = datetime.now(UTC)
    for i, (ago, title, status, verdict, suggested, origin, sources, tags) in enumerate(
        DEMO_CLAIMS
    ):
        db.add(
            Item(
                workspace_id=admin.workspace_id,
                author_id=admin.user.id,
                type="claim",
                title=title,
                status=status,
                tags=tags,
                data={
                    "ref": f"FAN-{137 + i:04d}",
                    "first_seen_at": (now - timedelta(minutes=ago)).isoformat(),
                    "origin": origin,
                    "verdict": verdict,
                    "verdict_suggested": suggested,
                    "source_count": sources,
                    "demo": True,
                },
            )
        )
    await db.commit()
    await broadcast(admin.workspace_id, "demo.reset", {})
    return {"items": len(DEMO_CLAIMS)}
