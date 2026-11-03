"""The Registre: originals of communiqués, decrees and notices as their issuers published them, so a
circulating copy can be compared word by word (Authentique / Modifié / Introuvable / Incohérent).

A match proves that the words correspond to a registered original, not that the original says
something true. « Introuvable » never means « Faux »: the registry is never complete, only the
issuer can confirm. Every journalist of the newsroom registers originals and seals them on the
issuer's behalf; another newsroom confirms an entry (« vérifié » once two newsrooms vouch).
"""

import difflib
import re
import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import dates, numbers, places, seal
from app.core.access import AnyMember, Db, Member
from app.core.activity import broadcast, record
from app.core.db import SessionLocal
from app.core.errors import ApiError
from app.core.models import Communique, SealKey, Workspace
from app.core.seal import fingerprint, normalise, seal_url
from app.core.words import words

router = APIRouter(tags=["registry"])

# Entries confirmed by this many newsrooms (the one that registered it included) are « vérifiés ».
CONFIRMED_AT = 2
PLACE_KEYS = ("name", "country", "region", "locality", "lat", "lng")


class OriginalIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    issuer: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=500)
    number: str | None = Field(default=None, max_length=60)
    issued_on: str | None = Field(default=None, max_length=10)
    text: str = Field(min_length=20, max_length=30000)
    url: HttpUrl | None = None
    file_id: uuid.UUID | None = None
    # Where the communiqué applies, as a place name (« Antananarivo »), structured by code.
    place: str | None = Field(default=None, max_length=200)
    is_demo: bool = False

    @field_validator("issued_on")
    @classmethod
    def day(cls, value):
        if not value:
            return None
        parsed = dates.parse(value)
        if not parsed:
            raise ValueError("Use a past or current YYYY-MM-DD date")
        return parsed.isoformat()

    @field_validator("issuer", "title", "number")
    @classmethod
    def tidy(cls, value):
        return re.sub(r"\s+", " ", value).strip() if value else value

    @field_validator("issuer")
    @classmethod
    def not_reserved(cls, value):
        # `checky:` names hold the newsroom's own verdict key (app/core/seal.py).
        if seal.reserved_issuer(value):
            raise ValueError("This issuer name is reserved")
        return value


class NewsroomOut(BaseModel):
    slug: str
    name: str


class SealOut(BaseModel):
    key_id: str
    signature: str
    sealed_at: str
    url: str


class DiffOp(BaseModel):
    op: Literal["equal", "insert", "delete", "replace"]
    a: str
    b: str


class ChangedNumber(BaseModel):
    kind: str
    original: str | None
    submitted: str | None


class CommuniqueOut(BaseModel):
    id: uuid.UUID
    issuer: str
    number: str | None
    issued_on: str | None
    title: str
    text: str
    url: str | None
    file_id: uuid.UUID | None
    fingerprint: str | None
    status: Literal["original", "fake_caught"]
    is_demo: bool
    created_at: datetime
    location: dict[str, Any]
    own: bool
    newsroom: NewsroomOut | None
    # Newsrooms vouching for the entry, the registering one included.
    confirmations: int
    confirmed: bool
    confirmed_by_us: bool
    sealed: SealOut | None
    # A fake caught: the original it imitates and how it differs.
    original_id: uuid.UUID | None = None
    diff: list[DiffOp] = []
    changed_numbers: list[ChangedNumber] = []
    summary: str | None = None
    # An original: how many fakes of it were caught.
    fakes: int = 0


class FakeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=5, max_length=30000)
    url: HttpUrl | None = None


def out(c: Communique, ws: Workspace | None, viewer: uuid.UUID, fakes: int = 0) -> CommuniqueOut:
    loc = c.location or {}
    sealed = None
    if c.sealed and c.sealed.get("signature"):
        sealed = SealOut(
            key_id=c.sealed["key_id"],
            signature=c.sealed["signature"],
            sealed_at=c.sealed["sealed_at"],
            url=seal_url(c.id, c.sealed),
        )
    confirmations = 1 + len(c.confirmed_by or [])
    original_id = loc.get("original_id")
    return CommuniqueOut(
        id=c.id,
        issuer=c.issuer,
        number=c.number,
        issued_on=c.issued_on,
        title=c.title,
        text=c.text,
        url=c.url,
        file_id=c.file_id,
        fingerprint=c.fingerprint,
        status=c.status,
        is_demo=c.is_demo,
        created_at=c.created_at,
        location={k: v for k, v in loc.items() if k in PLACE_KEYS},
        own=c.workspace_id == viewer,
        newsroom=NewsroomOut(slug=ws.slug, name=ws.name) if ws and ws.publishes else None,
        confirmations=confirmations,
        confirmed=confirmations >= CONFIRMED_AT,
        confirmed_by_us=str(viewer) in (c.confirmed_by or []),
        sealed=sealed,
        original_id=uuid.UUID(original_id) if original_id else None,
        diff=loc.get("diff") or [],
        changed_numbers=loc.get("changed_numbers") or [],
        summary=loc.get("summary"),
        fakes=fakes,
    )


async def _fake_counts(db: AsyncSession, viewer: uuid.UUID, ids: list[uuid.UUID]) -> dict[str, int]:
    """Fakes caught per original, counting only the fakes this newsroom may read (its own and the
    public newsrooms'): a private newsroom's work never leaks, not even as a number."""
    if not ids:
        return {}
    key = Communique.location["original_id"].astext
    rows = await db.execute(
        select(key, func.count())
        .join(Workspace, Workspace.id == Communique.workspace_id)
        .where(
            Communique.status == "fake_caught",
            key.in_([str(i) for i in ids]),
            or_(Communique.workspace_id == viewer, Workspace.publishes),
        )
        .group_by(key)
    )
    return {k: n for k, n in rows.all()}


def _visible(viewer: uuid.UUID):
    """The entries a newsroom may read: its own, and those of every public newsroom."""
    return (
        select(Communique, Workspace)
        .join(Workspace, Workspace.id == Communique.workspace_id)
        .where(or_(Communique.workspace_id == viewer, Workspace.publishes))
    )


async def _get_visible(db: AsyncSession, member: Member, cid: uuid.UUID):
    row = (await db.execute(_visible(member.workspace_id).where(Communique.id == cid))).first()
    if row is None:
        raise ApiError(404, "not_found", "Communiqué not found")
    c, ws = row
    return c, ws


@router.get("/workspaces/{ws}/registry")
async def originals(
    member: AnyMember,
    db: Db,
    q: str = Query(default="", max_length=200),
    status: Literal["original", "fake_caught"] | None = None,
    scope: Literal["mine", "network"] = "mine",
) -> list[CommuniqueOut]:
    """`mine`: this newsroom's registry. `network`: the originals of the other public newsrooms,
    to confirm them."""
    stmt = _visible(member.workspace_id)
    if scope == "network":
        stmt = stmt.where(Communique.workspace_id != member.workspace_id)
    else:
        stmt = stmt.where(Communique.workspace_id == member.workspace_id)
    if status:
        stmt = stmt.where(Communique.status == status)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            or_(
                Communique.title.ilike(like),
                Communique.issuer.ilike(like),
                Communique.number.ilike(like),
            )
        )
    rows = (
        await db.execute(
            stmt.order_by(
                Communique.issued_on.desc().nulls_last(), Communique.created_at.desc()
            ).limit(200)
        )
    ).all()
    counts = await _fake_counts(
        db, member.workspace_id, [c.id for c, _ in rows if c.status == "original"]
    )
    return [out(c, w, member.workspace_id, counts.get(str(c.id), 0)) for c, w in rows]


@router.post("/workspaces/{ws}/registry", status_code=201)
async def register(body: OriginalIn, member: AnyMember, db: Db) -> CommuniqueOut:
    data = body.model_dump(mode="json", exclude={"place"})
    location = None
    if body.place:
        location = await places.geocode(db, body.place) or places.place(body.place)
    original = Communique(
        workspace_id=member.workspace_id,
        added_by=member.user.id,
        fingerprint=fingerprint(body.text),
        status="original",
        confirmed_by=[],
        location=location or {},
        **data,
    )
    db.add(original)
    await db.flush()
    await record(db, member.workspace_id, member.user.id, "communique", original.id, "register")
    await db.commit()
    await db.refresh(original)
    await broadcast(member.workspace_id, "registry.changed", {"id": str(original.id)})
    ws = await db.get(Workspace, member.workspace_id)
    return out(original, ws, member.workspace_id)


# --- seals: the issuer's keys ------------------------------------------------------------------


class KeyOut(BaseModel):
    key_id: str
    issuer: str
    public_key: str
    created_at: datetime
    revoked_at: datetime | None
    seals: int


async def _key_out(db: AsyncSession, key: SealKey) -> KeyOut:
    count = await db.scalar(
        select(func.count())
        .select_from(Communique)
        .where(
            Communique.workspace_id == key.workspace_id,
            Communique.sealed["key_id"].astext == key.key_id,
        )
    )
    return KeyOut(
        key_id=key.key_id,
        issuer=key.issuer,
        public_key=key.public_key,
        created_at=key.created_at,
        revoked_at=key.revoked_at,
        seals=count or 0,
    )


@router.get("/workspaces/{ws}/registry/keys")
async def seal_keys(member: AnyMember, db: Db) -> list[KeyOut]:
    stmt = select(SealKey).where(
        SealKey.workspace_id == member.workspace_id, SealKey.issuer != seal.NEWSROOM_ISSUER
    )
    keys = (await db.scalars(stmt.order_by(SealKey.created_at.desc()))).all()
    return [await _key_out(db, k) for k in keys]


@router.post("/workspaces/{ws}/registry/keys/{key_id}/revoke")
async def revoke_key(key_id: str, member: AnyMember, db: Db) -> KeyOut:
    """A lost or leaked key: its seals still check out mathematically but every page shows them
    as revoked; the next seal creates a new key."""
    key = await db.scalar(
        select(SealKey).where(SealKey.workspace_id == member.workspace_id, SealKey.key_id == key_id)
    )
    if key is None or seal.reserved_issuer(key.issuer):
        raise ApiError(404, "not_found", "Key not found")
    if key.revoked_at is None:
        key.revoked_at = datetime.now(UTC)
        await record(
            db,
            member.workspace_id,
            member.user.id,
            "seal_key",
            key.id,
            "revoke",
            {"key_id": key_id},
        )
        await db.commit()
        await db.refresh(key)
    return await _key_out(db, key)


@router.get("/workspaces/{ws}/registry/{cid}")
async def get_original(cid: uuid.UUID, member: AnyMember, db: Db) -> CommuniqueOut:
    c, ws = await _get_visible(db, member, cid)
    counts = await _fake_counts(db, member.workspace_id, [c.id])
    return out(c, ws, member.workspace_id, counts.get(str(c.id), 0))


@router.get("/workspaces/{ws}/registry/{cid}/fakes")
async def fakes_of(cid: uuid.UUID, member: AnyMember, db: Db) -> list[CommuniqueOut]:
    """The fakes caught that imitate this original, newest first (from every visible newsroom)."""
    await _get_visible(db, member, cid)
    rows = (
        await db.execute(
            _visible(member.workspace_id)
            .where(
                Communique.status == "fake_caught",
                Communique.location["original_id"].astext == str(cid),
            )
            .order_by(Communique.created_at.desc())
            .limit(100)
        )
    ).all()
    return [out(c, w, member.workspace_id) for c, w in rows]


@router.post("/workspaces/{ws}/registry/{cid}/confirm")
async def confirm(cid: uuid.UUID, member: AnyMember, db: Db) -> CommuniqueOut:
    """Another newsroom vouches for the entry (it checked with the issuer). The registering newsroom
    cannot confirm its own entry; confirming twice changes nothing."""
    c, ws = await _get_visible(db, member, cid)
    if c.status != "original":
        raise ApiError(409, "not_an_original", "Only originals can be confirmed")
    if c.workspace_id == member.workspace_id:
        raise ApiError(409, "own_entry", "A newsroom cannot confirm its own entry")
    mine = str(member.workspace_id)
    if mine not in (c.confirmed_by or []):
        c.confirmed_by = [*(c.confirmed_by or []), mine]
        await record(db, member.workspace_id, member.user.id, "communique", c.id, "confirm")
        await db.commit()
        await db.refresh(c)
        await broadcast(c.workspace_id, "registry.changed", {"id": str(c.id)})
    return out(c, ws, member.workspace_id)


@router.post("/workspaces/{ws}/registry/{cid}/fake", status_code=201)
async def record_fake(cid: uuid.UUID, body: FakeIn, member: AnyMember, db: Db) -> CommuniqueOut:
    """« Faux repéré »: a circulating copy that imitates this original, kept with its word diff so
    the next newsroom (and the Fil officiel) sees at once what was changed."""
    original, _ = await _get_visible(db, member, cid)
    if original.status != "original":
        raise ApiError(409, "not_an_original", "A fake is recorded against an original")
    found = compare(original, body.text)
    if found["status"] == "authentic":
        raise ApiError(409, "same_as_original", "This text is the original, word for word")
    fake = Communique(
        workspace_id=member.workspace_id,
        added_by=member.user.id,
        issuer=original.issuer,
        number=original.number,
        issued_on=original.issued_on,
        title=original.title,
        text=body.text,
        url=str(body.url) if body.url else None,
        fingerprint=fingerprint(body.text),
        status="fake_caught",
        confirmed_by=[],
        is_demo=original.is_demo,
        location={
            **{k: v for k, v in (original.location or {}).items() if k in PLACE_KEYS},
            "original_id": str(original.id),
            "diff": found["diff"],
            "changed_numbers": found["changed_numbers"],
            "summary": found["summary"],
            "caught_at": datetime.now(UTC).isoformat(),
        },
    )
    db.add(fake)
    await db.flush()
    await record(
        db,
        member.workspace_id,
        member.user.id,
        "communique",
        fake.id,
        "fake",
        {"original_id": str(original.id)},
    )
    await db.commit()
    await db.refresh(fake)
    await broadcast(member.workspace_id, "registry.changed", {"id": str(fake.id)})
    ws = await db.get(Workspace, member.workspace_id)
    return out(fake, ws, member.workspace_id)


# --- seals: sealing an original, and checking a seal without an account ------------------------


class SealResult(BaseModel):
    sealed: SealOut
    payload: dict[str, Any]
    public_key: str
    qr_svg: str
    # The QR only opens for everyone once the newsroom publishes its registry (« is_public »).
    public: bool


async def _seal_result(db: AsyncSession, c: Communique) -> SealResult:
    key = await db.scalar(select(SealKey).where(SealKey.key_id == c.sealed["key_id"]))
    ws = await db.get(Workspace, c.workspace_id)
    url = seal.seal_url(c.id, c.sealed)
    return SealResult(
        sealed=SealOut(
            key_id=c.sealed["key_id"],
            signature=c.sealed["signature"],
            sealed_at=c.sealed["sealed_at"],
            url=url,
        ),
        payload=c.sealed["payload"],
        public_key=key.public_key if key else "",
        qr_svg=seal.qr_svg(url),
        public=bool(ws and ws.publishes),
    )


async def _own_original(db: AsyncSession, member: Member, cid: uuid.UUID) -> Communique:
    c = await db.get(Communique, cid)
    if c is None or c.workspace_id != member.workspace_id:
        raise ApiError(404, "not_found", "Communiqué not found")
    if c.status != "original":
        raise ApiError(409, "not_an_original", "Only originals can be sealed")
    return c


async def _still_valid(db: AsyncSession, c: Communique) -> bool:
    if not (c.sealed and c.sealed.get("signature")):
        return False
    key = await db.scalar(select(SealKey).where(SealKey.key_id == c.sealed["key_id"]))
    return bool(key and key.revoked_at is None and c.sealed["payload"] == seal.payload_of(c))


@router.post("/workspaces/{ws}/registry/{cid}/seal")
async def seal_original(cid: uuid.UUID, member: AnyMember, db: Db) -> SealResult:
    """The issuer signs its original: Ed25519 over issuer, number, date, title and the text's
    fingerprint. Sealing an entry already sealed with a valid key returns the same seal."""
    c = await _own_original(db, member, cid)
    if not await _still_valid(db, c):
        await seal.seal(db, c, member.user.id, "newsroom")
        await record(
            db,
            member.workspace_id,
            member.user.id,
            "communique",
            c.id,
            "seal",
            {"key_id": c.sealed["key_id"]},
        )
        await db.commit()
        await db.refresh(c)
        await broadcast(member.workspace_id, "registry.changed", {"id": str(c.id)})
    return await _seal_result(db, c)


@router.get("/workspaces/{ws}/registry/{cid}/seal")
async def seal_of(cid: uuid.UUID, member: AnyMember, db: Db) -> SealResult:
    """The seal and its QR again (to print or download it later)."""
    c = await _own_original(db, member, cid)
    if not (c.sealed and c.sealed.get("signature")):
        raise ApiError(404, "not_sealed", "This original is not sealed")
    return await _seal_result(db, c)


class PublicSeal(BaseModel):
    id: uuid.UUID
    alg: str
    payload: dict[str, Any]
    # The exact string that was signed; the page shows the fields parsed back from it.
    message: str
    signature: str
    key_id: str
    public_key: str
    sealed_at: str
    # Sealed by the newsroom on the issuer's behalf (« issuer » on seals made before 3 Nov 2026).
    sealed_by: Literal["issuer", "newsroom"]
    revoked_at: datetime | None
    is_demo: bool
    newsroom: NewsroomOut
    url: str
    text: str


async def _public_sealed(db: AsyncSession, cid: uuid.UUID):
    row = (
        await db.execute(
            select(Communique, Workspace)
            .join(Workspace, Workspace.id == Communique.workspace_id)
            .where(Communique.id == cid, Workspace.publishes)
        )
    ).first()
    if row is None or not (row[0].sealed and row[0].sealed.get("signature")):
        raise ApiError(404, "not_found", "No public seal for this communiqué")
    c, ws = row
    key = await db.scalar(select(SealKey).where(SealKey.key_id == c.sealed["key_id"]))
    if key is None:
        raise ApiError(404, "not_found", "No public seal for this communiqué")
    return c, ws, key


@router.get("/public/sceau/{cid}")
async def public_seal(cid: uuid.UUID, db: Db) -> PublicSeal:
    """Everything a phone needs to check the seal itself: the signed fields, the exact message,
    the signature and the issuer's public key. Only public newsrooms' seals are served."""
    c, ws, key = await _public_sealed(db, cid)
    payload = c.sealed["payload"]
    return PublicSeal(
        id=c.id,
        alg=seal.ALG,
        payload=payload,
        message=seal.canonical(payload),
        signature=c.sealed["signature"],
        key_id=key.key_id,
        public_key=key.public_key,
        sealed_at=c.sealed["sealed_at"],
        sealed_by="issuer" if c.sealed.get("role") == "issuer" else "newsroom",
        revoked_at=key.revoked_at,
        is_demo=c.is_demo,
        newsroom=NewsroomOut(slug=ws.slug, name=ws.name),
        url=seal.seal_url(c.id, c.sealed),
        text=c.text,
    )


class VerifyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # The signature printed in the QR (after `#`); the stored one when absent.
    signature: str | None = Field(default=None, max_length=200)
    # A self-contained QR also carries the signed message and the key id: then the printed
    # message is what is checked, and compared with the registry.
    message: str | None = Field(default=None, max_length=4000)
    key_id: str | None = Field(default=None, max_length=40)


class VerifyOut(BaseModel):
    valid: bool
    revoked: bool
    # The registry still holds what was signed (nothing changed after sealing).
    matches_record: bool
    key_id: str


@router.post("/public/sceau/{cid}/verify")
async def verify_public_seal(cid: uuid.UUID, body: VerifyIn, db: Db) -> VerifyOut:
    """The server-side check, for browsers without Ed25519 in WebCrypto."""
    c, ws, key = await _public_sealed(db, cid)
    payload = c.sealed["payload"]
    if body.message is not None:
        found = seal.read_communique_fragment(f"{seal.b64u(body.message.encode())}.x.y")
        printed = key
        if body.key_id and body.key_id != key.key_id:
            printed = await db.scalar(
                select(SealKey).where(SealKey.key_id == body.key_id, SealKey.workspace_id == ws.id)
            )
        if found is None or printed is None or seal.reserved_issuer(printed.issuer):
            return VerifyOut(
                valid=False, revoked=False, matches_record=False, key_id=body.key_id or ""
            )
        return VerifyOut(
            valid=seal.verify_message(printed.public_key, body.message, body.signature or ""),
            revoked=printed.revoked_at is not None,
            matches_record=found[0] == seal.payload_of(c),
            key_id=printed.key_id,
        )
    return VerifyOut(
        valid=seal.verify(key.public_key, payload, body.signature or c.sealed["signature"]),
        revoked=key.revoked_at is not None,
        matches_record=payload == seal.payload_of(c),
        key_id=key.key_id,
    )


class PublicKeyOut(BaseModel):
    key_id: str
    issuer: str
    # `verdict`: a newsroom's own key for its verdict cards; `communique`: an issuer's key.
    kind: Literal["communique", "verdict"] = "communique"
    alg: str
    public_key: str
    created_at: datetime
    newsroom: NewsroomOut


class RevokedKeyOut(BaseModel):
    key_id: str
    issuer: str
    kind: Literal["communique", "verdict"] = "communique"
    revoked_at: datetime
    newsroom: NewsroomOut


class SealKeysOut(BaseModel):
    keys: list[PublicKeyOut]
    revoked: list[RevokedKeyOut]


@router.get("/public/seal-keys")
async def public_seal_keys(db: Db) -> SealKeysOut:
    """The issuers' public keys (to check seals offline) and the revoked ones."""
    rows = (
        await db.execute(
            select(SealKey, Workspace)
            .join(Workspace, Workspace.id == SealKey.workspace_id)
            .where(Workspace.publishes)
            .order_by(SealKey.created_at.desc())
            .limit(1000)
        )
    ).all()
    keys, revoked = [], []
    for key, ws in rows:
        room = NewsroomOut(slug=ws.slug, name=ws.name)
        kind = "verdict" if key.issuer == seal.NEWSROOM_ISSUER else "communique"
        if key.revoked_at:
            revoked.append(
                RevokedKeyOut(
                    key_id=key.key_id,
                    issuer=key.issuer,
                    kind=kind,
                    revoked_at=key.revoked_at,
                    newsroom=room,
                )
            )
        else:
            keys.append(
                PublicKeyOut(
                    key_id=key.key_id,
                    issuer=key.issuer,
                    kind=kind,
                    alg=seal.ALG,
                    public_key=key.public_key,
                    created_at=key.created_at,
                    newsroom=room,
                )
            )
    return SealKeysOut(keys=keys, revoked=revoked)


# --- Fil officiel: the public newsrooms' originals and the fakes they caught -------------------


class OriginalRef(BaseModel):
    id: uuid.UUID
    issuer: str
    number: str | None
    issued_on: str | None
    title: str


class OfficialOut(BaseModel):
    id: uuid.UUID
    kind: Literal["original", "fake_caught"]
    issuer: str
    number: str | None
    issued_on: str | None
    title: str
    text: str
    url: str | None
    is_demo: bool
    created_at: datetime
    newsroom: NewsroomOut
    confirmed: bool
    sealed: bool
    seal_url: str | None
    fakes: int = 0
    original: OriginalRef | None = None
    diff: list[DiffOp] = []
    changed_numbers: list[ChangedNumber] = []
    summary: str | None = None


class OfficialPage(BaseModel):
    items: list[OfficialOut]
    total: int


@router.get("/public/registry")
async def official_feed(
    db: Db,
    newsroom: str = Query(default="", max_length=140),
    q: str = Query(default="", max_length=200),
    kind: Literal["original", "fake_caught"] | None = None,
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> OfficialPage:
    """« Fil officiel »: what the institutions really published and the fakes caught imitating it,
    newest first. Only newsrooms that publish (`is_public`) appear; a fake whose original is not
    public is left out (its diff would show the original's words)."""
    stmt = (
        select(Communique, Workspace)
        .join(Workspace, Workspace.id == Communique.workspace_id)
        .where(Workspace.publishes)
    )
    if newsroom:
        stmt = stmt.where(Workspace.slug == newsroom)
    if kind:
        stmt = stmt.where(Communique.status == kind)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            or_(
                Communique.title.ilike(like),
                Communique.issuer.ilike(like),
                Communique.number.ilike(like),
                Communique.text.ilike(like),
            )
        )
    rows = (await db.execute(stmt.order_by(Communique.created_at.desc()).limit(1000))).all()
    wanted = {(c.location or {}).get("original_id") for c, _ in rows if c.status == "fake_caught"}
    public_originals = {
        str(c.id): c
        for c, _ in (
            await db.execute(
                select(Communique, Workspace)
                .join(Workspace, Workspace.id == Communique.workspace_id)
                .where(
                    Workspace.publishes,
                    Communique.id.in_([uuid.UUID(i) for i in wanted if i]),
                )
            )
        ).all()
    }
    kept = [
        (c, w)
        for c, w in rows
        if c.status == "original" or (c.location or {}).get("original_id") in public_originals
    ]
    page = kept[offset : offset + limit]
    counts = await _public_fake_counts(db, [c.id for c, _ in page if c.status == "original"])
    items = []
    for c, w in page:
        loc = c.location or {}
        original = public_originals.get(loc.get("original_id") or "")
        signature = (c.sealed or {}).get("signature")
        items.append(
            OfficialOut(
                id=c.id,
                kind=c.status,
                issuer=c.issuer,
                number=c.number,
                issued_on=c.issued_on,
                title=c.title,
                text=c.text,
                url=c.url,
                is_demo=c.is_demo,
                created_at=c.created_at,
                newsroom=NewsroomOut(slug=w.slug, name=w.name),
                confirmed=1 + len(c.confirmed_by or []) >= CONFIRMED_AT,
                sealed=bool(signature),
                seal_url=seal_url(c.id, c.sealed) if signature else None,
                fakes=counts.get(str(c.id), 0),
                original=OriginalRef(
                    id=original.id,
                    issuer=original.issuer,
                    number=original.number,
                    issued_on=original.issued_on,
                    title=original.title,
                )
                if original
                else None,
                diff=loc.get("diff") or [],
                changed_numbers=loc.get("changed_numbers") or [],
                summary=loc.get("summary"),
            )
        )
    return OfficialPage(items=items, total=len(kept))


async def _public_fake_counts(db: AsyncSession, ids: list[uuid.UUID]) -> dict[str, int]:
    if not ids:
        return {}
    key = Communique.location["original_id"].astext
    rows = await db.execute(
        select(key, func.count())
        .join(Workspace, Workspace.id == Communique.workspace_id)
        .where(
            Communique.status == "fake_caught",
            key.in_([str(i) for i in ids]),
            Workspace.publishes,
        )
        .group_by(key)
    )
    return {k: n for k, n in rows.all()}


# --- word by word -----------------------------------------------------------------------------


def _key(token: str) -> str:
    """What a word is compared on: case, accents and stuck punctuation do not count."""
    return re.sub(r"[^a-z0-9%]", "", places.fold(token)) or token


def word_diff(original: str, submitted: str) -> list[dict[str, str]]:
    """`[{op, a, b}]` over words (difflib): `a` holds the original's words, `b` the copy's."""
    a, b = normalise(original).split(), normalise(submitted).split()
    matcher = difflib.SequenceMatcher(None, [_key(t) for t in a], [_key(t) for t in b], False)
    return [
        {"op": tag, "a": " ".join(a[i1:i2]), "b": " ".join(b[j1:j2])}
        for tag, i1, i2, j1, j2 in matcher.get_opcodes()
    ][:400]


def changed_numbers(original: str, submitted: str) -> list[dict[str, Any]]:
    """The numbers the copy states that the original does not: each paired with the original's
    number of the same kind it replaces (« 4 heures par jour » → « 72 heures »), or alone when it
    was added (« 40 % »)."""
    theirs = numbers.extract_numbers(original)
    ours = numbers.extract_numbers(submitted)
    spare = list(theirs)
    moved = []
    for o in ours:
        twin = next((t for t in theirs if t["kind"] == o["kind"] and numbers.same(o, t)), None)
        if twin is not None:
            if twin in spare:
                spare.remove(twin)
            continue
        moved.append(o)
    changes = []
    for o in moved:
        pair = next((t for t in spare if t["kind"] == o["kind"]), None)
        if pair is not None:
            spare.remove(pair)
        changes.append(
            {
                "kind": o["kind"],
                "original": pair["claimed"] if pair else None,
                "submitted": o["claimed"],
            }
        )
    return changes


def reference(c: Communique) -> str:
    """« le communiqué N° 2026-118 du 1er novembre 2026 (JIRAMA) »: the issuer goes in brackets, so
    the sentence reads right whatever its name (« de JIRAMA », « de Ministère … » would not)."""
    parts = ["le communiqué"]
    if c.number:
        parts.append(f"N° {c.number}")
    if day := dates.parse(c.issued_on):
        parts.append(f"du {dates.fr(day)}")
    parts.append(f"({c.issuer})")
    return " ".join(parts)


def _authentic(ops: list[dict[str, str]]) -> bool:
    """The original's words, in order and unchanged: either the whole original with something added
    before or after it (a forwarding line), or a verbatim excerpt of it (12 words at least)."""
    changed = [i for i, o in enumerate(ops) if o["op"] != "equal"]
    if not changed:
        return True
    if sum(len(o["a"].split()) for o in ops if o["op"] == "equal") < 12:
        return False
    kinds = {ops[i]["op"] for i in changed}
    return set(changed) <= {0, len(ops) - 1} and kinds in ({"insert"}, {"delete"})


def compare(original: Communique, submitted: str) -> dict[str, Any]:
    """`authentic` or `modified`, with the word diff, the numbers changed and a sentence."""
    ops = word_diff(original.text, submitted)
    ref = reference(original)
    if _authentic(ops):
        return {
            "status": "authentic",
            "diff": ops,
            "changed_numbers": [],
            "summary": f"Ce texte reprend mot pour mot {ref}, enregistré au registre.",
        }
    moved = changed_numbers(original.text, submitted)
    said = []
    for n in moved[:4]:
        if n["original"]:
            said.append(f"« {n['original']} » y devient « {n['submitted']} »")
        else:
            said.append(f"« {n['submitted']} » n'y figure pas")
    edits = sum(1 for o in ops if o["op"] != "equal")
    plural = "s" if edits > 1 else ""
    detail = " ; ".join(said) if said else f"{edits} passage{plural} changé{plural}"
    return {
        "status": "modified",
        "diff": ops,
        "changed_numbers": moved,
        "summary": f"{ref[0].upper()}{ref[1:]} est au registre, mais ce texte en diffère : "
        f"{detail}.",
    }


# --- match_text: which original a circulating text quotes, and how it differs ------------------

# Institutions people quote; the newsroom's Annuaire and the registry itself add the rest. Generic
# words (« ministère », « préfecture »…) take the capitalised words after them as the name.
INSTITUTIONS = (
    "JIRAMA",
    "CENI",
    "BNGRC",
    "INSTAT",
    "ORE",
    "ARTEC",
    "CNaPS",
    "OMNIS",
    "APMF",
    "ACM",
    "CUA",
    "HCC",
    "Banky Foiben'i Madagasikara",
    "Banque centrale de Madagascar",
    "Présidence de la République",
    "Primature",
    "Assemblée nationale",
    "Sénat",
    "Gendarmerie nationale",
    "Police nationale",
    "Météo Madagascar",
    "Institut Pasteur de Madagascar",
    "Commune urbaine d'Antananarivo",
)
_GENERIC = re.compile(
    r"\b(minist[eè]re|pr[ée]fecture|commune|r[ée]gion|district|mairie|direction|gendarmerie|police)"
    r"\s+(?:de\s+la\s+|de\s+l['’]|des\s+|du\s+|de\s+|d['’])?"
    r"((?:[A-ZÀ-Ý][\w'’-]+)(?:\s+(?:et\s+de\s+la\s+|et\s+|de\s+la\s+|de\s+l['’]|des\s+|du\s+|de\s+)?[A-ZÀ-Ý][\w'’-]+){0,3})",
    re.IGNORECASE,
)
_NUMBER = re.compile(
    r"\b(?:n\s?[°ºo]|no\.?|num[ée]ro|laharana)\s*[:.]?\s*(\d[\w/.-]*[0-9A-Za-z]|\d)", re.IGNORECASE
)
# Words every communiqué shares, which say nothing about which one is quoted.
_GENERIC_WORDS = {"communique", "urgent", "officiel", "officielle", "annonce", "informe", "selon"}
Status = Literal["authentic", "modified", "not_found", "inconsistent", "none"]


def quoted_numbers(text: str) -> list[str]:
    """Communiqué numbers the text cites (« N° 2026-118 », « n°118/2026/MEN »)."""
    seen: list[str] = []
    for m in _NUMBER.finditer(text or ""):
        n = m[1].strip(".-/")
        if n and n not in seen:
            seen.append(n)
    return seen


def _num_key(n: str | None) -> str:
    return re.sub(r"[^0-9a-z]", "", places.fold(n or ""))


def _aliases(name: str) -> set[str]:
    """How an issuer may be written: its full name, the part before a bracket or a dash, and its
    acronyms (« JIRAMA (Jiro sy Rano Malagasy) » → jirama, jiro sy rano malagasy)."""
    found = {name, re.split(r"\s[(–—-]\s?|\(", name)[0]}
    found |= set(re.findall(r"\b[A-Z][A-Za-z]*[A-Z]{2,}\b|\b[A-Z]{3,}\b", name))
    inner = re.search(r"\(([^)]+)\)", name)
    if inner:
        found.add(inner[1])
    out = set()
    for alias in found:
        alias = re.sub(r"\(\s*d[ée]mo\s*\)", "", alias, flags=re.IGNORECASE)
        folded = " ".join(re.findall(r"[a-z0-9']+", places.fold(alias)))
        if len(folded) >= 3:
            out.add(folded)
    return out


def _mentions(folded_text: str, name: str) -> bool:
    return any(
        re.search(rf"(?<![a-z0-9]){re.escape(a)}(?![a-z0-9])", folded_text) for a in _aliases(name)
    )


async def institution_names(db: AsyncSession, workspace_id: uuid.UUID) -> list[str]:
    """Institutions of the newsroom's Annuaire (slice « dossier » may expose its own list)."""
    try:
        from app.modules.directory import institutions  # type: ignore[attr-defined]

        return list(await institutions(db, workspace_id))
    except (ImportError, AttributeError, TypeError):
        pass
    from app.core.models import Contact

    rows = (
        await db.execute(
            select(Contact.kind, Contact.name, Contact.institution)
            .where(or_(Contact.workspace_id == workspace_id, Contact.shared.is_(True)))
            .limit(500)
        )
    ).all()
    names = set()
    for kind, name, institution in rows:
        if institution:
            names.add(institution)
        if kind == "institution" and name:
            names.add(name)
    return [re.sub(r"\s*\(d[ée]mo\)\s*", "", n, flags=re.IGNORECASE).strip() for n in names if n]


async def press_contacts(db: AsyncSession, workspace_id: uuid.UUID, issuer: str) -> list[dict]:
    """Who at the issuer can confirm a communiqué: the newsroom's Annuaire entries (and the shared
    ones) for that institution, press officers first. Only names and roles: the Annuaire has the rest."""
    from app.core.models import Contact

    rows = (
        await db.scalars(
            select(Contact)
            .where(or_(Contact.workspace_id == workspace_id, Contact.shared.is_(True)))
            .limit(500)
        )
    ).all()
    folded = places.fold(issuer)
    hits = [
        c
        for c in rows
        if any(
            n and (_mentions(places.fold(n), issuer) or _mentions(folded, n))
            for n in (c.institution, c.name if c.kind == "institution" else "")
        )
    ]
    hits.sort(key=lambda c: (c.kind != "officer", c.workspace_id != workspace_id, c.name))
    return [
        {
            "id": str(c.id),
            "name": c.name,
            "role": c.role,
            "institution": c.institution,
            "kind": c.kind,
        }
        for c in hits[:3]
    ]


def quoted_issuers(text: str, known: list[str]) -> list[str]:
    """Institutions the text names, longest names first: known ones (registry, Annuaire, the list
    above), then « ministère de la Santé »-like names read from the text itself."""
    folded = places.fold(text or "")
    found = [name for name in sorted(set(known), key=len, reverse=True) if _mentions(folded, name)]
    for m in _GENERIC.finditer(text or ""):
        phrase = re.sub(r"\s+", " ", m.group(0)).strip()
        if not any(
            _mentions(places.fold(phrase), f) or _mentions(places.fold(f), phrase) for f in found
        ):
            found.append(phrase[0].upper() + phrase[1:])
    return found


def _shape(n: str) -> str:
    """A number's format: digit runs as 9, letters as A, separators kept (2026-118 → 9-9)."""
    return re.sub(r"[a-z]+", "A", re.sub(r"\d+", "9", places.fold(n)))


def _out_of_sequence(number: str, registered: list[str]) -> str | None:
    """Why a cited number cannot belong to the issuer's series, or None when it could."""
    years = [int(y) for y in re.findall(r"(?<!\d)(19\d\d|20\d\d)(?!\d)", number)]
    if any(y > dates.today().year for y in years):
        return "future_year"
    shapes = {_shape(n) for n in registered if n}
    if len(registered) >= 2 and len(shapes) == 1 and _shape(number) not in shapes:
        return "format"
    return None


def _brief(c: Communique, ws: Workspace, viewer: uuid.UUID) -> dict[str, Any]:
    entry = out(c, ws, viewer).model_dump(mode="json")
    keep = ("id", "issuer", "number", "issued_on", "title", "url", "is_demo", "own", "newsroom")
    brief = {k: entry[k] for k in keep}
    brief["text"] = c.text
    brief["confirmed"] = entry["confirmed"]
    brief["sealed"] = bool(entry["sealed"])
    brief["seal_url"] = entry["sealed"]["url"] if entry["sealed"] else None
    return brief


def _result(
    status: Status, issuer, number, communique=None, found=None, summary="", contacts=None
) -> dict:
    found = found or {}
    return {
        "status": status,
        "issuer": issuer,
        "number": number,
        "communique": communique,
        "diff": found.get("diff", []),
        "changed_numbers": found.get("changed_numbers", []),
        "summary": found.get("summary") or summary,
        # Who can confirm, from the Annuaire, when nothing registered settles it.
        "contacts": contacts or [],
    }


async def match_text(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    text: str,
    *,
    with_contacts: bool = True,
) -> dict[str, Any]:
    """Which registered original a circulating text quotes, from this newsroom's registry and every
    public newsroom's, and how it differs: `authentic` (same words), `modified` (the number exists,
    the words differ: `diff` and `changed_numbers`), `not_found` (an institution or a number is
    cited, nothing registered matches: « Introuvable », never « Faux »), `inconsistent` (the number
    cannot belong to the issuer's series) or `none` (no institution or communiqué is cited)."""
    text = (text or "").strip()
    stmt = _visible(workspace_id).where(Communique.status == "original")
    rows = (await db.execute(stmt.order_by(Communique.created_at.desc()).limit(500))).all()
    # This newsroom's own entries first, then sealed ones, then the newest.
    rows.sort(key=lambda r: (r[0].workspace_id != workspace_id, not r[0].sealed))
    folded = places.fold(text)
    cited = quoted_numbers(text)
    registered_issuers = sorted({c.issuer for c, _ in rows})
    annuaire = await institution_names(db, workspace_id)
    issuers = quoted_issuers(text, [*registered_issuers, *annuaire, *INSTITUTIONS])

    # 1. The number cited, from the issuer cited (or any issuer when none is named).
    for number in cited:
        hits = [(c, w) for c, w in rows if c.number and _num_key(c.number) == _num_key(number)]
        named = [(c, w) for c, w in hits if _mentions(folded, c.issuer)]
        if named or (hits and not issuers):
            c, w = (named or hits)[0]
            return _result(
                "authentic" if compare(c, text)["status"] == "authentic" else "modified",
                c.issuer,
                c.number,
                _brief(c, w, workspace_id),
                compare(c, text),
            )

    # 2. The words: the original that holds most of what circulates (35 % at least, 4 words).
    asked = words(text) - _GENERIC_WORDS - {w for w in words(text) if w.isdigit()}
    for name in issuers:
        asked -= words(name)
    best, best_score = None, 0.0
    for c, w in rows:
        if issuers and not _mentions(folded, c.issuer):
            continue
        shared = asked & words(f"{c.title} {c.text}")
        score = len(shared) / max(1, len(asked))
        if len(shared) >= 4 and score > best_score:
            best, best_score = (c, w), score
    if best and best_score >= 0.35:
        c, w = best
        found = compare(c, text)
        return _result(found["status"], c.issuer, c.number, _brief(c, w, workspace_id), found)

    # 3. Nothing registered matches.
    issuer = issuers[0] if issuers else None
    number = cited[0] if cited else None
    if not issuer and not number:
        return _result("none", None, None, summary="Ce texte ne cite ni institution ni communiqué.")
    who = f" de {issuer}" if issuer else ""
    contacts = await press_contacts(db, workspace_id, issuer) if issuer and with_contacts else []
    if issuer and number:
        series = [
            c.number for c, _ in rows if c.number and _mentions(places.fold(issuer), c.issuer)
        ]
        why = _out_of_sequence(number, series)
        if why:
            example = next((n for n in series if n), None)
            reason = (
                "porte une année à venir"
                if why == "future_year"
                else "ne suit pas la numérotation de ses communiqués enregistrés "
                f"(par exemple N° {example})"
            )
            return _result(
                "inconsistent",
                issuer,
                number,
                summary=(
                    f"Le numéro N° {number} cité pour {issuer} {reason}. Seul l'émetteur peut "
                    "confirmer qu'un communiqué existe."
                ),
                contacts=contacts,
            )
    cited_as = f"Aucun communiqué N° {number}{who}" if number else f"Aucun communiqué{who}"
    return _result(
        "not_found",
        issuer,
        number,
        summary=(
            f"{cited_as} ne correspond à ce texte dans le registre. Introuvable ne veut pas dire "
            f"faux : le registre n'est jamais complet, seul l'émetteur peut confirmer."
        ),
        contacts=contacts,
    )


class MatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=3, max_length=30000)


@router.post("/workspaces/{ws}/registry/match")
async def match(body: MatchIn, member: AnyMember, db: Db) -> dict:
    """Compare a circulating text with the registered originals (no model involved)."""
    return await match_text(db, member.workspace_id, body.text)


# Kept for the first crew graph, which reads the older shape; new callers use `match_text`.
async def compare_text(ws: uuid.UUID, text: str) -> dict:
    async with SessionLocal() as db:
        rows = (
            await db.scalars(
                select(Communique)
                .where(Communique.workspace_id == ws, Communique.status == "original")
                .order_by(Communique.created_at.desc())
                .limit(200)
            )
        ).all()
    asked = words(text)
    ranked = sorted(
        (
            (len(asked & words(row.text)) / max(1, len(asked | words(row.text))), row)
            for row in rows
        ),
        key=lambda pair: pair[0],
        reverse=True,
    )
    if not ranked or ranked[0][0] < 0.35:
        return {"status": "not_found", "authenticity": "not_established"}
    best = ranked[0][1]
    ops = word_diff(best.text, text)
    return {
        "status": "text_match" if all(o["op"] == "equal" for o in ops) else "differences",
        "original_id": str(best.id),
        "title": best.title,
        "issuer": best.issuer,
        "url": best.url,
        "is_demo": best.is_demo,
        "changes": [
            {"operation": o["op"], "original": o["a"], "submitted": o["b"]} for o in ops[:100]
        ],
        "authenticity": "not_established",
        "match_method": "candidate_text_similarity",
    }


# --- demo --------------------------------------------------------------------------------------

# Fictional originals (flagged démo): the JIRAMA communiqué the pitch rumour doctors (4 hours a day,
# not 72), and an exam calendar with a fake caught that imitates it (FAN-0140's rumour).
DEMO_ORIGINALS = [
    {
        "key": "jirama-2026-118",
        "issuer": "JIRAMA",
        "number": "2026-118",
        "issued_on": "2026-11-01",
        "title": "Programme de délestage à Antananarivo du 3 au 9 novembre 2026 (démo)",
        "text": (
            "COMMUNIQUÉ N° 2026-118. La JIRAMA informe ses abonnés d'Antananarivo qu'en raison de "
            "travaux de maintenance sur la centrale hydroélectrique d'Andekaleka, un délestage de 4 "
            "heures par jour et par quartier sera appliqué du 3 au 9 novembre 2026, selon un "
            "programme tournant publié chaque matin sur ses pages officielles. Les hôpitaux et les "
            "stations de pompage d'eau ne sont pas concernés. La JIRAMA présente ses excuses pour "
            "la gêne occasionnée."
        ),
        "place": "Antananarivo",
        "seal": True,
    },
    {
        "key": "men-2026-311",
        "issuer": "Ministère de l'Éducation nationale",
        "number": "2026-311",
        "issued_on": "2026-10-20",
        "title": "Calendrier des épreuves écrites du baccalauréat 2026 (démo)",
        "text": (
            "Le ministère de l'Éducation nationale rappelle que les épreuves écrites du "
            "baccalauréat 2026 débuteront le 24 novembre 2026 sur l'ensemble du territoire, "
            "conformément au calendrier publié en août. Aucun report n'est prévu à ce jour."
        ),
        "place": "Madagascar",
        "seal": False,
        "fake": (
            "Le ministère de l'Éducation nationale annonce que les épreuves écrites du "
            "baccalauréat 2026 sont reportées au 15 décembre 2026 sur l'ensemble du territoire. "
            "Partagez !"
        ),
    },
]


def demo_id(workspace_id: uuid.UUID, key: str) -> uuid.UUID:
    """The same id after every demo reset, so a printed demo QR keeps working."""
    return uuid.uuid5(uuid.NAMESPACE_URL, f"checky:demo:{workspace_id}:{key}")


async def seed_demo(db: AsyncSession, workspace_id, user_id, items) -> None:
    """The fictional originals of the demo, the JIRAMA one sealed when SEAL_SECRET is set, and one
    fake caught. Idempotent: the newsroom's demo entries are replaced."""
    await db.execute(
        Communique.__table__.delete().where(
            Communique.workspace_id == workspace_id, Communique.is_demo.is_(True)
        )
    )
    for spec in DEMO_ORIGINALS:
        c = Communique(
            id=demo_id(workspace_id, spec["key"]),
            workspace_id=workspace_id,
            added_by=user_id,
            issuer=spec["issuer"],
            number=spec["number"],
            issued_on=spec["issued_on"],
            title=spec["title"],
            text=spec["text"],
            fingerprint=fingerprint(spec["text"]),
            status="original",
            confirmed_by=[],
            location=places.gazetteer(spec["place"]) or {},
            is_demo=True,
        )
        db.add(c)
        await db.flush()
        if spec["seal"] and seal.available():
            await seal.seal(db, c, user_id, "newsroom")
        if spec.get("fake"):
            found = compare(c, spec["fake"])
            db.add(
                Communique(
                    id=demo_id(workspace_id, spec["key"] + ":fake"),
                    workspace_id=workspace_id,
                    added_by=user_id,
                    issuer=c.issuer,
                    number=c.number,
                    issued_on=c.issued_on,
                    title=c.title,
                    text=spec["fake"],
                    fingerprint=fingerprint(spec["fake"]),
                    status="fake_caught",
                    confirmed_by=[],
                    is_demo=True,
                    location={
                        **(c.location or {}),
                        "original_id": str(c.id),
                        "diff": found["diff"],
                        "changed_numbers": found["changed_numbers"],
                        "summary": found["summary"],
                        "caught_at": datetime.now(UTC).isoformat(),
                    },
                )
            )
    await db.flush()
