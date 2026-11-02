"""The Registre: originals of communiqués, decrees and notices as their issuers published them, so a
circulating copy can be compared word by word (Authentique / Modifié / Introuvable / Incohérent).

A match proves that the words correspond to a registered original, not that the original says
something true. « Introuvable » never means « Faux »: the registry is never complete, only the
issuer can confirm. Who may write: the institution's own account (`issuer`) or the newsroom's
editors and admins; another newsroom confirms an entry (« vérifié » once two newsrooms vouch).
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

from app.core import dates, numbers, places
from app.core.access import AnyMember, Anyone, Db, Issuer, Member
from app.core.activity import broadcast, record
from app.core.db import SessionLocal
from app.core.errors import ApiError
from app.core.models import Communique, Workspace
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


def _ensure_reader(member: Member) -> None:
    # A veilleur reports what was heard; the registry is the desk's and the issuers'.
    if member.role == "veilleur":
        raise ApiError(403, "forbidden", "Registry access requires a desk or issuer role")


def out(c: Communique, ws: Workspace | None, viewer: uuid.UUID, fakes: int = 0) -> CommuniqueOut:
    loc = c.location or {}
    sealed = None
    if c.sealed and c.sealed.get("signature"):
        sealed = SealOut(
            key_id=c.sealed["key_id"],
            signature=c.sealed["signature"],
            sealed_at=c.sealed["sealed_at"],
            url=seal_url(c.id, c.sealed["signature"]),
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
        newsroom=NewsroomOut(slug=ws.slug, name=ws.name) if ws and ws.is_public else None,
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
            or_(Communique.workspace_id == viewer, Workspace.is_public.is_(True)),
        )
        .group_by(key)
    )
    return {k: n for k, n in rows.all()}


def _visible(viewer: uuid.UUID):
    """The entries a newsroom may read: its own, and those of every public newsroom."""
    return (
        select(Communique, Workspace)
        .join(Workspace, Workspace.id == Communique.workspace_id)
        .where(or_(Communique.workspace_id == viewer, Workspace.is_public.is_(True)))
    )


async def _get_visible(db: AsyncSession, member: Member, cid: uuid.UUID):
    row = (await db.execute(_visible(member.workspace_id).where(Communique.id == cid))).first()
    if row is None:
        raise ApiError(404, "not_found", "Communiqué not found")
    c, ws = row
    # An institution's account keeps to its own entries.
    if member.role == "issuer" and (
        c.workspace_id != member.workspace_id or c.added_by != member.user.id
    ):
        raise ApiError(404, "not_found", "Communiqué not found")
    return c, ws


@router.get("/workspaces/{ws}/registry")
async def originals(
    member: Anyone,
    db: Db,
    q: str = Query(default="", max_length=200),
    status: Literal["original", "fake_caught"] | None = None,
    scope: Literal["mine", "network"] = "mine",
) -> list[CommuniqueOut]:
    """`mine`: this newsroom's registry (an issuer sees only what it registered). `network`: the
    originals of the other public newsrooms, to confirm them."""
    _ensure_reader(member)
    stmt = _visible(member.workspace_id)
    if scope == "network" and member.role != "issuer":
        stmt = stmt.where(Communique.workspace_id != member.workspace_id)
    else:
        stmt = stmt.where(Communique.workspace_id == member.workspace_id)
        if member.role == "issuer":
            stmt = stmt.where(Communique.added_by == member.user.id)
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
async def register(body: OriginalIn, member: Issuer, db: Db) -> CommuniqueOut:
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


@router.get("/workspaces/{ws}/registry/{cid}")
async def get_original(cid: uuid.UUID, member: Anyone, db: Db) -> CommuniqueOut:
    _ensure_reader(member)
    c, ws = await _get_visible(db, member, cid)
    counts = await _fake_counts(db, member.workspace_id, [c.id])
    return out(c, ws, member.workspace_id, counts.get(str(c.id), 0))


@router.get("/workspaces/{ws}/registry/{cid}/fakes")
async def fakes_of(cid: uuid.UUID, member: Anyone, db: Db) -> list[CommuniqueOut]:
    """The fakes caught that imitate this original, newest first (from every visible newsroom)."""
    _ensure_reader(member)
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
async def record_fake(cid: uuid.UUID, body: FakeIn, member: Anyone, db: Db) -> CommuniqueOut:
    """« Faux repéré »: a circulating copy that imitates this original, kept with its word diff so
    the next newsroom (and the Fil officiel) sees at once what was changed."""
    _ensure_reader(member)
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
    number of the same kind it replaces (« 4 heures par jour » → « 72 heures »), or alone when it was
    added (« 40 % »)."""
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
    """« le communiqué N° 2026-118 de JIRAMA du 1er novembre 2026 »"""
    parts = ["le communiqué"]
    if c.number:
        parts.append(f"N° {c.number}")
    parts.append(f"de {c.issuer}")
    if day := dates.parse(c.issued_on):
        parts.append(f"du {dates.fr(day)}")
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
        "summary": f"{ref[0].upper()}{ref[1:]} est au registre, mais ce texte en diffère : {detail}.",
    }


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
