"""Demo data for the pitch: plausible public claims, clearly synthetic (M12)."""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter
from sqlalchemy import delete, select

from app.core import dates
from app.core.access import Admin, Db
from app.core.activity import broadcast, record
from app.core.models import Item, Source, Workspace

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
        "published",
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
        "published",
        "false",
        None,
        "tiktok",
        2,
        ["économie"],
    ),
]


# The reason a journalist wrote for each published demo verdict (shown on the public archive).
DEMO_REASONS = {
    0: "Le communiqué du ministère confirme trois cas, pris en charge au CHRD d'Ambositra.",
    1: "La vidéo date de janvier 2019 : une recherche inversée la retrouve sur Facebook, pendant la saison cyclonique.",
    7: "Aucune nouvelle coupure n'est prévue cette année ; l'image partagée sur TikTok est un montage.",
}

# Sources attached to the demo claims (index in DEMO_CLAIMS → (title, text)), written so the claim
# checker and the Vérifier page have something to conclude from. Clearly labelled as fictional.
DEMO_SOURCES = {
    0: (
        "Démo · Communiqué du ministère de la Santé (exemple fictif)",
        (
            "Le ministère de la Santé publique confirme trois cas de peste bubonique dans le district "
            "d'Ambositra, notifiés entre le 18 et le 22 octobre. Les trois patients sont pris en charge "
            "au CHRD et leur état est stable. Une campagne de désinsectisation est en cours dans les "
            "fokontany concernés."
        ),
    ),
    1: (
        "Démo · Recherche inversée de la vidéo (exemple fictif)",
        (
            "La vidéo partagée sur WhatsApp montre la rue d'Analakely inondée. Une recherche inversée sur "
            "les images clés retrouve la même vidéo publiée sur Facebook le 14 janvier 2019, pendant la "
            "saison cyclonique. Ce matin, seules de faibles pluies ont été relevées sur Antananarivo."
        ),
    ),
    2: (
        "Démo · Relevé des prix du riz (exemple fictif)",
        (
            "Selon le relevé mensuel des prix, le kilo de riz local vary gasy est passé de 2 800 ariary "
            "en septembre à 3 300 ariary en octobre à Antananarivo, soit une hausse d'environ 18 %. "
            "Le riz importé est resté stable autour de 2 900 ariary le kilo."
        ),
    ),
    3: (
        "Démo · Calendrier des examens (exemple fictif)",
        (
            "Le calendrier publié en août prévoit les épreuves écrites du baccalauréat 2026 à partir du "
            "24 novembre. Aucun report n'a été annoncé à ce jour par le ministère de l'Éducation nationale."
        ),
    ),
    4: (
        "Démo · Programme de délestage à Toamasina (exemple fictif)",
        (
            "La JIRAMA annonce pour Toamasina des coupures tournantes de 4 heures par jour et par quartier "
            "cette semaine, en raison d'une panne sur un groupe de la centrale thermique."
        ),
    ),
    6: (
        "Démo · Bulletin d'une radio locale (exemple fictif)",
        (
            "Le pont de Mangasoavina reste ouvert à la circulation, mais il est limité aux véhicules de "
            "moins de 3,5 tonnes jusqu'à lundi, le temps de travaux de consolidation."
        ),
    ),
    7: (
        "Démo · Note de la Banque centrale (exemple fictif)",
        (
            "Les billets en circulation vont de 100 à 20 000 ariary et aucune nouvelle coupure n'est "
            "prévue cette année. Les images d'un « nouveau billet de 20 000 ariary » partagées sur "
            "TikTok sont un montage."
        ),
    ),
}


@router.post("/workspaces/{ws}/demo/reset")
async def reset_demo(admin: Admin, db: Db) -> dict:
    # The demo newsroom shows its published verdicts and takes public tips, for the pitch.
    ws = await db.get(Workspace, admin.workspace_id)
    ws.is_public = True
    # Sources outlive their claim (SET NULL), so the demo's own go first; their passages cascade.
    items = select(Item.id).where(Item.workspace_id == admin.workspace_id)
    await db.execute(delete(Source).where(Source.item_id.in_(items)))
    await db.execute(delete(Item).where(Item.workspace_id == admin.workspace_id))
    created_sources = []
    now = datetime.now(UTC)
    for i, (ago, title, status, verdict, suggested, origin, sources, tags) in enumerate(
        DEMO_CLAIMS
    ):
        item = Item(
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
                "source_count": 1 if i in DEMO_SOURCES else 0,
                "assignee_id": admin.user.id if status == "in_progress" else None,
                "demo": True,
                **({"reason": DEMO_REASONS[i]} if i in DEMO_REASONS else {}),
            },
        )
        db.add(item)
        await db.flush()
        await record(db, admin.workspace_id, admin.user.id, "item", item.id, "create")
        if i in DEMO_SOURCES:
            title, text = DEMO_SOURCES[i]
            source = Source(
                workspace_id=admin.workspace_id,
                item_id=item.id,
                created_by=admin.user.id,
                kind="text",
                status="ready",
                title=title,
                text=text,
                # Written the day the rumour surfaced, so the checker reads it as current.
                published_at=(now - timedelta(minutes=ago))
                .astimezone(dates.EAT)
                .date()
                .isoformat(),
            )
            db.add(source)
            await db.flush()
            created_sources.append(source.id)
    await db.commit()
    from app.modules.rag import queue_embedding

    for source_id in created_sources:
        await queue_embedding(db, admin.workspace_id, admin.user.id, source_id)
    await broadcast(admin.workspace_id, "demo.reset", {})
    return {"items": len(DEMO_CLAIMS)}
