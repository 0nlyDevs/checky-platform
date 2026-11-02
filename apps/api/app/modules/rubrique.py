"""« Ma rubrique »: a journalist's morning page, plus the carnet's Angles and Documents.

A journalist covers beats (énergie, santé…: the newsroom's own list, `workspace.settings.beats`,
or the defaults) and places. The morning page gathers what circulates on them (tips, SMS
questions, radio clips, press items, the desk's open claims), the dossiers waiting for them or for
a signature, who to call, the latest official figures, three angles and the week's « Météo des
rumeurs ». `…/rubrique/brief` says the same as a short text to paste into WhatsApp or an SMS.

Angles (« Explorer un angle ») are the one model call here: grounded in the newsroom's own facts,
each angle must rest on numbered facts and is shown dashed: the AI suggests, a journalist keeps.
"""

import logging
import re
import uuid
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.access import Anyone, Db, Member
from app.core.models import (
    DEFAULT_BEATS,
    MemberPref,
    Workspace,
)
from app.core.places import MG_REGIONS, fold

log = logging.getLogger("checky.rubrique")
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


# ----------------------------------------------------------------------------------- beats
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


# ----------------------------------------------------------------------------------- prefs
class PrefsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    beats: list[str] = Field(default_factory=list, max_length=20)
    # Place names: a region, a town (« Toamasina » counts as Atsinanana), any place in the world.
    regions: list[str] = Field(default_factory=list, max_length=30)
    language: Literal["fr", "mg", "en"] = "fr"
    station: str | None = Field(default=None, max_length=120)  # a veilleur's radio


class PrefsOut(PrefsIn):
    beats_offered: list[str]
    regions_offered: list[str]


async def load_prefs(db: AsyncSession, member: Member) -> MemberPref | None:
    return await db.scalar(
        select(MemberPref).where(
            MemberPref.workspace_id == member.workspace_id, MemberPref.user_id == member.user.id
        )
    )


def _clean(values: list[str], limit: int) -> list[str]:
    out: list[str] = []
    for v in values:
        v = re.sub(r"\s+", " ", v or "").strip()[:80]
        if v and not any(_same(v, o) for o in out):
            out.append(v)
    return out[:limit]


def _prefs_out(pref: MemberPref | None, workspace: Workspace) -> PrefsOut:
    return PrefsOut(
        beats=list(pref.beats or []) if pref else [],
        regions=list(pref.regions or []) if pref else [],
        language=(pref.language if pref and pref.language in ("fr", "mg", "en") else "fr"),
        station=pref.station if pref else None,
        beats_offered=offered_beats(workspace),
        regions_offered=sorted(MG_REGIONS),
    )


@router.get("/workspaces/{ws}/me/prefs")
async def get_prefs(member: Anyone, db: Db) -> PrefsOut:
    return _prefs_out(await load_prefs(db, member), await db.get(Workspace, member.workspace_id))


async def save_prefs(db: AsyncSession, workspace_id: uuid.UUID, user_id: str, body: PrefsIn):
    from app.modules.veille import canonical_region

    beats = _clean(body.beats, 20)
    regions = _clean([canonical_region(r) or r for r in body.regions], 30)
    values = {
        "beats": beats,
        "regions": regions,
        "language": body.language,
        "station": (body.station or "").strip() or None,
    }
    await db.execute(
        insert(MemberPref)
        .values(id=uuid.uuid4(), workspace_id=workspace_id, user_id=user_id, **values)
        .on_conflict_do_update(index_elements=["workspace_id", "user_id"], set_=values)
    )


@router.put("/workspaces/{ws}/me/prefs")
async def put_prefs(body: PrefsIn, member: Anyone, db: Db) -> PrefsOut:
    await save_prefs(db, member.workspace_id, member.user.id, body)
    await db.commit()
    return await get_prefs(member, db)


# -------------------------------------------------------------------------------- the page


# ----------------------------------------------------------------------------------- angles


# -------------------------------------------------------------------------------- documents


# ------------------------------------------------------------------------------- demo seed
