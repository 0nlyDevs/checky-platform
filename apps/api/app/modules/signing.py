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
import unicodedata
import uuid
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter
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

# A fact-checker's rating, in its own words, read as one of our four verdicts. Phrases that
# contain another verdict's word come first (« partly false » is not « false »).
RATINGS: list[tuple[str, tuple[str, ...]]] = [
    (
        "misleading",
        (
            "partly false", "partiellement faux", "partially false", "mostly false", "plutot faux",
            "half true", "demi-vrai", "partly true", "partiellement vrai", "out of context",
            "hors contexte", "sorti de son contexte", "missing context", "contexte manquant",
            "trompeu", "misleading", "exagere", "exaggerat", "manipule", "manipulated", "altered",
            "deforme", "distorted", "enganoso", "mixture", "mixed", "mamitaka",
        ),
    ),
    (
        "unverifiable",
        (
            "unproven", "inverifiable", "unverifiable", "unverified", "non prouve", "non verifie",
            "sans preuve", "no evidence", "unsupported", "indetermine", "impossible a verifier",
            "research in progress",
        ),
    ),
    (
        "false",
        (
            "faux", "fausse", "false", "fake", "untrue", "not true", "pas vrai", "incorrect",
            "pants on fire", "falso", "wrong", "inexact", "infonde", "sans fondement", "fabrique",
            "hoax", "intox", "scam", "arnaque", "diso",
        ),
    ),
    (
        "true",
        ("vrai", "true", "correct", "accurate", "verdadero", "exact", "confirme", "marina"),
    ),
]  # fmt: skip


def rating_verdict(rating: str) -> str | None:
    """Our verdict for a fact-checker's rating, or None when the words are not recognised."""
    flat = unicodedata.normalize("NFKD", " ".join(rating.lower().split()))
    flat = "".join(c for c in flat if not unicodedata.combining(c))
    for verdict, phrases in RATINGS:
        if any(p in flat for p in phrases):
            return verdict
    return None


class Review(BaseModel):
    publisher: str = Field(min_length=1, max_length=200)
    url: HttpUrl
    rating: str = Field(min_length=1, max_length=200)
    date: str | None = Field(default=None, max_length=40)
    title: str = Field(default="", max_length=500)


class AdoptIn(BaseModel):
    review: Review
    reason: str | None = Field(default=None, min_length=10, max_length=2000)
    publish: bool = True


@router.post("/workspaces/{ws}/items/{item_id}/adopt")
async def adopt(item_id: uuid.UUID, body: AdoptIn, member: AnyMember, db: Db) -> ItemOut:
    """The review is relayed as the fact-checker's, with its date and link: it becomes the
    dossier's source [1] and the newsroom signs the matching verdict under its own byline."""
    review = body.review
    verdict = rating_verdict(review.rating)
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
