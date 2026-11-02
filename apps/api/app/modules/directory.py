"""The Annuaire and « Qui peut le prouver ? ».

Contacts are curated by the newsroom (or declared by the institutions): who they are, the beats
and places they can settle, the languages they answer in, their official pages and their track
record (kept by code in `stats`). A declared official page is not verified until a journalist checks
it; `official_hosts` returns only checked ones (the crew's credibility grid reads it).

For a dossier, `GET …/items/{id}/who` takes each point the reading says is missing and the claim's
beats and places, and proposes the 1–3 people best placed to settle it, with why and a question
ready to send. `POST …/items/{id}/questions` logs the question and returns ready links (WhatsApp,
SMS, e-mail); the contact answers at `/reponse/{token}` without an account, and the answer becomes
a dated source of the dossier, read again by the checker. Never scraped personal numbers.
"""

import re
import secrets
import time
import unicodedata
import urllib.parse
import uuid
from collections import defaultdict, deque
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict, Field, HttpUrl
from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import dates, places
from app.core.access import AnyMember, Db
from app.core.activity import broadcast, record
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.errors import ApiError
from app.core.models import Contact, ContactRequest, Item, Source, Workspace
from app.core.words import words
from app.modules.items import _get_item
from app.workers.queue import JobContext, enqueue, handler

router = APIRouter(tags=["directory"])

PUBLIC_AUTHOR = "public"  # the contact answering through a token link has no account
Phone = Field(default=None, max_length=60, pattern=r"^\+?[0-9 ()-]{3,60}$")


class OfficialPage(BaseModel):
    # `verified` is never read from a client: a journalist's « Vérifier » sets it on every page of the
    # contact at once, and any edit clears it again (see update_contact).
    model_config = ConfigDict(extra="forbid")
    kind: str = Field(default="site", max_length=30)  # site|facebook|x|youtube|…
    url: HttpUrl


class ContactIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    kind: Literal["institution", "officer", "expert"] = "institution"
    role: str = Field(default="", max_length=200)
    institution: str = Field(default="", max_length=200)
    topics: list[str] = Field(default_factory=list, max_length=20)
    languages: list[str] = Field(default_factory=list, max_length=10)
    # A place in words (« Toamasina », « Atsimo-Andrefana »), geocoded; or the structured place.
    place: str | None = Field(default=None, max_length=200)
    location: dict[str, Any] | None = None
    phone: str | None = Phone
    whatsapp: str | None = Phone
    email: str | None = Field(default=None, max_length=200, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    website: HttpUrl | None = None
    official_pages: list[OfficialPage] = Field(default_factory=list, max_length=10)
    hours: str | None = Field(default=None, max_length=200)
    shared: bool = False


class ContactOut(BaseModel):
    id: uuid.UUID
    name: str
    kind: str
    role: str
    institution: str
    topics: list[str]
    languages: list[str]
    location: dict[str, Any]
    phone: str | None
    whatsapp: str | None
    email: str | None
    website: str | None
    official_pages: list[dict[str, Any]]
    hours: str | None
    shared: bool
    verified_at: datetime | None
    verified_by: str | None
    stats: dict[str, Any]
    is_demo: bool
    # False for a contact another newsroom shared: readable, not editable here.
    own: bool = True


def contact_out(c: Contact, ws: uuid.UUID | None = None) -> ContactOut:
    return ContactOut(
        id=c.id,
        name=c.name,
        kind=c.kind or "institution",
        role=c.role or "",
        institution=c.institution or "",
        topics=list(c.topics or []),
        languages=list(c.languages or []),
        location=c.location or {},
        phone=c.phone,
        whatsapp=c.whatsapp,
        email=c.email,
        website=c.website,
        official_pages=list(c.official_pages or []),
        hours=c.hours,
        shared=bool(c.shared),
        verified_at=c.verified_at,
        verified_by=c.verified_by,
        stats=c.stats or {},
        is_demo=bool(c.is_demo),
        own=ws is None or c.workspace_id == ws,
    )


async def _fields(db: AsyncSession, body: ContactIn, partial: bool = False) -> dict[str, Any]:
    values = body.model_dump(mode="json", exclude_unset=partial)
    place = values.pop("place", None)
    if place:
        values["location"] = await places.geocode(db, place) or {"name": place}
    elif "location" in values:
        values["location"] = values["location"] or {}
    for key in ("topics", "languages"):
        if key in values:
            values[key] = [v.strip()[:60] for v in values[key] if v and v.strip()]
    if "official_pages" in values:
        values["official_pages"] = [
            {**p, "verified": False} for p in values["official_pages"] or []
        ]
    return values


def _visible(ws: uuid.UUID):
    """The newsroom's own contacts and those other newsrooms chose to share."""
    return or_(Contact.workspace_id == ws, Contact.shared.is_(True))


@router.get("/workspaces/{ws}/contacts")
async def contacts(
    member: AnyMember,
    db: Db,
    q: str = Query(default="", max_length=200),
    topic: str = Query(default="", max_length=60),
    region: str = Query(default="", max_length=120),
) -> list[ContactOut]:
    stmt = select(Contact).where(_visible(member.workspace_id))
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            or_(Contact.name.ilike(like), Contact.institution.ilike(like), Contact.role.ilike(like))
        )
    if topic:
        stmt = stmt.where(Contact.topics.contains([topic]))
    rows = list(await db.scalars(stmt.order_by(Contact.institution, Contact.name).limit(300)))
    if region:
        rows = [
            c
            for c in rows
            if not places.region_of(c.location)
            or places.fold(places.region_of(c.location) or "") == places.fold(region)
        ]
    return [contact_out(c, member.workspace_id) for c in rows]


@router.post("/workspaces/{ws}/contacts", status_code=201)
async def create_contact(body: ContactIn, member: AnyMember, db: Db) -> ContactOut:
    contact = Contact(
        workspace_id=member.workspace_id, created_by=member.user.id, **await _fields(db, body)
    )
    db.add(contact)
    await db.flush()
    await record(db, member.workspace_id, member.user.id, "contact", contact.id, "create")
    await db.commit()
    return contact_out(contact)


async def _own(db: AsyncSession, ws: uuid.UUID, contact_id: uuid.UUID) -> Contact:
    contact = await db.get(Contact, contact_id)
    if contact is None or contact.workspace_id != ws:
        raise ApiError(404, "not_found", "Contact not found")
    return contact


@router.patch("/workspaces/{ws}/contacts/{contact_id}")
async def edit_contact(
    contact_id: uuid.UUID, body: ContactIn, member: AnyMember, db: Db
) -> ContactOut:
    contact = await _own(db, member.workspace_id, contact_id)
    for key, value in (await _fields(db, body, partial=True)).items():
        setattr(contact, key, value)
    # Changing identity or channels invalidates any previous verification.
    contact.verified_at = contact.verified_by = None
    contact.official_pages = [{**p, "verified": False} for p in contact.official_pages or []]
    await record(db, member.workspace_id, member.user.id, "contact", contact.id, "update")
    await db.commit()
    return contact_out(contact)


@router.post("/workspaces/{ws}/contacts/{contact_id}/verify")
async def verify_contact(contact_id: uuid.UUID, member: AnyMember, db: Db) -> ContactOut:
    """A journalist checked the channels and the official pages (called the switchboard, matched the
    page to the institution): the pages now count as official in « Fiabilité de la source »."""
    contact = await _own(db, member.workspace_id, contact_id)
    contact.verified_at, contact.verified_by = datetime.now(UTC), member.user.id
    contact.official_pages = [{**p, "verified": True} for p in contact.official_pages or []]
    await record(db, member.workspace_id, member.user.id, "contact", contact.id, "verify")
    await db.commit()
    return contact_out(contact)


@router.delete("/workspaces/{ws}/contacts/{contact_id}", status_code=204)
async def delete_contact(contact_id: uuid.UUID, member: AnyMember, db: Db) -> None:
    contact = await _own(db, member.workspace_id, contact_id)
    await db.delete(contact)
    await record(db, member.workspace_id, member.user.id, "contact", contact_id, "delete")
    await db.commit()


def host(url: str | None) -> str | None:
    netloc = urllib.parse.urlsplit(url or "").hostname or ""
    netloc = netloc.lower().rstrip(".")
    return netloc.removeprefix("www.") or None


async def official_hosts(db: AsyncSession, workspace_id: uuid.UUID) -> set[str]:
    """Hosts of the official pages the newsroom checked (contract used by the crew's credibility
    grid): a page counts once a journalist verified it, never because it was declared."""
    hosts: set[str] = set()
    for c in await db.scalars(select(Contact).where(_visible(workspace_id))):
        # The contact's own verification stamp is the only source of truth: a page's flag is
        # derived from it and never trusted on its own.
        if not c.verified_at:
            continue
        for page in c.official_pages or []:
            if page.get("verified") and (h := host(page.get("url"))):
                hosts.add(h)
        if h := host(c.website):
            hosts.add(h)
    return hosts


# --- « Qui peut le prouver ? » --------------------------------------------------------------

# Words that say which beat a claim belongs to, so it meets the people who cover that beat. The
# newsroom's own beats are the contacts' topics; this only reads the claim.
BEAT_WORDS: dict[str, tuple[str, ...]] = {
    "énergie": ("delestage", "jirama", "electricite", "courant", "coupure", "carburant", "ore"),
    "eau": ("eau", "robinet", "potable"),
    "santé": ("peste", "cholera", "epidemie", "hopital", "vaccin", "csb", "sdsp", "pasteur",
              "malade", "deces", "variole", "rougeole", "sante"),
    "éducation": ("bac", "baccalaureat", "examen", "ecole", "cepe", "bepc", "enseignant",
                  "rentree", "eleves", "education"),
    "élections": ("ceni", "election", "elections", "vote", "candidat", "scrutin", "electeurs"),
    "catastrophe": ("cyclone", "inondation", "bngrc", "sinistres", "crue", "seisme", "alerte"),
    "météo": ("cyclone", "pluie", "meteo", "tempete", "vent"),
    "économie": ("prix", "riz", "ariary", "inflation", "instat", "billet", "billets", "tarif",
                 "salaire", "banque", "hausse"),
    "transport": ("pont", "route", "taxi", "fermee", "ferme", "circulation", "vol", "aeroport"),
    "sécurité": ("enlevement", "gendarmerie", "police", "dahalo", "attaque", "agression"),
}  # fmt: skip


def _fold(text: str) -> str:
    flat = unicodedata.normalize("NFKD", (text or "").lower())
    return "".join(c for c in flat if not unicodedata.combining(c)).strip()


def place_in(text: str) -> dict[str, Any] | None:
    """The Malagasy place a text names (punctuation stripped: « Antananarivo, selon… »)."""
    return places.gazetteer(re.sub(r"[^\w'’-]+", " ", text or ""))


def claim_beats(item: Item) -> set[str]:
    found = {_fold(t) for t in item.tags or []}
    seen = words(f"{item.title} {item.body}")
    for beat, hints in BEAT_WORDS.items():
        if seen & set(hints):
            found.add(_fold(beat))
    return found


def missing_points(item: Item) -> list[str]:
    """What the reading says is missing, one point per sentence (`analysis.missing` is a text in
    the checker and a list in the crew's confidence block; both are read)."""
    data = item.data or {}
    analysis = data.get("analysis") if isinstance(data.get("analysis"), dict) else {}
    confidence = analysis.get("confidence") if isinstance(analysis.get("confidence"), dict) else {}
    raw: list[str] = []
    for value in (analysis.get("missing"), confidence.get("missing")):
        if isinstance(value, str):
            raw.append(value)
        elif isinstance(value, list):
            raw += [str(v) for v in value if isinstance(v, str | int | float)]
    points: list[str] = []
    for chunk in raw:
        for part in re.split(r"\n+|;|(?<=[.!?])\s+(?=[A-ZÀ-Ý«])", chunk):
            part = part.strip(" -–•*\t").strip()
            if len(part) >= 8 and part.lower() not in {p.lower() for p in points}:
                points.append(part[:300])
    return points[:4]


def track_record(stats: dict[str, Any]) -> str | None:
    asked, answered = int(stats.get("asked") or 0), int(stats.get("answered") or 0)
    if not asked:
        return None
    text = f"A répondu à {answered} question{'s' if answered > 1 else ''} sur {asked}"
    hours = stats.get("last_answer_hours")
    if isinstance(hours, int | float):
        text += (
            " · dernière réponse en moins d'une heure"
            if hours < 1
            else f" · dernière réponse en {round(hours)} h"
        )
    return text


def question_text(newsroom: str, item: Item, point: str | None) -> str:
    """The question as it will be sent; the journalist edits it before sending."""
    title = item.title.strip().rstrip(".")
    ask = "Confirmez-vous cette information ?"
    if point:
        ask += f" Il nous manque notamment ceci : {point.rstrip('.')}."
    return (
        f"Bonjour, ici la rédaction {newsroom}. Une information circule : « {title} ». {ask} "
        "Une réponse courte suffit (oui, non, ou ce que vous savez), avec la référence d'un "
        "document si vous en avez une. Merci."
    )


def score(contact: Contact, text: str, beats: set[str], where: dict | None) -> tuple[float, list]:
    """How well placed a contact is to settle `text`, and why in a few words."""
    seen = words(text)
    why: list[str] = []
    points = 0.0
    named = words(contact.institution) - {"service", "direction", "ministere", "institut"}
    if named and named <= seen:
        points += 5
        why.append(f"{contact.institution} est citée")
    topics = [t for t in contact.topics or [] if _fold(t) in beats]
    if topics:
        points += 3 * min(len(topics), 2)
        why += topics[:2]
    about = words(" ".join([contact.role or "", *(contact.topics or [])])) & seen
    points += min(len(about), 3)
    region = places.region_of(contact.location)
    if where and places.region_of(where):
        if region and places.same_region(contact.location, where):
            points += 2
            why.append(region)
        elif not region:
            points += 0.5
            why.append("national")
        else:
            points -= 1
    elif not region:
        why.append("national")
    else:
        why.append(region)
    if "mg" in (contact.languages or []):
        why.append("parle malgache")
    if contact.verified_at:
        points += 0.5
    stats = contact.stats or {}
    if stats.get("asked"):
        points += min(int(stats.get("answered") or 0) / int(stats["asked"]), 1.0)
    return points, why


class WhoContact(BaseModel):
    contact: ContactOut
    why: list[str]
    track: str | None
    question: str
    score: float


class WhoPoint(BaseModel):
    point: str | None  # None: the claim as a whole (the reading named nothing missing yet)
    contacts: list[WhoContact]


class QuestionOut(BaseModel):
    id: uuid.UUID
    contact_id: uuid.UUID | None
    contact: str | None
    institution: str | None
    channel: str
    question: str
    answer_url: str
    message: str
    links: dict[str, str]
    sent_at: datetime | None
    answered_at: datetime | None
    answer: dict[str, Any] | None
    source_id: uuid.UUID | None


class WhoOut(BaseModel):
    points: list[WhoPoint]
    beats: list[str]
    place: dict[str, Any] | None
    questions: list[QuestionOut]


@router.get("/workspaces/{ws}/items/{item_id}/who")
async def who(item_id: uuid.UUID, member: AnyMember, db: Db) -> WhoOut:
    item = await _get_item(db, member, item_id)
    ws = await db.get(Workspace, member.workspace_id)
    pool = list(await db.scalars(select(Contact).where(_visible(member.workspace_id))))
    claim = f"{item.title} {item.body}"
    beats = claim_beats(item)
    where = place_in(claim)
    out = []
    for point in missing_points(item) or [None]:
        text = f"{point or ''} {claim}"
        ranked = sorted(
            ((*score(c, text, beats, where), c) for c in pool),
            key=lambda r: r[0],
            reverse=True,
        )
        out.append(
            WhoPoint(
                point=point,
                contacts=[
                    WhoContact(
                        contact=contact_out(c, member.workspace_id),
                        why=why,
                        track=track_record(c.stats or {}),
                        question=question_text(ws.name, item, point),
                        score=round(s, 1),
                    )
                    for s, why, c in ranked[:3]
                    if s >= 3
                ],
            )
        )
    return WhoOut(
        points=out,
        beats=sorted(beats),
        place=where,
        questions=await _questions(db, item.id),
    )


# --- questions and answers ------------------------------------------------------------------


def answer_url(token: str) -> str:
    return f"{get_settings().public_web_url.rstrip('/')}/reponse/{token}"


def _digits(phone: str | None) -> str:
    return re.sub(r"\D", "", phone or "")


def links(contact: Contact | None, message: str, ref: str | None) -> dict[str, str]:
    """Ready links: the journalist's own phone or mail app sends; Checky sends nothing itself."""
    if contact is None:
        return {}
    text = urllib.parse.quote(message)
    out: dict[str, str] = {}
    if wa := _digits(contact.whatsapp or contact.phone):
        out["whatsapp"] = f"https://wa.me/{wa}?text={text}"
    if phone := _digits(contact.phone):
        out["sms"] = f"sms:+{phone}?body={text}"
        out["tel"] = f"tel:+{phone}"
    if contact.email:
        subject = urllib.parse.quote(f"Vérification {ref or ''}".strip())
        out["mailto"] = f"mailto:{contact.email}?subject={subject}&body={text}"
    return out


def _message(question: str, token: str) -> str:
    return f"{question}\n\nRépondre ici, sans compte : {answer_url(token)}"


async def _questions(db: AsyncSession, item_id: uuid.UUID) -> list[QuestionOut]:
    rows = (
        await db.execute(
            select(ContactRequest, Contact)
            .outerjoin(Contact, Contact.id == ContactRequest.contact_id)
            .where(ContactRequest.item_id == item_id)
            .order_by(ContactRequest.created_at)
        )
    ).all()
    item = await db.get(Item, item_id)
    ref = (item.data or {}).get("ref") if item else None
    return [_question_out(r, c, ref) for r, c in rows]


def _question_out(r: ContactRequest, c: Contact | None, ref: str | None) -> QuestionOut:
    message = _message(r.question, r.token)
    return QuestionOut(
        id=r.id,
        contact_id=r.contact_id,
        contact=c.name if c else None,
        institution=c.institution if c else None,
        channel=r.channel,
        question=r.question,
        answer_url=answer_url(r.token),
        message=message,
        links=links(c, message, ref),
        sent_at=r.sent_at,
        answered_at=r.answered_at,
        answer=r.answer,
        source_id=r.source_id,
    )


class QuestionIn(BaseModel):
    contact_id: uuid.UUID
    question: str = Field(min_length=10, max_length=2000)
    channel: Literal["whatsapp", "sms", "email", "call"] = "whatsapp"


@router.get("/workspaces/{ws}/items/{item_id}/questions")
async def list_questions(item_id: uuid.UUID, member: AnyMember, db: Db) -> list[QuestionOut]:
    await _get_item(db, member, item_id)
    return await _questions(db, item_id)


@router.post("/workspaces/{ws}/items/{item_id}/questions", status_code=201)
async def ask_contact(
    item_id: uuid.UUID, body: QuestionIn, member: AnyMember, db: Db
) -> QuestionOut:
    item = await _get_item(db, member, item_id)
    contact = await db.get(Contact, body.contact_id)
    if contact is None or not (contact.workspace_id == member.workspace_id or contact.shared):
        raise ApiError(404, "not_found", "Contact not found")
    now = datetime.now(UTC)
    request = ContactRequest(
        workspace_id=member.workspace_id,
        item_id=item.id,
        contact_id=contact.id,
        created_by=member.user.id,
        token=secrets.token_urlsafe(18),
        question=body.question.strip(),
        channel=body.channel,
        sent_at=now,
    )
    db.add(request)
    stats = contact.stats or {}
    contact.stats = {
        **stats,
        "asked": int(stats.get("asked") or 0) + 1,
        "last_asked_at": now.isoformat(),
    }
    await db.flush()
    await record(
        db,
        member.workspace_id,
        member.user.id,
        "item",
        item.id,
        "question",
        {"request_id": str(request.id), "contact_id": str(contact.id), "channel": body.channel},
    )
    await db.commit()
    out = _question_out(request, contact, (item.data or {}).get("ref"))
    await broadcast(member.workspace_id, "question.created", out.model_dump(mode="json"))
    return out


@handler("remind_question")
async def remind_question(ctx: JobContext) -> dict[str, Any]:
    """Three hours without an answer: a reminder the journalist can send (nothing is sent by
    itself). Queued by whoever schedules it; harmless when the answer already came."""
    async with SessionLocal() as db:
        request = await db.get(ContactRequest, uuid.UUID(ctx.input["request_id"]))
        if request is None:
            return {"skipped": "gone"}
        if request.answered_at:
            return {"skipped": "answered"}
        request.reminded_at = datetime.now(UTC)
        await db.commit()
        return {
            "reminded": True,
            "message": f"Rappel : {_message(request.question, request.token)}",
        }


# The page a contact opens from the link: no account, the token is the only key.
_ANSWERS: dict[str, deque[float]] = defaultdict(deque)
ANSWER_LIMIT, ANSWER_WINDOW = 10, 600.0
STANCES = {
    "confirms": "Confirme l'information.",
    "denies": "Dément l'information.",
    "unknown": "Ne peut ni confirmer ni démentir.",
}


def _allow(addr: str) -> bool:
    now, q = time.monotonic(), _ANSWERS[addr]
    while q and now - q[0] > ANSWER_WINDOW:
        q.popleft()
    if len(q) >= ANSWER_LIMIT:
        return False
    q.append(now)
    return True


class ReponseOut(BaseModel):
    question: str
    claim: str
    ref: str | None
    newsroom: str
    contact: str | None
    institution: str | None
    asked_at: datetime | None
    answered_at: datetime | None
    stance: str | None


class ReponseIn(BaseModel):
    stance: Literal["confirms", "denies", "unknown"]
    text: str = Field(min_length=2, max_length=4000)
    name: str = Field(min_length=1, max_length=200)


async def _by_token(db: AsyncSession, token: str):
    row = (
        await db.execute(
            select(ContactRequest, Item, Workspace)
            .join(Item, Item.id == ContactRequest.item_id)
            .join(Workspace, Workspace.id == ContactRequest.workspace_id)
            .where(ContactRequest.token == token)
        )
    ).first()
    if row is None:
        raise ApiError(404, "not_found", "Question not found")
    return row


@router.get("/public/reponse/{token}")
async def reponse(token: str, db: Db) -> ReponseOut:
    request, item, ws = await _by_token(db, token)
    contact = await db.get(Contact, request.contact_id) if request.contact_id else None
    return ReponseOut(
        question=request.question,
        claim=item.title,
        ref=(item.data or {}).get("ref"),
        newsroom=ws.name,
        contact=contact.name if contact else None,
        institution=contact.institution if contact else None,
        asked_at=request.sent_at,
        answered_at=request.answered_at,
        stance=(request.answer or {}).get("stance"),
    )


@router.post("/public/reponse/{token}")
async def answer(token: str, body: ReponseIn, request: Request, db: Db) -> ReponseOut:
    """The answer becomes a dated source of the dossier, the contact's track record is updated
    and the checker reads the dossier again (unless the newsroom runs without AI)."""
    if not _allow(request.client.host if request.client else "unknown"):
        raise ApiError(429, "too_many_answers", "Too many answers, try again in a few minutes")
    asked, item, ws = await _by_token(db, token)
    if asked.answered_at:
        raise ApiError(409, "already_answered", "This question was already answered")
    contact = await db.get(Contact, asked.contact_id) if asked.contact_id else None
    now = datetime.now(UTC)
    who_ = contact.name if contact else body.name.strip()
    # « Porte-parole (JIRAMA) », but not « Service de la JIRAMA (JIRAMA) ».
    if contact and contact.institution and _fold(contact.institution) not in _fold(contact.name):
        who_ = f"{contact.name} ({contact.institution})"
    source = Source(
        workspace_id=ws.id,
        item_id=item.id,
        created_by=PUBLIC_AUTHOR,
        kind="text",
        status="ready",
        title=f"Réponse de {who_}"[:500],
        author=body.name.strip()[:300],
        text=(
            f"{STANCES[body.stance]}\n\n{body.text.strip()}\n\n— {body.name.strip()}, réponse reçue "
            f"le {dates.fr_moment(now.astimezone(dates.EAT))} à la question : « {asked.question} »"
        ),
        published_at=now.astimezone(dates.EAT).date().isoformat(),
    )
    db.add(source)
    await db.flush()
    asked.answered_at = now
    asked.answer = {"stance": body.stance, "text": body.text.strip(), "name": body.name.strip()}
    asked.source_id = source.id
    if contact is not None:
        stats = contact.stats or {}
        hours = (now - asked.sent_at).total_seconds() / 3600 if asked.sent_at else None
        contact.stats = {
            **stats,
            "answered": int(stats.get("answered") or 0) + 1,
            "last_answered_at": now.isoformat(),
            **({"last_answer_hours": round(hours, 1)} if hours is not None else {}),
        }
    await record(db, ws.id, PUBLIC_AUTHOR, "source", source.id, "create")
    await record(
        db,
        ws.id,
        PUBLIC_AUTHOR,
        "item",
        item.id,
        "answer",
        {"request_id": str(asked.id), "stance": body.stance, "source_id": str(source.id)},
    )
    await db.commit()
    from app.modules import sources as sources_module
    from app.modules.rag import queue_embedding

    await broadcast(ws.id, "source.created", await sources_module.source_payload(db, source))
    await sources_module._sync_source_count(db, ws.id, item.id)
    await queue_embedding(db, ws.id, asked.created_by, source.id)
    if (ws.settings or {}).get("ai_enabled", True):
        # Read again with the answer; the journalist who asked owns the job.
        await enqueue(db, ws.id, asked.created_by, "analyze_claim", {"item_id": str(item.id)})
    return await reponse(token, db)


# --- demo -----------------------------------------------------------------------------------

# Fictional people, real institutions: every number is a fictional +261 34 00 000 xx, every
# e-mail is on example.org, and each official page is the institution's public site.
DEMO_CONTACTS: list[dict[str, Any]] = [
    {
        "name": "Chargée de communication, JIRAMA (démo)",
        "kind": "officer",
        "institution": "JIRAMA",
        "role": "Service communication et relations presse",
        "topics": ["énergie", "eau"],
        "place": "Antananarivo",
        "site": "https://www.jirama.mg",
        "hours": "Lun–ven, 8 h–17 h",
        "stats": {"asked": 4, "answered": 3, "last_answer_hours": 2},
    },
    {
        "name": "Direction régionale JIRAMA Atsinanana (démo)",
        "kind": "officer",
        "institution": "JIRAMA",
        "role": "Exploitation électricité, Toamasina",
        "topics": ["énergie"],
        "place": "Toamasina",
        "site": "https://www.jirama.mg",
        "stats": {"asked": 2, "answered": 1, "last_answer_hours": 6},
    },
    {
        "name": "Office de régulation de l'électricité, ORE (démo)",
        "institution": "ORE",
        "role": "Tarifs et contrôle des opérateurs",
        "topics": ["énergie", "économie"],
        "site": "https://www.ore.mg",
        "stats": {"asked": 1, "answered": 1, "last_answer_hours": 20},
    },
    {
        "name": "Ingénieur réseaux électriques, enseignant (démo)",
        "kind": "expert",
        "institution": "Expert indépendant",
        "role": "Réseaux électriques et délestage",
        "topics": ["énergie"],
        "languages": ["fr", "mg", "en"],
    },
    {
        "name": "BNGRC · cellule de veille (démo)",
        "institution": "BNGRC",
        "role": "Alertes cyclones et inondations",
        "topics": ["catastrophe", "météo", "environnement"],
        "site": "https://www.bngrc.mg",
        "hours": "7 j/7, 24 h/24",
        "stats": {"asked": 3, "answered": 3, "last_answer_hours": 1},
    },
    {
        "name": "Météo Madagascar · prévisionniste de garde (démo)",
        "institution": "Météo Madagascar",
        "role": "Prévisions et bulletins cycloniques",
        "topics": ["météo", "catastrophe"],
        "site": "https://www.meteomadagascar.mg",
    },
    {
        "name": "INSTAT · service des prix (démo)",
        "institution": "INSTAT",
        "role": "Indices des prix et recensements",
        "topics": ["économie", "population"],
        "site": "https://www.instat.mg",
        "stats": {"asked": 2, "answered": 2, "last_answer_hours": 26},
    },
    {
        "name": "Banque centrale · communication (démo)",
        "institution": "Banky Foiben'i Madagasikara",
        "role": "Billets, pièces et politique monétaire",
        "topics": ["économie"],
        "site": "https://www.banky-foibe.mg",
    },
    {
        "name": "CENI · service communication (démo)",
        "institution": "CENI",
        "role": "Calendrier et résultats électoraux",
        "topics": ["élections", "politique"],
        "site": "https://www.ceni-madagascar.mg",
    },
    {
        "name": "Ministère de l'Éducation · communication (démo)",
        "institution": "Ministère de l'Éducation nationale",
        "role": "Examens et calendrier scolaire",
        "topics": ["éducation"],
        "site": "https://www.education.gov.mg",
        "stats": {"asked": 3, "answered": 2, "last_answer_hours": 5},
    },
    {
        "name": "Institut Pasteur de Madagascar · communication (démo)",
        "institution": "Institut Pasteur de Madagascar",
        "role": "Peste, épidémies, laboratoire",
        "topics": ["santé"],
        "site": "https://www.pasteur.mg",
    },
    {
        "name": "SDSP Atsinanana · médecin inspecteur (démo)",
        "kind": "officer",
        "institution": "Ministère de la Santé publique",
        "role": "Service de district de santé publique",
        "topics": ["santé"],
        "place": "Toamasina",
        "site": "https://www.sante.gov.mg",
    },
    {
        "name": "Commune urbaine d'Antananarivo · communication (démo)",
        "institution": "Commune urbaine d'Antananarivo",
        "role": "Voirie, marchés, circulation",
        "topics": ["transport", "société"],
        "place": "Antananarivo",
    },
]


async def seed_demo(db: AsyncSession, workspace_id, user_id, items: dict[str, Item]) -> None:
    """Thirteen fictional contacts for the demo newsroom (replaced on every reset)."""
    await db.execute(
        delete(Contact).where(Contact.workspace_id == workspace_id, Contact.is_demo.is_(True))
    )
    now = datetime.now(UTC)
    for n, spec in enumerate(DEMO_CONTACTS, 1):
        spec = dict(spec)
        site = spec.pop("site", None)
        place = spec.pop("place", None)
        number = f"+261 34 00 000 {n:02d}"
        db.add(
            Contact(
                workspace_id=workspace_id,
                created_by=user_id,
                kind=spec.pop("kind", "institution"),
                languages=spec.pop("languages", ["fr", "mg"]),
                location=places.gazetteer(place) if place else {},
                phone=number,
                whatsapp=number,
                email=f"contact{n:02d}@example.org",
                website=site,
                official_pages=[{"kind": "site", "url": site, "verified": True}] if site else [],
                verified_at=now if site else None,
                verified_by=user_id if site else None,
                is_demo=True,
                **spec,
            )
        )
    await db.flush()
