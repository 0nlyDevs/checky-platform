"""Explicit newsroom signatures; no automatic publication from an AI result.

Knowing is not publishing: the facts and Checky's reading are on the dossier without anyone's
signature. A signature is a byline: the newsroom's name and the journalist's, needed only to send
a verdict out. Routes:

- `POST …/items/{id}/sign` one dossier, with the verdict and the public explanation;
- `POST /workspaces/{ws}/items/sign {ids}` the waiting ones at once, each with its suggested
  verdict and its analysis reason (« Signer les N »);
- `POST …/items/{id}/adopt {review}` « Reprendre ce verdict »: a fact-checker's published review
  becomes source [1] and the newsroom signs its conclusion, credited to it;
- `POST …/items/{id}/release` under double signature, another editor publishes the signed version.

Once a verdict is published the truth gets its first stop (« Page publique ») and the people who
asked are told (`sms.notify_signed`, when that module exists).
"""

import hashlib
import json
import logging
import re
import unicodedata
import uuid
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import dates
from app.core.access import AnyMember, Db, Editor, Member
from app.core.activity import broadcast, record
from app.core.config import get_settings
from app.core.errors import ApiError
from app.core.models import Item, Source, Workspace, auth_user
from app.modules.items import ItemOut

log = logging.getLogger("checky.signing")
router = APIRouter(tags=["signing"])
SIGNATURE_FIELDS = {
    "signed_by",
    "signed_at",
    "signed_digest",
    "published_by",
    "published_at",
    "byline",
}
VERDICTS = ("true", "false", "misleading", "unverifiable")
Verdict = Literal["true", "false", "misleading", "unverifiable"]


class SignIn(BaseModel):
    verdict: Verdict
    reason: str = Field(min_length=10, max_length=2000)
    publish: bool = False


def digest(title, body, data):
    return hashlib.sha256(
        json.dumps(
            {
                "title": title,
                "body": body,
                "verdict": data.get("verdict"),
                "reason": data.get("reason"),
            },
            sort_keys=True,
            ensure_ascii=False,
        ).encode()
    ).hexdigest()


async def publication_guard(db, member, status, title, body, data):
    if status != "published":
        return
    if data.get("verdict") not in VERDICTS:
        raise ApiError(409, "no_verdict", "A newsroom verdict is required to publish")
    workspace = await db.get(Workspace, member.workspace_id)
    if not (workspace.settings or {}).get("double_signature"):
        return
    if not member.at_least("editor"):
        raise ApiError(403, "editor_required", "An editor must release this verdict")
    if not data.get("signed_by") or data.get("signed_digest") != digest(title, body, data):
        raise ApiError(409, "signature_required", "Sign the current version before publication")
    if data["signed_by"] == member.user.id:
        raise ApiError(
            409, "second_signer_required", "A different editor must release this verdict"
        )


async def names(db: AsyncSession, ids) -> dict[str, str]:
    """Display names of Better Auth users (name, else email), for bylines and the carnet."""
    ids = [i for i in set(ids) if i]
    if not ids:
        return {}
    rows = await db.execute(
        select(auth_user.c.id, auth_user.c.name, auth_user.c.email).where(auth_user.c.id.in_(ids))
    )
    return {r.id: (r.name or r.email or r.id) for r in rows}


def permalink(item: Item) -> str:
    return f"{get_settings().public_web_url.rstrip('/')}/verifies/{item.id}"


def may_sign(member: Member, item: Item) -> bool:
    # The author, the journalist the dossier is assigned to (tips have no desk author), or an editor.
    return (
        item.author_id == member.user.id
        or (item.data or {}).get("assignee_id") == member.user.id
        or member.at_least("editor")
    )


def signed_current(item: Item) -> bool:
    """A signature exists and still matches the dossier as it reads now."""
    data = item.data or {}
    return bool(data.get("signed_by")) and data.get("signed_digest") == digest(
        item.title, item.body, data
    )


async def _locked(db: AsyncSession, member: Member, item_id: uuid.UUID) -> Item:
    item = await db.scalar(
        select(Item)
        .where(Item.id == item_id, Item.workspace_id == member.workspace_id)
        .with_for_update()
    )
    if item is None:
        raise ApiError(404, "not_found", "Item not found")
    return item


async def _apply(
    db: AsyncSession,
    member: Member,
    ws: Workspace,
    item: Item,
    verdict: str,
    reason: str,
    publish: bool,
    extra: dict | None = None,
) -> bool:
    """Write the signature on the item (not committed). Returns True when it is now published."""
    if not may_sign(member, item):
        raise ApiError(403, "forbidden", "Only the author or an editor can sign this dossier")
    at = datetime.now(UTC).isoformat()
    signer = (await names(db, [member.user.id])).get(member.user.id) or member.user.email
    data = {
        **item.data,
        **(extra or {}),
        "verdict": verdict,
        "reason": reason.strip(),
        "signed_by": member.user.id,
        "signed_at": at,
        "byline": {"newsroom": ws.name, "journalist": signer, "signed_at": at},
    }
    data["signed_digest"] = digest(item.title, item.body, data)
    # Under double signature a signature only verifies; another editor releases (`/release`).
    published = publish and not (ws.settings or {}).get("double_signature")
    item.status = "published" if published else "verified"
    if published:
        data["published_by"], data["published_at"] = member.user.id, at
    item.data = data
    await record(
        db,
        member.workspace_id,
        member.user.id,
        "item",
        item.id,
        "sign",
        {"verdict": verdict, "status": item.status, **({"adopted": True} if extra else {})},
    )
    if published:
        await _first_truth_stop(db, ws, item, member.user.id)
    return published


async def _first_truth_stop(db: AsyncSession, ws: Workspace, item: Item, user_id: str) -> None:
    """The public page is the truth's first stop, when the newsroom shows its verdicts."""
    if not ws.is_public:
        return
    try:
        from app.modules import trajet

        await trajet.add_stop(
            db,
            ws.id,
            item.id,
            side="truth",
            channel="web",
            place="Page publique",
            location={},
            proof={"url": permalink(item)},
            status="broadcast",
            added_by=user_id,
        )
    except (ImportError, AttributeError):
        pass


async def _notify(db: AsyncSession, item: Item) -> None:
    """Tell the people who asked (SMS line, « Me prévenir »), once the verdict is public."""
    try:
        from app.modules import sms

        notify = sms.notify_signed
    except (ImportError, AttributeError):
        return
    try:
        await notify(db, item)
        await db.commit()
    except Exception:  # a notification must never undo a signature
        log.exception("notify_signed failed for %s", item.id)
        await db.rollback()


async def _done(db: AsyncSession, member: Member, item: Item, published: bool) -> ItemOut:
    await db.commit()
    await db.refresh(item)
    if published:
        await _notify(db, item)
        await db.refresh(item)
    out = ItemOut.model_validate(item)
    await broadcast(member.workspace_id, "item.updated", out.model_dump(mode="json"))
    return out


@router.post("/workspaces/{ws}/items/{item_id}/sign")
async def sign(item_id: uuid.UUID, body: SignIn, member: AnyMember, db: Db) -> ItemOut:
    item = await _locked(db, member, item_id)
    ws = await db.get(Workspace, member.workspace_id)
    published = await _apply(db, member, ws, item, body.verdict, body.reason, body.publish)
    return await _done(db, member, item, published)


@router.post("/workspaces/{ws}/items/{item_id}/release")
async def release(item_id: uuid.UUID, member: Editor, db: Db) -> ItemOut:
    """« Publier la version signée »: an editor publishes what a journalist signed, as long as
    nothing changed since (same digest) and, under double signature, someone else signed it."""
    item = await _locked(db, member, item_id)
    if item.status == "published":
        raise ApiError(409, "already_published", "This verdict is already published")
    if not signed_current(item):
        raise ApiError(409, "signature_required", "Sign the current version before publication")
    await publication_guard(db, member, "published", item.title, item.body, item.data)
    ws = await db.get(Workspace, member.workspace_id)
    item.status = "published"
    item.data = {
        **item.data,
        "published_by": member.user.id,
        "published_at": datetime.now(UTC).isoformat(),
    }
    await record(
        db, member.workspace_id, member.user.id, "item", item.id, "publish", {"status": "published"}
    )
    await _first_truth_stop(db, ws, item, member.user.id)
    return await _done(db, member, item, True)


# --- « Signer les N » -----------------------------------------------------------------------


class BatchIn(BaseModel):
    ids: list[uuid.UUID] = Field(min_length=1, max_length=50)
    publish: bool = True


class Skipped(BaseModel):
    id: uuid.UUID
    code: str


class BatchOut(BaseModel):
    signed: list[ItemOut]
    skipped: list[Skipped]


def batch_reason(data: dict) -> str:
    analysis = data.get("analysis") if isinstance(data.get("analysis"), dict) else {}
    for text in (data.get("reason"), analysis.get("reason")):
        if isinstance(text, str) and len(text.strip()) >= 10:
            return text.strip()[:2000]
    return ""


@router.post("/workspaces/{ws}/items/sign")
async def sign_many(body: BatchIn, member: AnyMember, db: Db) -> BatchOut:
    """Each dossier is signed with its own verdict, or the suggested one, and its explanation, or
    the analysis reason. One that cannot be signed is skipped with the reason, never guessed."""
    signed, skipped = [], []
    for item_id in dict.fromkeys(body.ids):
        # Read again each time: a failed notification rolls back and expires what was loaded.
        ws = await db.get(Workspace, member.workspace_id, populate_existing=True)
        item = await db.scalar(
            select(Item)
            .where(Item.id == item_id, Item.workspace_id == member.workspace_id)
            .with_for_update()
        )
        data = (item.data or {}) if item else {}
        verdict = data.get("verdict") or data.get("verdict_suggested")
        code = None
        if item is None:
            code = "not_found"
        elif verdict not in VERDICTS:
            code = "no_verdict"
        elif signed_current(item):
            code = "already_signed"
        elif not batch_reason(data):
            code = "missing_reason"
        elif not may_sign(member, item):
            code = "forbidden"
        if code:
            skipped.append(Skipped(id=item_id, code=code))
            continue
        published = await _apply(db, member, ws, item, verdict, batch_reason(data), body.publish)
        signed.append(await _done(db, member, item, published))
    return BatchOut(signed=signed, skipped=skipped)


# --- « Reprendre ce verdict » ---------------------------------------------------------------

# A fact-checker's rating, in its own words, read as one of our four verdicts. Matched on whole
# words after accents are removed, in this order: false-leaning phrases and negations first
# (« inaccurate », « not true » must never read as true), then misleading, then unverifiable,
# then true only when nothing else matched. Anything unclear returns None: the journalist picks.
RATINGS: list[tuple[str, tuple[str, ...]]] = [
    (
        "false",
        (
            "inaccurate", "not accurate", "not true", "untrue", "not correct", "incorrect",
            "pas vrai", "pas exact", "inexact", "mostly false", "plutot faux", "faux", "fausse",
            "false", "fake", "pants on fire", "falso", "wrong", "infonde", "sans fondement",
            "fabrique", "hoax", "intox", "scam", "arnaque", "diso",
        ),
    ),
    (
        "misleading",
        (
            "misleading", "trompeur", "trompeuse", "half true", "demi vrai", "mixture", "mixed",
            "missing context", "contexte manquant", "out of context", "hors contexte",
            "sorti de son contexte", "partly false", "partiellement faux", "partly true",
            "partiellement vrai", "exagere", "exaggerated", "manipule", "manipulated", "altered",
            "deforme", "distorted", "enganoso", "mamitaka",
        ),
    ),
    (
        "unverifiable",
        (
            "unproven", "inverifiable", "unverifiable", "unverified", "non prouve", "non verifie",
            "sans preuve", "no evidence", "unsupported", "indetermine", "impossible a verifier",
        ),
    ),
    ("true", ("vrai", "true", "mostly true", "plutot vrai", "correct", "accurate", "exact",
              "verdadero", "marina")),
]  # fmt: skip


def _flat(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text.lower())
    folded = "".join(c for c in folded if not unicodedata.combining(c))
    return " " + " ".join(re.findall(r"[a-z0-9]+", folded)) + " "


def rating_verdict(rating: str) -> str | None:
    """Our verdict for a fact-checker's rating, or None when the words are not clear."""
    flat = _flat(rating)
    found = [v for v, phrases in RATINGS if any(f" {_flat(p).strip()} " in flat for p in phrases)]
    if not found:
        return None
    if "false" in found and "misleading" in found:
        # « Partly false » holds a false word inside a misleading phrase; anything else that
        # says both (« faux et trompeur ») is not clear enough to sign without a person choosing.
        return "misleading" if flat.strip().startswith(("partly", "partiellement")) else None
    return found[0]


class Review(BaseModel):
    publisher: str = Field(min_length=1, max_length=200)
    url: HttpUrl
    rating: str = Field(min_length=1, max_length=200)
    date: str | None = Field(default=None, max_length=40)
    title: str = Field(default="", max_length=500)


class AdoptIn(BaseModel):
    review: Review
    # Required when the rating's words are not clear; the journalist's choice wins otherwise.
    verdict: Verdict | None = None
    reason: str | None = Field(default=None, min_length=10, max_length=2000)
    # Signing only by default: the journalist sees the mapped verdict and publishes after.
    publish: bool = False


class RatingOut(BaseModel):
    rating: str
    verdict: str | None


@router.get("/workspaces/{ws}/ratings")
async def read_rating(member: AnyMember, rating: str = Query(max_length=200)) -> RatingOut:
    """How « Reprendre ce verdict » would read a fact-checker's rating, shown before signing."""
    return RatingOut(rating=rating, verdict=rating_verdict(rating))


@router.post("/workspaces/{ws}/items/{item_id}/adopt")
async def adopt(item_id: uuid.UUID, body: AdoptIn, member: AnyMember, db: Db) -> ItemOut:
    """The review is relayed as the fact-checker's, with its date and link: it becomes the
    dossier's source [1] and the newsroom signs the matching verdict under its own byline."""
    review = body.review
    verdict = body.verdict or rating_verdict(review.rating)
    if verdict is None:
        raise ApiError(422, "unknown_rating", "Choose the verdict by hand for this rating")
    item = await _locked(db, member, item_id)
    if not may_sign(member, item):
        raise ApiError(403, "forbidden", "Only the author or an editor can sign this dossier")
    ws = await db.get(Workspace, member.workspace_id)
    day = dates.parse(review.date)
    when = f" le {dates.fr(day)}" if day else ""
    title = review.title.strip()
    source = Source(
        workspace_id=member.workspace_id,
        item_id=item.id,
        created_by=member.user.id,
        kind="url",
        status="ready",
        url=str(review.url),
        title=f"{review.publisher} · {title or review.rating}"[:500],
        text=(
            f"{review.publisher} a publié une vérification{when}"
            + (f" : « {title} »" if title else "")
            + f". Sa conclusion : {review.rating}."
        ),
        published_at=day.isoformat() if day else None,
    )
    db.add(source)
    await db.flush()
    await record(
        db,
        member.workspace_id,
        member.user.id,
        "item",
        item.id,
        "source",
        {"source_id": str(source.id), "kind": source.kind},
    )
    reason = body.reason or (
        f"{review.publisher} a vérifié cette affirmation{when} et conclut « {review.rating} » [1]. "
        "Notre rédaction reprend son verdict."
    )
    adopted = {**review.model_dump(mode="json"), "source_id": str(source.id)}
    published = await _apply(
        db, member, ws, item, verdict, reason, body.publish, extra={"adopted": adopted}
    )
    await _done(db, member, item, published)
    await db.refresh(source)
    from app.modules import sources as sources_module
    from app.modules.rag import queue_embedding

    await broadcast(
        member.workspace_id, "source.created", await sources_module.source_payload(db, source)
    )
    # Keeps `source_count` in step (and broadcasts the item again when it changes).
    await sources_module._sync_source_count(db, member.workspace_id, item.id)
    await queue_embedding(db, member.workspace_id, member.user.id, source.id)
    await db.refresh(item)
    return ItemOut.model_validate(item)


# --- « Carnet de diligence » and the attestation ------------------------------------------

VERDICT_WORDS = {
    "true": "Vrai",
    "misleading": "Trompeur",
    "false": "Faux",
    "unverifiable": "Invérifiable",
}
STANCE_WORDS = {"confirms": "confirme", "denies": "dément", "unknown": "ne peut pas trancher"}
CHANNEL_WORDS = {"whatsapp": "WhatsApp", "sms": "SMS", "email": "e-mail", "call": "appel"}
ROUTE_WORDS = {
    "facebook": "Facebook",
    "whatsapp": "WhatsApp",
    "tiktok": "TikTok",
    "radio": "Radio",
    "sms": "SMS",
    "press": "Presse",
    "web": "Web",
    "poster": "Affiche",
    "institution": "Institution",
    "voice": "Vocal",
    "other": "Autre",
}


class CarnetEntry(BaseModel):
    at: datetime
    kind: str
    actor: str
    text: str


class CarnetSource(BaseModel):
    id: uuid.UUID
    title: str
    kind: str
    url: str | None
    published_at: str | None
    added_at: datetime
    added_by: str


class CarnetQuestion(BaseModel):
    contact: str | None
    institution: str | None
    channel: str
    sent_at: datetime | None
    answered_at: datetime | None
    stance: str | None


class CarnetOut(BaseModel):
    newsroom: str
    item_id: uuid.UUID
    ref: str | None
    title: str
    status: str
    first_seen_at: str | None
    verdict: str | None
    verdict_suggested: str | None
    reason: str | None
    byline: dict | None
    generated_at: datetime
    entries: list[CarnetEntry]
    sources: list[CarnetSource]
    questions: list[CarnetQuestion]
    checks: int
    routes: dict[str, int]


def _actor(user_id: str, known: dict[str, str]) -> str:
    if user_id == "public":
        return "Public"
    if user_id == "system":
        return "Checky"
    if user_id.startswith("radio:"):
        return "Radio partenaire"
    return known.get(user_id) or "Membre de la rédaction"


def _entry_text(action: str, diff: dict, titles: dict[str, str], contacts: dict[str, str]) -> str:
    word = VERDICT_WORDS.get(str(diff.get("verdict") or diff.get("verdict_suggested") or ""), "—")
    if action == "create":
        return "Dossier ouvert"
    if action == "source":
        return f"Source ajoutée : {titles.get(str(diff.get('source_id')), 'source retirée')}"
    if action == "analysis":
        return f"Lecture de Checky : « {word} » suggéré"
    if action == "sign":
        published = diff.get("status") == "published"
        adopted = " (verdict d'un fact-checker repris)" if diff.get("adopted") else ""
        return f"Verdict signé : {word}{' et publié' if published else ''}{adopted}"
    if action == "publish":
        return "Version signée publiée"
    if action == "question":
        who = contacts.get(str(diff.get("contact_id")), "un contact")
        return f"Question envoyée à {who} ({CHANNEL_WORDS.get(diff.get('channel'), 'message')})"
    if action == "answer":
        return f"Réponse reçue : {STANCE_WORDS.get(diff.get('stance'), 'réponse')}"
    if action == "route":
        side = "Rumeur vue" if diff.get("side") == "rumour" else "Correction envoyée"
        channel = ROUTE_WORDS.get(str(diff.get("channel")), str(diff.get("channel") or "—"))
        return f"{side} : {channel} · {diff.get('place') or '—'}"
    if action == "diffuse":
        n = len(diff.get("routes") or [])
        return f"Diffusé sur {n} route{'s' if n > 1 else ''}"
    if action == "broadcast":
        return f"Diffusé à l'antenne : {diff.get('station')}"
    if action == "comment":
        return "Commentaire dans le fil"
    if action == "update" and "status" in diff:
        return "Statut modifié"
    return "Dossier modifié"


async def carnet_of(db: AsyncSession, item: Item) -> CarnetOut:
    from app.core.models import Activity, Contact, ContactRequest, Route

    ws = await db.get(Workspace, item.workspace_id)
    activity = list(
        await db.scalars(
            select(Activity)
            .where(Activity.workspace_id == item.workspace_id, Activity.entity_id == item.id)
            .order_by(Activity.created_at)
        )
    )
    sources = list(
        await db.scalars(
            select(Source).where(Source.item_id == item.id).order_by(Source.created_at)
        )
    )
    asked = (
        await db.execute(
            select(ContactRequest, Contact)
            .outerjoin(Contact, Contact.id == ContactRequest.contact_id)
            .where(ContactRequest.item_id == item.id)
            .order_by(ContactRequest.created_at)
        )
    ).all()
    routes = list(await db.scalars(select(Route).where(Route.item_id == item.id)))
    known = await names(db, [a.actor_id for a in activity] + [s.created_by for s in sources])
    titles = {str(s.id): s.title for s in sources}
    contacts = {str(c.id): c.name for _, c in asked if c is not None}
    data = item.data or {}
    return CarnetOut(
        newsroom=ws.name,
        item_id=item.id,
        ref=data.get("ref"),
        title=item.title,
        status=item.status,
        first_seen_at=data.get("first_seen_at"),
        verdict=data.get("verdict"),
        verdict_suggested=data.get("verdict_suggested"),
        reason=data.get("reason"),
        byline=data.get("byline") if isinstance(data.get("byline"), dict) else None,
        generated_at=datetime.now(UTC),
        entries=[
            CarnetEntry(
                at=a.created_at,
                kind=a.action,
                actor=_actor(a.actor_id, known),
                text=_entry_text(a.action, a.diff or {}, titles, contacts),
            )
            for a in activity
        ],
        sources=[
            CarnetSource(
                id=s.id,
                title=s.title,
                kind=s.kind,
                url=s.url,
                published_at=s.published_at,
                added_at=s.created_at,
                added_by=_actor(s.created_by, known),
            )
            for s in sources
        ],
        questions=[
            CarnetQuestion(
                contact=c.name if c else None,
                institution=c.institution if c else None,
                channel=r.channel,
                sent_at=r.sent_at,
                answered_at=r.answered_at,
                stance=(r.answer or {}).get("stance"),
            )
            for r, c in asked
        ],
        checks=sum(1 for a in activity if a.action == "analysis"),
        routes={
            "rumour": sum(1 for r in routes if r.side == "rumour"),
            "truth": sum(1 for r in routes if r.side == "truth"),
        },
    )


@router.get("/workspaces/{ws}/items/{item_id}/carnet")
async def carnet(item_id: uuid.UUID, member: AnyMember, db: Db) -> CarnetOut:
    """Everything done on the dossier, dated: checks, sources, questions and answers, routes,
    signatures. Printed as « Exporter le carnet »."""
    from app.modules.items import _get_item

    return await carnet_of(db, await _get_item(db, member, item_id))


class AttestationOut(BaseModel):
    summary: str
    payload: dict
    sha256: str
    signature: str
    key_id: str
    public_key: str
    issued_at: str


def _summary(p: dict) -> str:
    n, q = len(p["sources"]), p["questions"]
    text = (
        f"{p['newsroom']} atteste avoir vérifié « {p['title']} »"
        + (f" ({p['ref']})" if p.get("ref") else "")
        + f" : {n} source{'s' if n > 1 else ''} au dossier, {q['sent']} question"
        + f"{'s' if q['sent'] > 1 else ''} envoyée{'s' if q['sent'] > 1 else ''} et "
        + f"{q['answered']} réponse{'s' if q['answered'] > 1 else ''} reçue"
        + f"{'s' if q['answered'] > 1 else ''}, {p['checks']} lecture"
        + f"{'s' if p['checks'] > 1 else ''} de Checky."
    )
    day = dates.parse(p.get("signed_at"))
    who = p.get("signed_by")
    return (
        f"{text} Verdict signé"
        + (f" le {dates.fr(day)}" if day else "")
        + (f" par {who}" if who else "")
        + f" : {p['verdict_word']}."
    )


@router.get("/workspaces/{ws}/items/{item_id}/attestation")
async def attestation(item_id: uuid.UUID, member: AnyMember, db: Db) -> AttestationOut:
    """« Attestation de vérification »: the carnet's summary signed with the server's key, so a
    partner, a court or a reader can check that this newsroom did this work on this version."""
    from app.core import attest
    from app.modules.items import _get_item

    item = await _get_item(db, member, item_id)
    data = item.data or {}
    if not data.get("signed_by") or data.get("verdict") not in VERDICTS:
        raise ApiError(409, "not_signed", "Sign the verdict before issuing an attestation")
    book = await carnet_of(db, item)
    byline = book.byline or {}
    payload = {
        "v": 1,
        "kind": "checky.attestation",
        "newsroom": book.newsroom,
        "item_id": str(item.id),
        "ref": book.ref,
        "title": item.title,
        "first_seen_at": book.first_seen_at,
        "verdict": data["verdict"],
        "verdict_word": VERDICT_WORDS[data["verdict"]],
        "reason": data.get("reason"),
        "signed_at": data.get("signed_at"),
        "signed_by": byline.get("journalist"),
        "published_at": data.get("published_at"),
        "signed_digest": data.get("signed_digest"),
        "sources": [
            {"title": s.title, "published_at": s.published_at, "url": s.url}
            for s in book.sources[:30]
        ],
        "questions": {
            "sent": len(book.questions),
            "answered": sum(1 for q in book.questions if q.answered_at),
        },
        "checks": book.checks,
        "routes": book.routes,
        "issued_at": datetime.now(UTC).isoformat(),
    }
    try:
        signed = attest.sign(payload)
    except attest.AttestationUnavailable as e:
        raise ApiError(
            503, "attestation_unavailable", "No server key: set SEAL_SECRET to sign attestations"
        ) from e
    return AttestationOut(
        summary=_summary(payload),
        payload=payload,
        sha256=signed["sha256"],
        signature=signed["signature"],
        key_id=signed["key_id"],
        public_key=signed["public_key"],
        issued_at=payload["issued_at"],
    )


class VerifyIn(BaseModel):
    payload: dict
    signature: str = Field(min_length=1, max_length=200)


class VerifyOut(BaseModel):
    valid: bool
    key_id: str
    sha256: str
    summary: str | None


@router.post("/public/attestations/verify")
async def verify_attestation(body: VerifyIn) -> VerifyOut:
    """Anyone can check an attestation against the server's key (no account)."""
    from app.core import attest

    try:
        key = attest.public_key()
    except attest.AttestationUnavailable as e:
        raise ApiError(503, "attestation_unavailable", "No server key to verify with") from e
    valid = attest.verify(body.payload, body.signature)
    summary = None
    if valid:
        try:
            summary = _summary(body.payload)
        except (KeyError, TypeError):
            summary = None
    return VerifyOut(
        valid=valid,
        key_id=key["key_id"],
        sha256=hashlib.sha256(attest.canonical(body.payload)).hexdigest(),
        summary=summary,
    )
