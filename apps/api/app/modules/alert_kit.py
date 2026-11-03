"""« Kit d'alerte » (brief 6.4): what a newsroom says, and to whom, while a dangerous rumour runs.

On an alert, `POST …/alerts/{id}/kit` drafts, from the alert's own evidence only (its reports and
the facts code counted), five parts: « Ce qu'on sait », « Ce qu'on ne sait pas », « À dire à
l'antenne » (a careful script, French and Malagasy), « Qui appeler » (police, gendarmerie, local
authorities, BNGRC… from the Annuaire, for the alert's regions) and « À ne pas dire ».

One model call in JSON mode writes the texts; code then guards them:
- any personal name found around the accusation (the danger reasons, the sentences that accuse)
  is replaced by « la personne mise en cause », in every part;
- a sentence with a number that is not in the evidence is dropped;
- a script sentence with alarm words (urgent, scandale, « partagez »…) is dropped;
- « Qui appeler » is built by code from the Annuaire, numbers as the newsroom entered them, never
  written by the model; « Personne au carnet » when no entry fits.
With « Mode sans IA », or when no model answers, the kit is a template written from the facts.

The draft is a reading (dashed) until a journalist edits or approves it (solid, logged). An
approved kit is sent to the desk (live event, Ma rubrique) and to the partner radios of those
regions: each radio becomes a truth stop of the alert on « Le trajet », with ready WhatsApp/SMS
links (Checky sends nothing itself). The Malagasy script leaves only after « Relu en malgache »,
bound to the exact text.
"""

import json
import logging
import re
import urllib.parse
import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import ai, places, tone
from app.core.access import AnyMember, Db, Member
from app.core.activity import broadcast, record
from app.core.errors import ApiError
from app.core.models import Contact, Item, RadioPartner, Route, Workspace
from app.modules.alerts import AlertOut, _get_alert, _members, alert_out
from app.modules.veille import canonical_region

log = logging.getLogger("checky.alert_kit")
router = APIRouter(tags=["alerts"])

ACCUSED_FR = "la personne mise en cause"
ACCUSED_MG = "ilay olona voatonona"  # relire (mg)

# « Qui appeler »: the offices that act on a dangerous rumour, by the words their entry carries.
CALL_WORDS: dict[str, tuple[str, ...]] = {
    "police": ("police", "polisy", "commissariat", "commissaire"),
    "gendarmerie": ("gendarmerie", "gendarme", "zandary", "zandarimariam", "brigade"),
    "autorités locales": (
        "préfecture", "prefecture", "préfet", "prefet", "mairie", "maire", "commune",
        "région", "region", "gouverneur", "district", "chef de district", "fokontany", "kaominina",
    ),
    "BNGRC": ("bngrc", "risques et catastrophes", "protection civile"),
    "santé": ("santé", "sante", "hôpital", "hopital", "chu", "csb", "pasteur", "ministère de la santé"),
}  # fmt: skip
MAX_CALLS = 5
MAX_LINES = 6

# Sentences that open with a capital but are common words, not names.
NOT_NAMES = {
    "le", "la", "les", "un", "une", "des", "il", "elle", "ils", "on", "selon", "depuis", "hier",
    "ce", "cette", "ces", "nous", "vous", "rien", "aucun", "aucune", "notre", "votre", "radio",
    "police", "gendarmerie", "mairie", "commune", "région", "region", "district", "fokontany",
    "préfecture", "prefecture", "ministère", "ministere", "madagascar", "nilaza", "misy", "ny",
    "tsy", "aza", "ary", "fa", "dia", "ankizy", "zaza", "olona", "mpihaino", "enlèvement",
    "enlevement", "urgent", "alerte", "attention", "info", "message", "démo", "demo", "auditeur",
    "auditrice", "voleur", "voleurs", "mpangalatra", "tsena", "marché", "marche", "lundi",
    "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche", "bngrc", "jirama", "csb",
}  # fmt: skip
NAME = re.compile(r"[A-ZÀ-Ý][a-zà-ÿ'’-]{2,}(?:[ -][A-ZÀ-Ý][a-zà-ÿ'’-]{2,})*")
NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
NEGATION = re.compile(r"\b(ne|n'|n’|pas|jamais|aza|tsy)\b", re.IGNORECASE)

SYSTEM = (
    "Tu aides une rédaction de Madagascar à préparer un « kit d'alerte » sur une rumeur dangereuse "
    "qui circule. Tu écris UNIQUEMENT à partir des éléments numérotés fournis : ce que des "
    "auditeurs, des SMS, des radios ou des signalements ont rapporté. Rien n'est confirmé. "
    "N'invente aucun fait, aucun chiffre, aucun lieu, aucune source. Ne nomme jamais une personne "
    "accusée, ni sa famille ni son adresse : écris « la personne mise en cause ». Pas de mots qui "
    "affolent (urgent, catastrophe, scandale), pas d'appel à partager. Le texte à dire à "
    "l'antenne est prudent, deux à quatre phrases, et dit « rien ne confirme à ce stade… » ; il "
    "demande de ne pas se faire justice et de ne pas relayer le message. Réponds en JSON : "
    '{"known": [phrases courtes], "unknown": [phrases courtes], "script_fr": "…", '
    '"script_mg": "… (en malgache)", "dont_say": [phrases courtes]}.'
)


# ----------------------------------------------------------------------------------- evidence
def evidence(alert: Item) -> dict[str, Any]:
    """What the kit may rest on: the alert's reports and the facts code counted."""
    d = alert.data or {}
    facts = d.get("facts") or {}
    reports = [
        {
            "n": i + 1,
            "canal": m.get("kind"),
            "radio": m.get("station"),
            "lieu": m.get("place") or m.get("region"),
            "texte": f"{m.get('title') or ''}. {m.get('excerpt') or ''}".strip(" ."),
        }
        for i, m in enumerate(_members(alert)[:12])
    ]
    first = facts.get("first_at")
    hours = None
    if first:
        try:
            hours = int((datetime.now(UTC) - datetime.fromisoformat(first)).total_seconds() // 3600)
        except ValueError:
            hours = None
    return {
        "reports": reports,
        "count": int(facts.get("reports") or len(reports)),
        "stations": list(facts.get("stations") or []),
        "regions": list(facts.get("regions") or []),
        "hours": hours,
        "reasons": [r.get("kind") for r in (d.get("risk") or {}).get("reasons") or [] if r],
    }


def allowed_numbers(ev: dict[str, Any]) -> set[str]:
    """Every number the kit may say: those in the reports and the counts code made."""
    text = " ".join(r["texte"] for r in ev["reports"])
    found = {n.replace(",", ".") for n in NUMBER.findall(text)}
    counts = [ev["count"], len(ev["stations"]), len(ev["regions"]), ev["hours"]]
    return found | {str(c) for c in counts if c is not None}


def accused_names(alert: Item) -> set[str]:
    """Personal names around the accusation: in the « accusation » danger reasons, and in the
    reports' sentences that accuse someone (the tone lexicon). Places, offices and common words
    are left out. A name and each of its parts are returned, so « Rakoto » alone is caught too."""
    d = alert.data or {}
    reasons = [
        r
        for key in ("risk", "risk_override")
        for r in ((d.get(key) or {}).get("reasons") or [])
        if isinstance(r, dict) and r.get("kind") == "accusation"
    ]
    texts = [str(r.get("quote") or "") for r in reasons]
    for m in _members(alert):
        for sentence in re.split(
            r"(?<=[.!?…])\s+|\n+", f"{m.get('title') or ''}. {m.get('excerpt') or ''}"
        ):
            if tone._find(sentence, tone.ACCUSATION):
                texts.append(sentence)
    places_seen = {
        places.fold(w) for m in _members(alert) for w in (m.get("place"), m.get("region")) if w
    }
    out: set[str] = set()
    for text in texts:
        for match in NAME.finditer(text):
            parts = [p for p in re.split(r"[ -]", match.group(0)) if p]
            kept = [
                p
                for p in parts
                if places.fold(p) not in NOT_NAMES
                and places.fold(p) not in places_seen
                and not places.gazetteer(p)
            ]
            if not kept:
                continue
            # A sentence's first word is a name only when it looks Malagasy (Ra…, Andria…) or
            # comes with another capitalised word.
            at_start = match.start() == 0 or text[: match.start()].rstrip().endswith(
                (".", "!", "?")
            )
            if at_start and len(kept) == 1 and not re.match(r"(Ra|Andria|Ran)", kept[0]):
                continue
            out.add(" ".join(kept))
            out |= {p for p in kept if len(p) >= 3}
    return out


def strip_names(text: str, names: set[str], replacement: str) -> tuple[str, int]:
    count = 0
    for name in sorted(names, key=len, reverse=True):
        text, n = re.subn(
            rf"(?<!\w){re.escape(name)}(?!\w)", replacement, text, flags=re.IGNORECASE
        )
        count += n
    # « la personne mise en cause la personne mise en cause » after a first and a last name
    text = re.sub(rf"(?:{re.escape(replacement)}[\s,]*){{2,}}", replacement + " ", text)
    return re.sub(r"\s{2,}", " ", text).strip(), count


def sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?…])\s+", text or "") if s.strip()]


def _unbacked(sentence: str, numbers: set[str]) -> bool:
    return any(n.replace(",", ".") not in numbers for n in NUMBER.findall(sentence))


def _alarming(sentence: str) -> bool:
    if "!" in sentence or any(e in sentence for e in tone.ALARM_EMOJI):
        return True
    for words in (tone.URGENCY, tone.EMOTIVE, tone.HIDDEN, tone.VIOLENCE):
        if tone._find(sentence, words):
            return True
    # « Partagez » is an alarm; « ne partagez pas » is the advice.
    return bool(tone._find(sentence, tone.SHARE)) and not NEGATION.search(sentence)


def guard(kit: dict[str, Any], alert: Item, ev: dict[str, Any]) -> dict[str, Any]:
    """The code rules every kit obeys, whoever wrote it. Returns the kit and what was removed."""
    names = accused_names(alert)
    numbers = allowed_numbers(ev)
    removed = {"names": 0, "numbers": 0, "alarm": 0}

    def clean(text: str, lang: str, script: bool = False) -> str:
        text, n = strip_names(text, names, ACCUSED_MG if lang == "mg" else ACCUSED_FR)
        removed["names"] += n
        kept = []
        for s in sentences(text):
            if _unbacked(s, numbers):
                removed["numbers"] += 1
            elif script and _alarming(s):
                removed["alarm"] += 1
            else:
                kept.append(s)
        return " ".join(kept)

    out = dict(kit)
    for key in ("known", "unknown"):
        out[key] = [x for x in (clean(s, "fr") for s in kit.get(key) or []) if x][:MAX_LINES]
    out["script"] = {
        "fr": clean((kit.get("script") or {}).get("fr") or "", "fr", script=True),
        "mg": clean((kit.get("script") or {}).get("mg") or "", "mg", script=True),
    }
    # « À ne pas dire » is advice: names go, numbers may not be repeated there either.
    out["dont_say"] = [x for x in (clean(s, "fr") for s in kit.get("dont_say") or []) if x]
    out["guards"] = removed
    return out


# ----------------------------------------------------------------------------------- template
def _join(items: list[str]) -> str:
    return items[0] if len(items) == 1 else f"{', '.join(items[:-1])} et {items[-1]}"


def _since(hours: int | None) -> str:
    if hours is None:
        return ""
    if hours < 1:
        return " depuis moins d'une heure"
    return f" depuis {hours} heure{'s' if hours > 1 else ''}"


DONT_SAY = [
    "Le nom de la personne mise en cause, ni sa famille, ni son quartier.",
    "Un chiffre que personne n'a vérifié (victimes, montants, nombre de cas).",
    "Des mots qui affolent : « urgent », « catastrophe », « partagez vite ».",
    "« C'est faux » tant qu'aucun verdict n'est signé : dites « rien ne confirme à ce stade ».",
]
KIND_FR = {
    "clip": "radio", "sms": "SMS", "tip": "signalement", "press": "presse", "item": "dossier",
    "veilleur": "veilleur", "web": "web",
}  # fmt: skip


def template(alert: Item, ev: dict[str, Any]) -> dict[str, Any]:
    """The kit from the facts only (« Mode sans IA », or no model answered)."""
    regions = ev["regions"]
    where = (
        f" dans {'la région' if len(regions) == 1 else 'les régions'} {_join(regions)}"
        if regions
        else ""
    )
    kinds = sorted({KIND_FR.get(r["canal"] or "", r["canal"] or "") for r in ev["reports"]} - {""})
    known = [
        f"« {alert.title.rstrip('.')} » : {ev['count']} élément{'s' if ev['count'] > 1 else ''} regroupé{'s' if ev['count'] > 1 else ''}{_since(ev['hours'])}."
    ]
    if kinds:
        known.append(f"Canaux : {', '.join(kinds)}.")
    if ev["stations"]:
        known.append(f"Entendu sur {_join(ev['stations'])}.")
    if regions:
        known.append(f"Signalé{where}.")
    unknown = [
        "Aucune source officielle ne confirme ces faits à ce stade.",
        "Personne n'a vérifié sur place ce qui s'est passé.",
        "On ne sait pas d'où vient le premier message.",
    ]
    script_fr = (
        f"Une information circule{where}{_since(ev['hours'])}. Rien ne confirme à ce stade qu'elle "
        "soit vraie. Notre rédaction vérifie auprès des autorités. Ne relayez pas ce message et ne "
        "vous faites pas justice vous-même : appelez la police ou la gendarmerie."
    )
    mg_where = f" any amin'ny faritra {_join(regions).replace(' et ', ' sy ')}" if regions else ""
    script_mg = (  # relire (mg)
        f"Misy vaovao miely{mg_where}. Tsy misy manamarina izany hatreto. Manamarina amin'ny "
        "manampahefana ny mpanao gazety. Aza mampiely io hafatra io ary aza manao fitsarana "
        "an-tanana: antsoy ny polisy na ny zandary."
    )
    return {
        "known": known,
        "unknown": unknown,
        "script": {"fr": script_fr, "mg": script_mg},
        "dont_say": list(DONT_SAY),
    }


# ----------------------------------------------------------------------------------- who to call
async def who_to_call(db: AsyncSession, ws: uuid.UUID, regions: list[str]) -> list[dict[str, Any]]:
    """Police, gendarmerie, local authorities, BNGRC, health… from the Annuaire: those of the
    alert's regions first, then national ones. Numbers exactly as the newsroom entered them."""
    from app.modules.directory import NOT_ASKED, _visible

    wanted = {places.fold(canonical_region(r) or r) for r in regions}
    rows = await db.scalars(select(Contact).where(_visible(ws), Contact.kind.notin_(NOT_ASKED)))
    found = []
    for c in rows:
        about = places.fold(
            " ".join([c.name, c.institution or "", c.role or "", *(c.topics or [])])
        )
        office = next(
            (
                label
                for label, hints in CALL_WORDS.items()
                if any(
                    re.search(rf"(?<!\w){re.escape(places.fold(h))}(?!\w)", about) for h in hints
                )
            ),
            None,
        )
        if office is None:
            continue
        region = places.region_of(c.location)
        if region and wanted and places.fold(region) not in wanted:
            continue
        local = bool(region) and places.fold(region) in wanted
        found.append(
            (
                (2 if local else 0) + (1 if c.verified_at else 0) + (0.5 if c.phone else 0),
                {
                    "contact_id": str(c.id),
                    "name": c.name,
                    "institution": c.institution or "",
                    "role": c.role or "",
                    "office": office,
                    "region": region,
                    "phone": c.phone,
                    "whatsapp": c.whatsapp,
                    "why": " · ".join([office, region or "national"]),
                    "is_demo": bool(c.is_demo),
                },
            )
        )
    found.sort(key=lambda x: -x[0])
    out, offices = [], set()
    # One of each office first, then the rest.
    for _, c in found:
        if c["office"] not in offices:
            out.append(c)
            offices.add(c["office"])
    out += [c for _, c in found if c not in out]
    return out[:MAX_CALLS]


# ----------------------------------------------------------------------------------- drafting
def _lines(value: Any) -> list[str]:
    if isinstance(value, str):
        value = [value]
    return [
        " ".join(str(v).split())[:400]
        for v in value or []
        if isinstance(v, str | int | float) and str(v).strip()
    ]


async def _model_kit(alert: Item, ev: dict[str, Any], ws: uuid.UUID) -> tuple[dict, dict]:
    prompt = {
        "alerte": alert.title,
        "elements": ev["reports"],
        "faits": {
            "nombre_d_elements": ev["count"],
            "radios": ev["stations"],
            "regions": ev["regions"],
            "heures_depuis_le_premier": ev["hours"],
            "dangers": ev["reasons"],
        },
    }
    reply = await ai.complete(
        [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
        ],
        workspace_id=ws,
        temperature=0.2,
        response_format={"type": "json_object"},
    )
    m = re.search(r"\{.*\}", reply.content or "", re.DOTALL)
    if not m:
        raise ValueError("no JSON")
    raw = json.loads(m.group(0))
    kit = {
        "known": _lines(raw.get("known")),
        "unknown": _lines(raw.get("unknown")),
        "script": {
            "fr": " ".join(str(raw.get("script_fr") or "").split())[:1200],
            "mg": " ".join(str(raw.get("script_mg") or "").split())[:1200],
        },
        "dont_say": _lines(raw.get("dont_say")),
    }
    return kit, {"provider": reply.provider, "model": reply.model}


async def draft(db: AsyncSession, member: Member, alert: Item, use_ai: bool) -> dict[str, Any]:
    ev = evidence(alert)
    base = template(alert, ev)
    workspace = await db.get(Workspace, member.workspace_id)
    newsroom_ai = (workspace.settings or {}).get("ai_enabled", True) if workspace else True
    written_by, meta = "template", {}
    kit = base
    if use_ai and newsroom_ai:
        try:
            got, meta = await _model_kit(alert, ev, member.workspace_id)
            written_by = "model"
            kit = got
        except (ai.AiUnavailable, ValueError, json.JSONDecodeError) as e:
            log.info("alert kit: no model answer, template kit (%s)", e)
            written_by, meta = "template", {"fallback": True}
    kit = guard(kit, alert, ev)
    # A part the model left empty, or the guards emptied, comes from the facts.
    for key in ("known", "unknown"):
        kit[key] = kit[key] or base[key]
    for lang in ("fr", "mg"):
        kit["script"][lang] = kit["script"][lang] or base["script"][lang]
    kit["dont_say"] = list(dict.fromkeys([*DONT_SAY, *kit["dont_say"]]))[: MAX_LINES + 2]
    return {
        **kit,
        "call": await who_to_call(db, member.workspace_id, ev["regions"]),
        "status": "draft",
        "written_by": written_by,
        **meta,
        "drafted_by": member.user.id,
        "drafted_at": datetime.now(UTC).isoformat(),
        "basis": {"reports": ev["count"]},
        "sent": [],
    }


# ----------------------------------------------------------------------------------- reading
class CallOut(BaseModel):
    contact_id: str
    name: str
    institution: str = ""
    role: str = ""
    office: str
    region: str | None = None
    phone: str | None = None
    whatsapp: str | None = None
    why: str = ""
    is_demo: bool = False


class Script(BaseModel):
    fr: str = ""
    mg: str = ""


class SentOut(BaseModel):
    at: datetime
    by: str
    radios: list[dict[str, Any]]
    mg: bool
    desks: bool


class Relu(BaseModel):
    by: str
    name: str
    at: datetime
    current: bool


class KitOut(BaseModel):
    status: Literal["draft", "approved"]
    written_by: str
    provider: str | None = None
    model: str | None = None
    fallback: bool = False
    known: list[str]
    unknown: list[str]
    script: Script
    call: list[CallOut]
    dont_say: list[str]
    guards: dict[str, int] = Field(default_factory=dict)
    drafted_at: datetime
    approved_by: str | None = None
    approved_name: str | None = None
    approved_at: datetime | None = None
    edited: bool = False
    stale: bool = False  # new reports joined the alert since the draft
    relu_mg: Relu | None = None
    mg_hash: str | None = None
    sent: list[SentOut] = Field(default_factory=list)


class RadioChoice(BaseModel):
    id: uuid.UUID
    name: str
    station: str
    region: str | None
    languages: list[str]
    in_region: bool
    sent: bool
    has_contact: bool
    is_demo: bool


class StopOut(BaseModel):
    id: uuid.UUID
    channel: str
    place: str
    status: str
    at: datetime


class KitState(BaseModel):
    alert: AlertOut
    kit: KitOut | None
    radios: list[RadioChoice]
    trajet: list[StopOut]  # the alert's truth stops (kit sent to radios)


def _mg_hash(kit: dict[str, Any]) -> str | None:
    from app.modules.trajet import mg_hash

    mg = (kit.get("script") or {}).get("mg") or ""
    return mg_hash({"script_mg": mg}) if mg else None


def kit_out(alert: Item) -> KitOut | None:
    d = alert.data or {}
    kit = d.get("kit") if isinstance(d.get("kit"), dict) else None
    if not kit:
        return None
    relu = kit.get("relu_mg") if isinstance(kit.get("relu_mg"), dict) else None
    h = _mg_hash(kit)
    facts = d.get("facts") or {}
    return KitOut(
        status="approved" if kit.get("status") == "approved" else "draft",
        written_by=kit.get("written_by") or "template",
        provider=kit.get("provider"),
        model=kit.get("model"),
        fallback=bool(kit.get("fallback")),
        known=list(kit.get("known") or []),
        unknown=list(kit.get("unknown") or []),
        script=Script(**(kit.get("script") or {})),
        call=[CallOut(**c) for c in kit.get("call") or []],
        dont_say=list(kit.get("dont_say") or []),
        guards=kit.get("guards") or {},
        drafted_at=kit.get("drafted_at"),
        approved_by=kit.get("approved_by"),
        approved_name=kit.get("approved_name"),
        approved_at=kit.get("approved_at"),
        edited=bool(kit.get("edited")),
        stale=int(facts.get("reports") or 0) > int((kit.get("basis") or {}).get("reports") or 0),
        relu_mg=Relu(**{**relu, "current": bool(h) and relu.get("mg_hash") == h}) if relu else None,
        mg_hash=h,
        sent=[SentOut(**s) for s in kit.get("sent") or []],
    )


def station_of(r: RadioPartner) -> str:
    return f"{r.name} {r.frequency or ''}".strip()


async def radio_choices(db: AsyncSession, alert: Item) -> list[RadioChoice]:
    regions = {places.fold(r) for r in ((alert.data or {}).get("facts") or {}).get("regions") or []}
    kit = (alert.data or {}).get("kit") or {}
    sent = {str(r.get("id")) for s in kit.get("sent") or [] for r in s.get("radios") or []}
    rows = await db.scalars(
        select(RadioPartner).where(
            RadioPartner.workspace_id == alert.workspace_id, RadioPartner.approved.is_(True)
        )
    )
    out = []
    for r in rows:
        region = places.region_of(r.location)
        out.append(
            RadioChoice(
                id=r.id,
                name=r.name,
                station=station_of(r),
                region=region,
                languages=list(r.languages or []),
                in_region=bool(region) and places.fold(region) in regions,
                sent=str(r.id) in sent,
                has_contact=bool(r.whatsapp or r.sms),
                is_demo=bool(r.is_demo),
            )
        )
    out.sort(key=lambda r: (not r.in_region, r.name.lower()))
    return out


async def _state(db: AsyncSession, alert: Item) -> KitState:
    stops = await db.scalars(
        select(Route).where(Route.item_id == alert.id, Route.side == "truth").order_by(Route.at)
    )
    return KitState(
        alert=alert_out(alert),
        kit=kit_out(alert),
        radios=await radio_choices(db, alert),
        trajet=[
            StopOut(id=s.id, channel=s.channel, place=s.place, status=s.status, at=s.at)
            for s in stops
        ],
    )


async def _save(
    db: AsyncSession, member: Member, alert: Item, kit: dict, action: str, diff: dict
) -> KitState:
    alert.data = {**(alert.data or {}), "kit": kit}
    await record(db, member.workspace_id, member.user.id, "alert", alert.id, action, diff)
    await db.commit()
    await db.refresh(alert)
    await broadcast(member.workspace_id, "alert.updated", alert_out(alert).model_dump(mode="json"))
    return await _state(db, alert)


def _kit(alert: Item) -> dict[str, Any]:
    kit = (alert.data or {}).get("kit")
    if not isinstance(kit, dict):
        raise ApiError(404, "no_kit", "No alert kit yet: prepare it first")
    return dict(kit)


# ----------------------------------------------------------------------------------- routes
@router.get("/workspaces/{ws}/alerts/{alert_id}/kit")
async def get_kit(alert_id: uuid.UUID, member: AnyMember, db: Db) -> KitState:
    return await _state(db, await _get_alert(db, member, alert_id))


class DraftIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ai: bool = True  # false: « Mode sans IA » for this kit


@router.post("/workspaces/{ws}/alerts/{alert_id}/kit")
async def prepare_kit(alert_id: uuid.UUID, body: DraftIn, member: AnyMember, db: Db) -> KitState:
    """« Préparer le kit d'alerte »: a new reading (dashed), replacing an earlier one. What was
    already sent stays on record."""
    alert = await _get_alert(db, member, alert_id)
    if alert.status == "closed":
        raise ApiError(409, "alert_closed", "This alert is closed")
    previous = (alert.data or {}).get("kit") or {}
    kit = await draft(db, member, alert, body.ai)
    kit["sent"] = list(previous.get("sent") or [])
    return await _save(
        db, member, alert, kit, "kit_draft",
        {"written_by": kit["written_by"], "guards": kit.get("guards") or {}},
    )  # fmt: skip


class KitEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    known: list[str] | None = Field(default=None, max_length=12)
    unknown: list[str] | None = Field(default=None, max_length=12)
    script_fr: str | None = Field(default=None, max_length=2000)
    script_mg: str | None = Field(default=None, max_length=2000)
    dont_say: list[str] | None = Field(default=None, max_length=12)
    call_ids: list[str] | None = Field(default=None, max_length=10)  # entries kept, in order


@router.put("/workspaces/{ws}/alerts/{alert_id}/kit")
async def approve_kit(alert_id: uuid.UUID, body: KitEdit, member: AnyMember, db: Db) -> KitState:
    """A journalist's edit, or a plain approval (empty body): the kit becomes theirs (solid).
    The accused's name still never stays in it; a changed Malagasy script needs a new reread."""
    from app.modules.signing import names

    alert = await _get_alert(db, member, alert_id)
    kit = _kit(alert)
    edited = False
    alert_names = accused_names(alert)
    for key in ("known", "unknown", "dont_say"):
        value = getattr(body, key)
        if value is not None:
            lines = [strip_names(" ".join(v.split()), alert_names, ACCUSED_FR)[0] for v in value]
            lines = [x for x in lines if x]
            edited |= lines != kit.get(key)
            kit[key] = lines
    script = dict(kit.get("script") or {})
    for lang, value in (("fr", body.script_fr), ("mg", body.script_mg)):
        if value is not None:
            text = strip_names(
                " ".join(value.split()), alert_names, ACCUSED_MG if lang == "mg" else ACCUSED_FR
            )[0]
            edited |= text != script.get(lang)
            script[lang] = text
    kit["script"] = script
    if body.call_ids is not None:
        by_id = {c["contact_id"]: c for c in kit.get("call") or []}
        calls = [by_id[i] for i in body.call_ids if i in by_id]
        edited |= calls != kit.get("call")
        kit["call"] = calls
    if not (script.get("fr") or "").strip():
        raise ApiError(422, "script_required", "The script to say on air cannot be empty")
    name = (await names(db, [member.user.id])).get(member.user.id) or member.user.email or ""
    kit.update(
        status="approved",
        approved_by=member.user.id,
        approved_name=name,
        approved_at=datetime.now(UTC).isoformat(),
        edited=bool(kit.get("edited")) or edited,
    )
    return await _save(db, member, alert, kit, "kit_approve", {"edited": edited})


class ReluIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mg_hash: str = Field(min_length=64, max_length=64)


@router.post("/workspaces/{ws}/alerts/{alert_id}/kit/relu-mg")
async def kit_relu(alert_id: uuid.UUID, body: ReluIn, member: AnyMember, db: Db) -> KitState:
    """« Relu en malgache »: vouches for the exact Malagasy script on screen."""
    from app.modules.signing import names

    alert = await _get_alert(db, member, alert_id)
    kit = _kit(alert)
    h = _mg_hash(kit)
    if not h or body.mg_hash != h:
        raise ApiError(409, "mg_changed", "The Malagasy script changed: read it again")
    name = (await names(db, [member.user.id])).get(member.user.id) or member.user.email or ""
    kit["relu_mg"] = {
        "by": member.user.id,
        "name": name,
        "at": datetime.now(UTC).isoformat(),
        "mg_hash": h,
    }
    return await _save(db, member, alert, kit, "kit_relu_mg", {"mg_hash": h})


@router.delete("/workspaces/{ws}/alerts/{alert_id}/kit/relu-mg")
async def kit_unrelu(alert_id: uuid.UUID, member: AnyMember, db: Db) -> KitState:
    alert = await _get_alert(db, member, alert_id)
    kit = _kit(alert)
    if kit.pop("relu_mg", None) is None:
        return await _state(db, alert)
    return await _save(db, member, alert, kit, "kit_relu_mg", {"cleared": True})


class SendIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    radio_ids: list[uuid.UUID] = Field(default_factory=list, max_length=40)
    desks: bool = True


class RadioLink(BaseModel):
    radio_id: uuid.UUID
    station: str
    whatsapp: str | None = None
    sms: str | None = None


class SendOut(BaseModel):
    state: KitState
    links: list[RadioLink]
    message: str
    mg: bool


def message(alert: Item, kit: dict[str, Any], newsroom: str, mg: bool) -> str:
    ref = (alert.data or {}).get("ref") or ""
    script = kit.get("script") or {}
    parts = [
        f"{ref} · Kit d'alerte · {newsroom}".strip(" ·"),
        f"À dire à l'antenne :\n{script.get('fr') or ''}",
    ]
    if mg and script.get("mg"):
        parts.append(f"Amin'ny teny malagasy :\n{script['mg']}")
    if kit.get("dont_say"):
        parts.append("À ne pas dire :\n" + "\n".join(f"- {x}" for x in kit["dont_say"]))
    return "\n\n".join(parts)


def _digits(phone: str | None) -> str:
    return re.sub(r"\D", "", phone or "")


@router.post("/workspaces/{ws}/alerts/{alert_id}/kit/send")
async def send_kit(alert_id: uuid.UUID, body: SendIn, member: AnyMember, db: Db) -> SendOut:
    """« Envoyer »: the approved kit goes to the desk (live event, Ma rubrique) and to the chosen
    partner radios. Each radio is a truth stop of the alert on « Le trajet » (sent from the
    journalist's own phone through the ready links). Malagasy only once reread, exactly."""
    from app.modules import trajet

    alert = await _get_alert(db, member, alert_id)
    kit = _kit(alert)
    if kit.get("status") != "approved":
        raise ApiError(409, "kit_not_approved", "A journalist approves the kit before it is sent")
    if not body.radio_ids and not body.desks:
        raise ApiError(422, "nowhere", "Choose the desk or at least one radio")
    radios = []
    if body.radio_ids:
        rows = await db.scalars(
            select(RadioPartner).where(
                RadioPartner.id.in_(body.radio_ids),
                RadioPartner.workspace_id == member.workspace_id,
                RadioPartner.approved.is_(True),
            )
        )
        radios = list(rows)
        if len(radios) != len(set(body.radio_ids)):
            raise ApiError(404, "not_found", "Radio not found")
    relu = kit.get("relu_mg") if isinstance(kit.get("relu_mg"), dict) else None
    h = _mg_hash(kit)
    mg = bool(relu and h and relu.get("mg_hash") == h)
    workspace = await db.get(Workspace, member.workspace_id)
    text = message(alert, kit, workspace.name if workspace else "", mg)
    links = []
    for r in radios:
        await trajet.add_stop(
            db,
            member.workspace_id,
            alert.id,
            side="truth",
            channel="radio",
            place=station_of(r),
            location=r.location or {},
            proof={
                "method": "kit",
                "radio_id": str(r.id),
                "formats": ["kit_fr", *(["kit_mg"] if mg else [])],
                "mg_hash": h if mg else None,
            },
            status="sent",
            added_by=member.user.id,
            auto=False,
        )
        quoted = urllib.parse.quote(text)
        wa, sms = _digits(r.whatsapp), _digits(r.sms)
        links.append(
            RadioLink(
                radio_id=r.id,
                station=station_of(r),
                whatsapp=f"https://wa.me/{wa}?text={quoted}" if wa else None,
                sms=f"sms:+{sms}?body={quoted}" if sms else None,
            )
        )
    now = datetime.now(UTC).isoformat()
    kit["sent"] = [
        *(kit.get("sent") or []),
        {
            "at": now,
            "by": member.user.id,
            "radios": [{"id": str(r.id), "station": station_of(r)} for r in radios],
            "mg": mg,
            "desks": body.desks,
        },
    ]
    state = await _save(
        db, member, alert, kit, "kit_send",
        {"radios": [station_of(r) for r in radios], "desks": body.desks, "mg": mg},
    )  # fmt: skip
    if body.desks:
        await broadcast(
            member.workspace_id,
            "alert.kit",
            {
                "id": str(alert.id),
                "ref": (alert.data or {}).get("ref"),
                "title": alert.title,
                "script_fr": (kit.get("script") or {}).get("fr"),
                "regions": state.alert.facts.regions,
            },
        )
    if radios:
        await broadcast(member.workspace_id, "route.added", {"item_id": str(alert.id)})
    return SendOut(state=state, links=links, message=text, mg=mg)


# ------------------------------------------------------------ « Diffuser » proposes the radios
class ProposedRoute(BaseModel):
    channel: str
    place: str
    location: dict[str, Any]


class AlertRadios(BaseModel):
    alert_id: uuid.UUID
    ref: str | None
    state: str
    closed: dict[str, Any] | None
    routes: list[ProposedRoute]


@router.get("/workspaces/{ws}/items/{item_id}/alert-radios")
async def alert_radios(item_id: uuid.UUID, member: AnyMember, db: Db) -> list[AlertRadios]:
    """The radios « Diffuser » proposes on a dossier: those the kit of its alerts went to, or else
    the partner radios of those alerts' regions."""
    key = f"item:{item_id}"
    alerts = await db.scalars(
        select(Item).where(Item.workspace_id == member.workspace_id, Item.type == "alert")
    )
    out = []
    for alert in alerts:
        if key not in {m.get("key") for m in _members(alert)}:
            continue
        kit = (alert.data or {}).get("kit") or {}
        sent_ids = {str(r.get("id")) for s in kit.get("sent") or [] for r in s.get("radios") or []}
        choices = await radio_choices(db, alert)
        picked = [c for c in choices if str(c.id) in sent_ids] or [
            c for c in choices if c.in_region
        ]
        if not picked:
            continue
        by_id = {
            r.id: r
            for r in await db.scalars(
                select(RadioPartner).where(RadioPartner.id.in_([c.id for c in picked]))
            )
        }
        out.append(
            AlertRadios(
                alert_id=alert.id,
                ref=(alert.data or {}).get("ref"),
                state="closed" if alert.status == "closed" else "open",
                closed=(alert.data or {}).get("closed"),
                routes=[
                    ProposedRoute(
                        channel="radio", place=c.station, location=by_id[c.id].location or {}
                    )
                    for c in picked
                    if c.id in by_id
                ],
            )
        )
    return out
