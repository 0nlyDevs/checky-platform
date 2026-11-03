"""Demo data for the pitch: plausible public claims, clearly synthetic (M12)."""

import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter
from sqlalchemy import delete, select

from app.core import dates
from app.core.access import AnyMember, Db
from app.core.activity import broadcast, record
from app.core.models import Item, Source, Workspace
from app.modules import signing

log = logging.getLogger("checky.demo")
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
    # The rumour the pitch follows from birth to the fokontany poster (FAN-0145): a video of 2023
    # and a doctored JIRAMA communiqué (the registry holds the original: 4 hours a day, not 72).
    (
        430,
        "72 heures de délestage dès demain sur tout Antananarivo, selon la JIRAMA",
        "to_check",
        None,
        None,
        "facebook",
        1,
        ["énergie"],
    ),
]

# The circulating text of the demo rumour (pasted into Vérifier during the pitch). Fictional.
DEMO_RUMOUR_TEXT = (
    "URGENT ⚠️ COMMUNIQUÉ N° 2026-118 de la JIRAMA : délestage de 72 heures à partir du 3 novembre "
    "sur tout Antananarivo, hausse de 40 % du tarif en décembre. Partagez à tous vos contacts !!!"
)


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
    8: (
        "Démo · La vidéo du délestage retrouvée en ligne le 14 mars 2023 (exemple fictif)",
        (
            "La vidéo jointe au message montre des quartiers d'Antananarivo plongés dans le noir. Les "
            "mêmes images ont été mises en ligne le 14 mars 2023 sur la chaîne YouTube d'une télévision "
            "nationale, lors des coupures de mars 2023. Elles ne montrent donc pas la situation de "
            "novembre 2026."
        ),
    ),
}
# The demo video's fictional upload date (the source above is dated to it, not to the rumour).
DEMO_SOURCE_DATES = {8: "2023-03-14"}


# Every newsroom resource module (contacts, originals, figures, routes, clips, prefs, SMS…) may
# export `seed_demo(db, workspace_id, user_id, items)` where `items` maps the demo refs
# (FAN-0137…) to the created claims. Each seed is idempotent and runs on its own: a failure in
# one shelf is logged and never blocks the demo.
SEED_MODULES = (
    "directory",
    "registry",
    "figures",
    "trajet",
    "veille",
    "rubrique",
    "sms",
    "studio",
    "institution",
)


async def seed_extras(db, workspace_id, user_id, items: dict[str, Item]) -> None:
    import importlib

    for name in SEED_MODULES:
        try:
            module = importlib.import_module(f"app.modules.{name}")
        except ImportError:
            continue
        seed = getattr(module, "seed_demo", None)
        if seed is None:
            continue
        try:
            await seed(db, workspace_id, user_id, items)
            await db.commit()
        except Exception:
            log.exception("demo seed %s failed", name)
            await db.rollback()


@router.post("/workspaces/{ws}/demo/reset")
async def reset_demo(member: AnyMember, db: Db) -> dict:
    # The demo newsroom shows its published verdicts and takes public tips, for the pitch.
    ws = await db.get(Workspace, member.workspace_id)
    ws.is_public = True
    # Sources outlive their claim (SET NULL), so the demo's own go first; their passages cascade.
    items = select(Item.id).where(Item.workspace_id == member.workspace_id)
    await db.execute(delete(Source).where(Source.item_id.in_(items)))
    await db.execute(delete(Item).where(Item.workspace_id == member.workspace_id))
    created_sources = []
    by_ref: dict[str, Item] = {}
    now = datetime.now(UTC)
    for i, (ago, title, status, verdict, suggested, origin, sources, tags) in enumerate(
        DEMO_CLAIMS
    ):
        item = Item(
            workspace_id=member.workspace_id,
            author_id=member.user.id,
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
                "assignee_id": member.user.id if status == "in_progress" else None,
                "demo": True,
                **({"reason": DEMO_REASONS[i]} if i in DEMO_REASONS else {}),
            },
        )
        if status == "published" and verdict:
            # A published demo verdict is a signed one: the public page, the seal and the carnet
            # all rest on a signature, so the demo carries the signing journalist's byline.
            at = (now - timedelta(minutes=max(ago - 5, 1))).isoformat()
            who = member.user.name or member.user.email
            item.data = {
                **item.data,
                "reason": item.data.get("reason") or DEMO_REASONS.get(i, ""),
                "signed_by": member.user.id,
                "signed_at": at,
                "published_by": member.user.id,
                "published_at": at,
                "byline": {"newsroom": ws.name, "journalist": who, "signed_at": at},
            }
        db.add(item)
        await db.flush()
        if item.data.get("signed_by"):
            # After the flush, so the body is the stored one (the digest covers it).
            item.data = {
                **item.data,
                "signed_digest": signing.digest(item.title, item.body, item.data),
            }
        by_ref[item.data["ref"]] = item
        await record(db, member.workspace_id, member.user.id, "item", item.id, "create")
        if i in DEMO_SOURCES:
            title, text = DEMO_SOURCES[i]
            source = Source(
                workspace_id=member.workspace_id,
                item_id=item.id,
                created_by=member.user.id,
                kind="text",
                status="ready",
                title=title,
                text=text,
                # Written the day the rumour surfaced, so the checker reads it as current (or the
                # real date of an old video, so the date check sees it is old).
                published_at=DEMO_SOURCE_DATES.get(
                    i, (now - timedelta(minutes=ago)).astimezone(dates.EAT).date().isoformat()
                ),
            )
            db.add(source)
            await db.flush()
            created_sources.append(source.id)
    await db.commit()
    await seed_extras(db, member.workspace_id, member.user.id, by_ref)
    from app.modules.rag import queue_embedding

    for source_id in created_sources:
        await queue_embedding(db, member.workspace_id, member.user.id, source_id)
    await broadcast(member.workspace_id, "demo.reset", {})
    return {"items": len(DEMO_CLAIMS)}
