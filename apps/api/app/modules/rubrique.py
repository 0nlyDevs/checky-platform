"""Personal newsroom desk. Beats are editable interests, never a fixed country taxonomy."""

import re
import uuid

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.access import AnyMember, Db
from app.core.models import DEFAULT_BEATS, Item, MemberPref, Workspace
from app.core.places import fold
from app.modules.items import ItemOut

router = APIRouter(tags=["rubrique"])

# Words that put a text in a beat when nobody tagged it (French, Malagasy, a little English).
# Beats are the newsroom's; a beat with no entry here matches on its own name only.
BEAT_WORDS: dict[str, tuple[str, ...]] = {
    "santé": ("santé", "peste", "choléra", "épidémie", "vaccin", "hôpital", "malade", "paludisme",
              "médicament", "mpox", "pesta", "aretina", "fahasalamana", "eau du robinet",
              "empoisonné", "empoisonnée"),
    "éducation": ("éducation", "bac", "baccalauréat", "examen", "cepe", "bepc", "école", "élèves",
                  "enseignants", "rentrée", "université", "fianarana", "sekoly"),
    "politique": ("politique", "élection", "élections", "ministre", "président", "député",
                  "gouvernement", "ceni", "vote", "maire", "sénat", "fifidianana"),
    "économie": ("économie", "prix", "riz", "vary", "ariary", "salaire", "inflation", "billet",
                 "taxe", "banque", "pénurie", "vidin-javatra"),
    "énergie": ("énergie", "délestage", "jirama", "électricité", "coupure de courant",
                "carburant", "centrale", "tarif", "jiro", "fahatapahan-jiro", "herinaratra",
                "solika"),
    "sécurité": ("sécurité", "enlèvement", "dahalo", "attaque", "police", "gendarmerie",
                 "meurtre", "kidnapping", "braquage", "fakana an-keriny", "mpangalatra"),
    "environnement": ("environnement", "cyclone", "inondation", "crue", "sécheresse", "feux",
                      "forêt", "bngrc", "rivodoza", "tondra-drano"),
    "transport": ("transport", "pont", "route", "taxi-be", "bus", "aéroport", "train", "rn7",
                  "circulation", "lalana"),
    "sport": ("sport", "barea", "match", "football", "rugby", "makis", "baolina"),
    "culture": ("culture", "festival", "concert", "artiste", "musique", "film"),
    "société": ("société", "fokontany", "mariage", "église", "religion", "eau", "logement"),
    "international": ("international", "onu", "oms", "union africaine", "france", "chine",
                      "comores", "maurice"),
}  # fmt: skip


def offered_beats(workspace: Workspace | None) -> list[str]:
    beats = (workspace.settings or {}).get("beats") if workspace else None
    if isinstance(beats, list) and any(isinstance(b, str) and b.strip() for b in beats):
        return [b.strip() for b in beats if isinstance(b, str) and b.strip()]
    return list(DEFAULT_BEATS)


def _contains(folded: str, phrase: str) -> bool:
    return bool(re.search(rf"(?<![a-z0-9]){re.escape(fold(phrase))}(?:s|x)?(?![a-z0-9])", folded))


def beats_for(text: str, offered: list[str]) -> list[str]:
    """The newsroom's beats a text belongs to, by their name or their usual words."""
    folded = fold(text or "")
    if not folded:
        return []
    out = []
    for beat in offered:
        lexicon = BEAT_WORDS.get(beat) or BEAT_WORDS.get(fold(beat)) or (beat,)
        if any(_contains(folded, w) for w in (beat, *lexicon)):
            out.append(beat)
    return out


def _same(a: str, b: str) -> bool:
    return fold(a) == fold(b)


class Interests(BaseModel):
    beats: list[str] = Field(default_factory=list, max_length=20)
    regions: list[str] = Field(default_factory=list, max_length=30)


class RubriqueOut(BaseModel):
    interests: Interests
    items: list[ItemOut]


@router.get("/workspaces/{ws}/rubrique")
async def rubrique(member: AnyMember, db: Db) -> RubriqueOut:
    pref = await db.scalar(
        select(MemberPref).where(
            MemberPref.workspace_id == member.workspace_id, MemberPref.user_id == member.user.id
        )
    )
    interests = Interests(beats=pref.beats, regions=pref.regions) if pref else Interests()
    stmt = select(Item).where(Item.workspace_id == member.workspace_id)
    if interests.beats:
        stmt = stmt.where(Item.tags.overlap(interests.beats))
    return RubriqueOut(
        interests=interests,
        items=[
            ItemOut.model_validate(i)
            for i in await db.scalars(stmt.order_by(Item.updated_at.desc()).limit(30))
        ],
    )


@router.put("/workspaces/{ws}/rubrique")
async def preferences(body: Interests, member: AnyMember, db: Db) -> Interests:
    from sqlalchemy.dialects.postgresql import insert

    await db.execute(
        insert(MemberPref)
        .values(
            id=uuid.uuid4(),
            workspace_id=member.workspace_id,
            user_id=member.user.id,
            beats=body.beats,
            regions=body.regions,
        )
        .on_conflict_do_update(
            index_elements=["workspace_id", "user_id"],
            set_={"beats": body.beats, "regions": body.regions},
        )
    )
    await db.commit()
    return body
