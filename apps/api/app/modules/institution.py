"""The institution portal (brief 3.3–3.5, 8.1): an institution seals its own communiqués, declares
its official pages, numbers and press officer, and sees the fakes that use its name.

An institution is a workspace of kind `institution`, created from onboarding and verified by the
Checky team exactly like a newsroom (verification.py); there are no roles inside it. Until it is
verified it works privately: its seals, pages and numbers reach nobody (`Workspace.publishes`, and
its Annuaire entries stay unshared).

- Communiqués: the PDF goes through the ordinary upload (`…/files/upload-url`), then `…/read`
  reads issuer, number, date, title and text from it (the registry's own readers) for the press
  office to correct; `…/communiques` assigns or checks the chronological number against the
  institution's own series (« Incohérent » when it breaks it), seals the entry with the
  institution's Ed25519 key (`seal.py`, issuer = the institution, role `issuer`) and keeps it in
  the registry, where an issuer-signed entry counts as verified. `…/pdf` returns the PDF with the
  QR stamped on its first page. Keys and revocation are the registry's (`…/registry/keys`); the
  revoked list reaches phones through `/public/seal-keys`.
- « Alerte faux »: every registry match (`registry.match_text`, used by the desk, the public
  check, the extension and the phone) that ends Modifié, Introuvable or Incohérent on a text that
  names a verified institution, and every fake a newsroom records, lands in that institution's
  alerts (one row per distinct text; which newsroom checked it is never kept). The press office
  answers with a sealed denial.
- Profile: official pages and sites (« Page officielle ? »), official numbers (« Numéro
  officiel ? ») and the press officer (« Qui peut le prouver ? », the Annuaire), written as two
  Annuaire entries of the institution, shared with every newsroom once it is verified and marked
  « Vérifié le … par [institution] ».
"""

import hashlib
import io
import logging
import re
import uuid
from datetime import UTC, date, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import countries, dates, places, seal, storage
from app.core.access import AnyMember, Db, Member
from app.core.activity import broadcast, record
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.errors import ApiError
from app.core.models import (
    Communique,
    Contact,
    File,
    InstitutionAlert,
    Membership,
    NewsroomRequest,
    Workspace,
)
from app.modules.registry import CommuniqueOut, SealResult

log = logging.getLogger("checky.institution")
router = APIRouter(tags=["institution"])

DEMO_NAME = "Ministère de démo (démo)"
ALERT_STATUSES = ("modified", "not_found", "inconsistent", "fake_caught")
Channel = Literal["desk", "public", "extension", "phone", "sms"]


async def require_institution(member: AnyMember, db: Db) -> Member:
    ws = await db.get(Workspace, member.workspace_id)
    if ws is None or ws.kind != "institution":
        raise ApiError(404, "not_found", "Institution not found")
    return member


Institution = Annotated[Member, Depends(require_institution)]


def aliases_of(ws: Workspace) -> list[str]:
    """The institution's name and the other names it declared (acronym, Malagasy name)."""
    extra = (ws.settings or {}).get("aliases") or []
    return [ws.name, *[a for a in extra if isinstance(a, str) and a.strip()]]


def _named(text: str, names: list[str]) -> bool:
    from app.modules.registry import _mentions

    folded = places.fold(text or "")
    return any(_mentions(folded, n) for n in names if n)


async def verified_institutions(db: AsyncSession) -> list[Workspace]:
    return list(
        await db.scalars(
            select(Workspace).where(
                Workspace.kind == "institution", Workspace.verification == "approved"
            )
        )
    )


async def institution_names(db: AsyncSession) -> list[str]:
    """Every name of every verified institution, for the registry's issuer reading."""
    return [n for ws in await verified_institutions(db) for n in aliases_of(ws)]


async def signing_institution(db: AsyncSession, issuer: str) -> Workspace | None:
    """The verified institution this issuer name designates: it seals its own communiqués, so a
    newsroom no longer seals on its behalf (« a real institution is named as a signer only once it
    has signed »)."""
    for ws in await verified_institutions(db):
        names = aliases_of(ws)
        if _named(issuer, names) or any(_named(n, [issuer]) for n in names):
            return ws
    return None


# --- « Alerte faux » ---------------------------------------------------------------------------


async def raise_alerts(
    found: dict[str, Any],
    text: str,
    *,
    channel: str = "desk",
    url: str | None = None,
    image_url: str | None = None,
) -> int:
    """Record the check in the alerts of every verified institution the text names. Runs in its
    own session (the caller's transaction is left alone) and never raises: a check never fails
    because an alert could not be written. Returns how many institutions were alerted."""
    status = found.get("status")
    text = (text or "").strip()
    if status not in ALERT_STATUSES or len(text) < 5:
        return 0
    issuer = str(found.get("issuer") or "")
    original = found.get("communique") if isinstance(found.get("communique"), dict) else {}
    original_id = original.get("id") or found.get("original_id")
    try:
        async with SessionLocal() as db:
            hit = []
            for ws in await verified_institutions(db):
                names = aliases_of(ws)
                if _named(text, names) or (issuer and _named(issuer, names)):
                    hit.append(ws)
            for ws in hit:
                values = {
                    "id": uuid.uuid4(),
                    "workspace_id": ws.id,
                    "status": status,
                    "channel": channel,
                    "text": text[:4000],
                    "fingerprint": seal.fingerprint(text),
                    "url": url,
                    "image_url": image_url,
                    "summary": (found.get("summary") or "")[:1000] or None,
                    "number": (found.get("number") or None),
                    "original_id": uuid.UUID(str(original_id)) if original_id else None,
                }
                stmt = insert(InstitutionAlert).values(**values)
                stmt = stmt.on_conflict_do_update(
                    index_elements=["workspace_id", "fingerprint"],
                    set_={
                        "count": InstitutionAlert.count + 1,
                        "last_seen_at": func.now(),
                        "url": func.coalesce(InstitutionAlert.url, stmt.excluded.url),
                        "image_url": func.coalesce(
                            InstitutionAlert.image_url, stmt.excluded.image_url
                        ),
                    },
                )
                await db.execute(stmt)
            await db.commit()
        for ws in hit:
            await broadcast(ws.id, "institution.alert", {"status": status})
        return len(hit)
    except Exception:
        log.exception("institution alert failed")
        return 0


class OriginalRef(BaseModel):
    id: uuid.UUID
    number: str | None
    issued_on: str | None
    title: str


class AlertOut(BaseModel):
    id: uuid.UUID
    status: str
    channel: str
    text: str
    url: str | None
    image_url: str | None
    summary: str | None
    number: str | None
    original: OriginalRef | None
    count: int
    first_seen_at: datetime
    last_seen_at: datetime
    denial: OriginalRef | None
    dismissed_at: datetime | None
    is_demo: bool


def _ref(c: Communique | None) -> OriginalRef | None:
    if c is None:
        return None
    return OriginalRef(id=c.id, number=c.number, issued_on=c.issued_on, title=c.title)


async def _alert_out(db: AsyncSession, a: InstitutionAlert) -> AlertOut:
    original = await db.get(Communique, a.original_id) if a.original_id else None
    denial = await db.get(Communique, a.denial_id) if a.denial_id else None
    # Only an original the institution may read: its own, or one a publishing newsroom holds.
    if original is not None and original.workspace_id != a.workspace_id:
        owner = await db.get(Workspace, original.workspace_id)
        if not (owner and owner.publishes):
            original = None
    return AlertOut(
        id=a.id,
        status=a.status,
        channel=a.channel,
        text=a.text,
        url=a.url,
        image_url=a.image_url,
        summary=a.summary,
        number=a.number,
        original=_ref(original),
        count=a.count,
        first_seen_at=a.created_at,
        last_seen_at=a.last_seen_at,
        denial=_ref(denial),
        dismissed_at=a.dismissed_at,
        is_demo=a.is_demo,
    )


@router.get("/workspaces/{ws}/institution/alerts")
async def alerts(
    member: Institution, db: Db, state: Literal["open", "all"] = "open"
) -> list[AlertOut]:
    """The fakes that use the institution's name, newest first. Open = neither denied nor set
    aside."""
    stmt = select(InstitutionAlert).where(InstitutionAlert.workspace_id == member.workspace_id)
    if state == "open":
        stmt = stmt.where(
            InstitutionAlert.denial_id.is_(None), InstitutionAlert.dismissed_at.is_(None)
        )
    rows = await db.scalars(stmt.order_by(InstitutionAlert.last_seen_at.desc()).limit(200))
    return [await _alert_out(db, a) for a in rows]


async def _own_alert(db: AsyncSession, member: Member, alert_id: uuid.UUID) -> InstitutionAlert:
    a = await db.get(InstitutionAlert, alert_id)
    if a is None or a.workspace_id != member.workspace_id:
        raise ApiError(404, "not_found", "Alert not found")
    return a


@router.post("/workspaces/{ws}/institution/alerts/{alert_id}/dismiss")
async def dismiss_alert(alert_id: uuid.UUID, member: Institution, db: Db) -> AlertOut:
    """« Ce n'est pas un faux » or already handled: set aside, kept in « Toutes »."""
    a = await _own_alert(db, member, alert_id)
    a.dismissed_at = a.dismissed_at or datetime.now(UTC)
    await db.commit()
    await db.refresh(a)
    return await _alert_out(db, a)


# --- reading a communiqué PDF ------------------------------------------------------------------

MONTHS = {
    # French and Malagasy month names, folded (no accents).
    "janvier": 1, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6, "juillet": 7,
    "aout": 8, "septembre": 9, "octobre": 10, "novembre": 11, "decembre": 12,
    "janoary": 1, "febroary": 2, "martsa": 3, "aprily": 4, "mey": 5, "jona": 6, "jolay": 7,
    "aogositra": 8, "septambra": 9, "oktobra": 10, "novambra": 11, "desambra": 12,
}  # fmt: skip
_DAY_MONTH = re.compile(r"\b(\d{1,2})(?:er)?\s+([a-z]+)\s+((?:19|20)\d\d)\b")
_NUMERIC = re.compile(r"\b(\d{1,2})[/.-](\d{1,2})[/.-]((?:19|20)\d\d)\b")
_ISO = re.compile(r"\b((?:19|20)\d\d)-(\d{2})-(\d{2})\b")
# Lines of a letterhead or a heading that are not the communiqué's title.
_HEADING = re.compile(
    r"^(communiqu|n\s?[°o]|no\.?\s|laharana|repoblika|r[ée]publique|fitiavana|tanindrazana|"
    r"amour|minist[eè]re|ministera|secr[ée]tariat|direction|cabinet|fanambarana|"
    r"antananarivo|le\s+\d|page\s+\d)",
    re.IGNORECASE,
)


def read_date(text: str) -> date | None:
    """The first plausible date written in the text: « 1er novembre 2026 », « 01/11/2026 »,
    « 2026-11-01 », « 1 Novambra 2026 »."""
    folded = places.fold(text or "")
    found: list[tuple[int, date]] = []
    for m in _DAY_MONTH.finditer(folded):
        if (month := MONTHS.get(m[2])) is not None:
            try:
                found.append((m.start(), date(int(m[3]), month, int(m[1]))))
            except ValueError:
                pass
    for m in _NUMERIC.finditer(folded):
        try:
            found.append((m.start(), date(int(m[3]), int(m[2]), int(m[1]))))
        except ValueError:
            pass
    for m in _ISO.finditer(folded):
        try:
            found.append((m.start(), date(int(m[1]), int(m[2]), int(m[3]))))
        except ValueError:
            pass
    for _, day in sorted(found):
        if dates.parse(day):
            return day
    return None


def read_title(text: str, meta_title: str = "") -> str:
    """« Objet : … » when the letter has one, else the PDF's own title, else the first line that
    reads like a sentence and not like the letterhead."""
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in (text or "").splitlines()]
    lines = [ln for ln in lines if ln]
    for ln in lines:
        m = re.match(r"^(?:objet|object|lohahevitra)\s*[:.-]\s*(.+)$", ln, re.IGNORECASE)
        if m and len(m[1]) >= 4:
            return m[1][:200]
    if meta_title and len(meta_title) >= 4 and not meta_title.lower().endswith((".doc", ".docx")):
        return meta_title[:200]
    for ln in lines:
        if len(ln.split()) >= 3 and len(ln) <= 160 and not _HEADING.match(ln):
            return ln.rstrip(" .:")[:200]
    return ""


class ReadIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    file_id: uuid.UUID


class SequenceOut(BaseModel):
    # assigned: no number given, the next one of the series · ok: the number fits the series ·
    # inconsistent: it breaks the series (format, a future year, or out of date order) ·
    # duplicate: the institution already sealed this number.
    status: Literal["assigned", "ok", "inconsistent", "duplicate"]
    number: str
    expected: str
    reason: str | None = None


class DraftOut(BaseModel):
    file_id: uuid.UUID
    filename: str
    pages: int
    sha256: str
    issuer: str
    # The issuer named in the PDF's own text, when it is not the institution (a warning).
    issuer_read: str | None
    number: str | None
    issued_on: str | None
    title: str
    text: str
    sequence: SequenceOut


async def _own_pdf(db: AsyncSession, member: Member, file_id: uuid.UUID) -> File:
    f = await db.get(File, file_id)
    if f is None or f.workspace_id != member.workspace_id:
        raise ApiError(404, "not_found", "File not found")
    if f.mime != "application/pdf":
        raise ApiError(415, "unsupported_type", "A communiqué is sealed from its PDF")
    return f


@router.post("/workspaces/{ws}/institution/read")
async def read_pdf(body: ReadIn, member: Institution, db: Db) -> DraftOut:
    """The fields of an uploaded communiqué PDF, read without a model, for the press office to
    correct before sealing. A scanned PDF with no text layer gives an empty text to type in."""
    from app.modules.registry import quoted_issuers, quoted_numbers
    from app.workers.ingest import pdf_text

    f = await _own_pdf(db, member, body.file_id)
    if not storage.configured():
        raise ApiError(503, "storage_unavailable", "File storage is not configured")
    if f.status == "pending":
        obj = await storage.head(f.storage_key)
        if obj is None:
            raise ApiError(409, "not_uploaded", "The file has not reached storage yet")
        f.status, f.size_bytes = "ready", obj["size"]
    raw = await storage.read(f.storage_key)
    f.sha256 = hashlib.sha256(raw).hexdigest()
    try:
        meta, meta_title, text = pdf_text(raw)
    except Exception as exc:
        raise ApiError(422, "unreadable_pdf", "This PDF cannot be read") from exc
    f.meta = {**(f.meta or {}), **meta}
    ws = await db.get(Workspace, member.workspace_id)
    await db.commit()
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    numbers = quoted_numbers(text)
    issued = read_date(text) or dates.parse(meta.get("created_at"))
    named = quoted_issuers(text, aliases_of(ws))
    issuer_read = None
    if named and not any(_named(n, aliases_of(ws)) for n in named[:1]):
        issuer_read = named[0]
    issued_on = issued.isoformat() if issued else None
    return DraftOut(
        file_id=f.id,
        filename=f.filename,
        pages=int(meta.get("pages") or 0),
        sha256=f.sha256,
        issuer=ws.name,
        issuer_read=issuer_read,
        number=numbers[0] if numbers else None,
        issued_on=issued_on,
        title=read_title(text, meta_title),
        text=text,
        sequence=await _sequence(db, ws.id, numbers[0] if numbers else None, issued_on),
    )


# --- the chronological number ------------------------------------------------------------------


_YEAR = re.compile(r"(?<!\d)(?:19|20)\d\d(?!\d)")


def _runs(number: str) -> tuple[int, ...]:
    return tuple(int(n) for n in re.findall(r"\d+", number or ""))


def _year_of(number: str) -> int | None:
    m = _YEAR.search(number or "")
    return int(m[0]) if m else None


def _counter(number: str) -> re.Match | None:
    """The running counter of a number: its last run of digits that is not a year."""
    runs = list(re.finditer(r"\d+", number or ""))
    counters = [m for m in runs if not _YEAR.fullmatch(m[0])]
    return (counters or runs or [None])[-1]


def next_number(series: list[tuple[str, str | None]], issued_on: str | None) -> str:
    """The next number of the series for a communiqué of that date: « 2026-001 » to start, then
    the institution's own format with its counter plus one (back to 1 with a new year when the
    number carries the year)."""
    year = (dates.parse(issued_on) or dates.today()).year
    latest = series[-1][0] if series else ""
    m = _counter(latest)
    if m is None:
        return f"{year}-001"
    has_year = _year_of(latest) is not None
    pool = [n for n, _ in series if not has_year or _year_of(n) == year]
    value = 1 + max((int(c[0]) for n in pool if (c := _counter(n))), default=0)
    out = latest[: m.start()] + str(value).zfill(len(m[0])) + latest[m.end() :]
    return _YEAR.sub(str(year), out, count=1) if has_year else out


def check_number(
    number: str, issued_on: str | None, series: list[tuple[str, str | None]]
) -> tuple[str, str | None]:
    """(`ok` | `inconsistent` | `duplicate`, why). The rule of the communiqué check (3.1): a number
    that breaks the issuer's format, carries a year to come, or is out of date order (N° 045 dated
    after N° 050) is « Incohérent »."""
    from app.modules.registry import _num_key, _out_of_sequence, _shape

    key = _num_key(number)
    if any(_num_key(n) == key for n, _ in series):
        return "duplicate", f"Le N° {number} est déjà scellé."
    why = _out_of_sequence(number, [n for n, _ in series])
    if why == "future_year":
        return "inconsistent", f"Le N° {number} porte une année à venir."
    if why == "format":
        example = series[-1][0]
        return (
            "inconsistent",
            f"Le N° {number} ne suit pas le format de vos communiqués (N° {example}).",
        )
    mine = _runs(number)
    for other, day in series:
        if not (day and issued_on) or _shape(other) != _shape(number):
            continue
        theirs = _runs(other)
        if theirs < mine and day > issued_on:
            return "inconsistent", (
                f"Le N° {other} est daté du {dates.fr(dates.parse(day))} : le N° {number} ne "
                f"peut pas être plus ancien."
            )
        if theirs > mine and day < issued_on:
            return "inconsistent", (
                f"Le N° {other} est daté du {dates.fr(dates.parse(day))} : le N° {number}, plus "
                f"petit, ne peut pas venir après."
            )
    return "ok", None


async def _series(db: AsyncSession, ws: uuid.UUID) -> list[tuple[str, str | None]]:
    rows = await db.execute(
        select(Communique.number, Communique.issued_on).where(
            Communique.workspace_id == ws,
            Communique.status == "original",
            Communique.number.is_not(None),
        )
    )
    return sorted(((n, d) for n, d in rows.all() if n), key=lambda s: (s[1] or "", _runs(s[0])))


async def _sequence(
    db: AsyncSession, ws: uuid.UUID, number: str | None, issued_on: str | None
) -> SequenceOut:
    series = await _series(db, ws)
    expected = next_number(series, issued_on)
    if not (number or "").strip():
        return SequenceOut(status="assigned", number=expected, expected=expected)
    number = re.sub(r"\s+", " ", number).strip()
    status, why = check_number(number, issued_on, series)
    return SequenceOut(status=status, number=number, expected=expected, reason=why)


class SequenceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    number: str | None = Field(default=None, max_length=60)
    issued_on: str | None = Field(default=None, max_length=10)


@router.post("/workspaces/{ws}/institution/sequence")
async def sequence(body: SequenceIn, member: Institution, db: Db) -> SequenceOut:
    """The number checked against the series as the press office types it (or the next one)."""
    day = dates.parse(body.issued_on)
    return await _sequence(db, member.workspace_id, body.number, day.isoformat() if day else None)


# --- sealing -----------------------------------------------------------------------------------


class CommuniqueIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    file_id: uuid.UUID | None = None
    number: str | None = Field(default=None, max_length=60)
    issued_on: str = Field(min_length=8, max_length=10)
    title: str = Field(min_length=3, max_length=500)
    text: str = Field(min_length=20, max_length=30000)
    # The alert this communiqué denies (« Publier un démenti »).
    denies: uuid.UUID | None = None

    @field_validator("issued_on")
    @classmethod
    def day(cls, value: str) -> str:
        parsed = dates.parse(value)
        if not parsed:
            raise ValueError("Use a past or current YYYY-MM-DD date")
        return parsed.isoformat()

    @field_validator("title", "number")
    @classmethod
    def tidy(cls, value):
        return re.sub(r"\s+", " ", value).strip() if value else value


class SealedOut(BaseModel):
    communique: CommuniqueOut
    seal: SealResult
    pdf: bool


@router.post("/workspaces/{ws}/institution/communiques", status_code=201)
async def publish(body: CommuniqueIn, member: Institution, db: Db) -> SealedOut:
    """Register and seal a communiqué in the institution's name: the number is assigned or checked
    (an « Incohérent » or repeated number is refused), the entry is signed with the institution's
    own key and counts as verified in the registry."""
    from app.modules.registry import _seal_result, out

    if not seal.available():
        raise ApiError(503, "seal_unavailable", "Sealing is not configured on this server")
    ws = await db.get(Workspace, member.workspace_id)
    seq = await _sequence(db, ws.id, body.number, body.issued_on)
    if seq.status in ("inconsistent", "duplicate"):
        raise ApiError(409, f"{seq.status}_number", seq.reason or "This number breaks the series")
    f = await _own_pdf(db, member, body.file_id) if body.file_id else None
    alert = await _own_alert(db, member, body.denies) if body.denies else None
    c = Communique(
        workspace_id=ws.id,
        added_by=member.user.id,
        issuer=ws.name,
        number=seq.number,
        issued_on=body.issued_on,
        title=body.title,
        text=body.text,
        file_id=f.id if f else None,
        fingerprint=seal.fingerprint(body.text),
        status="original",
        confirmed_by=[],
        location={
            **({"file_sha256": f.sha256} if f and f.sha256 else {}),
            **({"denies": str(alert.id)} if alert else {}),
        },
        is_demo=bool((ws.settings or {}).get("demo")),
    )
    db.add(c)
    await db.flush()
    await seal.seal(db, c, member.user.id, "issuer")
    if alert is not None:
        alert.denial_id = c.id
    await record(
        db, ws.id, member.user.id, "communique", c.id, "seal", {"key_id": c.sealed["key_id"]}
    )
    await db.commit()
    await db.refresh(c)
    await broadcast(ws.id, "registry.changed", {"id": str(c.id)})
    return SealedOut(communique=out(c, ws, ws.id), seal=await _seal_result(db, c), pdf=True)


@router.get("/workspaces/{ws}/institution/communiques")
async def communiques(member: Institution, db: Db) -> list[SealedOut]:
    from app.modules.registry import _seal_result, out

    ws = await db.get(Workspace, member.workspace_id)
    rows = await db.scalars(
        select(Communique)
        .where(Communique.workspace_id == ws.id, Communique.status == "original")
        .order_by(Communique.issued_on.desc().nulls_last(), Communique.created_at.desc())
        .limit(200)
    )
    result = []
    for c in rows:
        if not (c.sealed and c.sealed.get("signature")):
            continue
        result.append(
            SealedOut(communique=out(c, ws, ws.id), seal=await _seal_result(db, c), pdf=True)
        )
    return result


def _plain(text: str) -> str:
    from app.core.pdf import plain

    return plain(text)


def _stamp_page(width: float, height: float, url: str, lines: list[str]) -> bytes:
    """One transparent page of the given size (points) with the QR and its caption in the bottom
    right corner, on a white card so it scans on any letterhead."""
    import segno
    from fpdf import FPDF

    png = io.BytesIO()
    segno.make(url, error="m").save(png, kind="png", scale=10, border=2)
    png.seek(0)
    pdf = FPDF(unit="pt", format=(width, height))
    pdf.set_auto_page_break(False)
    pdf.add_page()
    qr, pad, text_w = 92.0, 6.0, 150.0
    card_w, card_h = qr + text_w + 3 * pad, qr + 2 * pad
    x, y = width - card_w - 24, height - card_h - 24
    pdf.set_fill_color(255, 255, 255)
    pdf.set_draw_color(23, 26, 24)
    pdf.set_line_width(0.8)
    pdf.rect(x, y, card_w, card_h, style="DF")
    pdf.image(png, x=x + pad, y=y + pad, w=qr, h=qr)
    pdf.set_text_color(23, 26, 24)
    tx = x + qr + 2 * pad
    pdf.set_xy(tx, y + pad + 2)
    for i, line in enumerate(lines):
        pdf.set_font("Helvetica", "B" if i == 0 else "", 8.5 if i == 0 else 7.5)
        pdf.set_x(tx)
        pdf.multi_cell(text_w, 10, _plain(line), new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())


def _fresh_pdf(c: Communique) -> bytes:
    """A plain A4 copy of the communiqué when no PDF was uploaded (the demo's entries)."""
    from fpdf import FPDF

    pdf = FPDF(unit="mm", format="A4")
    pdf.set_margins(22, 22, 22)
    pdf.set_auto_page_break(True, margin=60)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 13)
    pdf.multi_cell(0, 7, _plain(c.issuer), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    day = dates.parse(c.issued_on)
    pdf.multi_cell(
        0,
        6,
        _plain(f"Communiqué N° {c.number or '—'} · {dates.fr(day) if day else '—'}"),
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(6)
    pdf.set_font("Helvetica", "B", 12)
    pdf.multi_cell(0, 7, _plain(c.title), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    pdf.set_font("Helvetica", "", 11)
    pdf.multi_cell(0, 6, _plain(c.text), new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())


def stamp(raw: bytes, url: str, lines: list[str]) -> bytes:
    """The PDF with the seal's QR on its first page (every other page untouched)."""
    from pypdf import PdfReader, PdfWriter

    reader = PdfReader(io.BytesIO(raw))
    writer = PdfWriter(clone_from=reader)
    first = writer.pages[0]
    box = first.mediabox
    width, height = float(box.width), float(box.height)
    overlay = PdfReader(io.BytesIO(_stamp_page(width, height, url, lines))).pages[0]
    first.merge_translated_page(overlay, float(box.left), float(box.bottom))
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


@router.get(
    "/workspaces/{ws}/institution/communiques/{cid}/pdf",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
)
async def sealed_pdf(cid: uuid.UUID, member: Institution, db: Db) -> Response:
    """The communiqué's PDF stamped with its seal QR, to publish and print. Made again on every
    download: Ed25519 is deterministic, so the QR is always the same."""
    c = await db.get(Communique, cid)
    if c is None or c.workspace_id != member.workspace_id or not (c.sealed or {}).get("signature"):
        raise ApiError(404, "not_found", "Sealed communiqué not found")
    raw = None
    if c.file_id and storage.configured():
        f = await db.get(File, c.file_id)
        if f is not None:
            try:
                raw = await storage.read(f.storage_key)
            except Exception:  # noqa: BLE001 - the original is gone: a plain copy is printed
                log.warning("institution pdf: original %s unreadable", f.id)
    day = dates.parse(c.issued_on)
    host = get_settings().public_web_url.split("://")[-1].rstrip("/")
    lines = [
        f"Scellé par {c.issuer}",
        f"N° {c.number or '—'} · {dates.fr(day) if day else '—'}",
        "Scannez pour vérifier la signature, même sans réseau",
        f"{host}/scanner",
    ]
    try:
        body = stamp(raw or _fresh_pdf(c), seal.seal_url(c.id, c.sealed), lines)
    except Exception as exc:
        if raw is None:
            raise
        log.warning("institution pdf: stamping the original failed (%s)", type(exc).__name__)
        body = stamp(_fresh_pdf(c), seal.seal_url(c.id, c.sealed), lines)
    name = re.sub(r"[^\w.-]+", "-", f"communique-{c.number or c.id}-scelle").strip("-")
    return Response(
        content=body,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{name}.pdf"'},
    )


# --- profile: official pages, numbers, press officer ------------------------------------------


class OfficerIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=2, max_length=200)
    role: str = Field(default="", max_length=200)
    phone: str | None = Field(default=None, max_length=60, pattern=r"^\+?[0-9 ()-]{3,60}$")
    whatsapp: str | None = Field(default=None, max_length=60, pattern=r"^\+?[0-9 ()-]{3,60}$")
    email: str | None = Field(default=None, max_length=200, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    hours: str | None = Field(default=None, max_length=200)


class ProfileIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    aliases: list[str] = Field(default_factory=list, max_length=8)
    website: HttpUrl | None = None
    pages: list[str] = Field(default_factory=list, max_length=10)
    phones: list[str] = Field(default_factory=list, max_length=6)
    topics: list[str] = Field(default_factory=list, max_length=12)
    officer: OfficerIn | None = None

    @field_validator("aliases", "topics")
    @classmethod
    def words(cls, value: list[str]) -> list[str]:
        out: list[str] = []
        for v in value:
            v = re.sub(r"\s+", " ", v).strip()[:120]
            if len(v) >= 2 and v not in out:
                out.append(v)
        return out


class PageOut(BaseModel):
    kind: str
    url: str
    display: str


class ProfileOut(BaseModel):
    id: uuid.UUID
    name: str
    verification: str
    publishes: bool
    is_demo: bool
    aliases: list[str]
    website: str | None
    pages: list[PageOut]
    phones: list[PageOut]
    topics: list[str]
    officer: OfficerIn | None
    declared_at: datetime | None
    communiques: int
    open_alerts: int


def _contact_ids(ws: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID]:
    return (
        uuid.uuid5(uuid.NAMESPACE_URL, f"checky:institution:{ws}:self"),
        uuid.uuid5(uuid.NAMESPACE_URL, f"checky:institution:{ws}:officer"),
    )


async def _profile_out(db: AsyncSession, ws: Workspace) -> ProfileOut:
    from app.modules.gestures import show_page

    self_id, officer_id = _contact_ids(ws.id)
    me = await db.get(Contact, self_id)
    officer = await db.get(Contact, officer_id)
    pages, phones = [], []
    for p in (me.official_pages if me else []) or []:
        url = str(p.get("url") or "")
        if p.get("kind") == "phone":
            number = url.removeprefix("tel:")
            phones.append(PageOut(kind="phone", url=number, display=countries.display(number)))
        else:
            pages.append(
                PageOut(kind=str(p.get("kind") or "site"), url=url, display=show_page(url))
            )
    count = await db.scalar(
        select(func.count())
        .select_from(Communique)
        .where(Communique.workspace_id == ws.id, Communique.sealed.is_not(None))
    )
    open_alerts = await db.scalar(
        select(func.count())
        .select_from(InstitutionAlert)
        .where(
            InstitutionAlert.workspace_id == ws.id,
            InstitutionAlert.denial_id.is_(None),
            InstitutionAlert.dismissed_at.is_(None),
        )
    )
    return ProfileOut(
        id=ws.id,
        name=ws.name,
        verification=ws.verification,
        publishes=ws.publishes,
        is_demo=bool((ws.settings or {}).get("demo")),
        aliases=aliases_of(ws)[1:],
        website=me.website if me else None,
        pages=pages,
        phones=phones,
        topics=list(me.topics or []) if me else [],
        officer=OfficerIn(
            name=officer.name,
            role=officer.role or "",
            phone=officer.phone,
            whatsapp=officer.whatsapp,
            email=officer.email,
            hours=officer.hours,
        )
        if officer
        else None,
        declared_at=me.verified_at if me else None,
        communiques=count or 0,
        open_alerts=open_alerts or 0,
    )


@router.get("/workspaces/{ws}/institution")
async def profile(member: Institution, db: Db) -> ProfileOut:
    return await _profile_out(db, await db.get(Workspace, member.workspace_id))


def _page_kind(url: str) -> str:
    from app.modules.gestures import page_key

    key = page_key(url)
    if key is None:
        raise ApiError(422, "not_a_page", f"Not a page or a site: {url}")
    return key[0]


async def declare(
    db: AsyncSession, ws: Workspace, user_id: str, body: ProfileIn, *, is_demo: bool = False
) -> None:
    """Write the institution's two Annuaire entries from its profile. The institution vouches for
    its own channels: they are « vérifiées le … par [institution] », and shared with every newsroom
    only once Checky has verified the institution."""
    from app.modules.directory import ContactIn, OfficialPage, _fields

    pages = [OfficialPage(kind=_page_kind(u), url=u) for u in body.pages]
    pages += [OfficialPage(kind="phone", url=p) for p in body.phones]
    now = datetime.now(UTC)
    shared = ws.verification == "approved"
    stats = {"declared_by": ws.name}
    self_id, officer_id = _contact_ids(ws.id)
    me = ContactIn(
        name=ws.name,
        kind="institution",
        institution=ws.name,
        topics=body.topics,
        languages=["mg", "fr"],
        website=body.website,
        official_pages=pages,
    )
    values = await _fields(db, ws.id, me)
    values["official_pages"] = [{**p, "verified": True} for p in values["official_pages"]]
    await _upsert(db, self_id, ws, user_id, values, shared, now, stats, is_demo)
    if body.officer is None:
        await db.execute(delete(Contact).where(Contact.id == officer_id))
    else:
        o = body.officer
        officer = ContactIn(
            name=o.name,
            kind="officer",
            role=o.role,
            institution=ws.name,
            topics=body.topics,
            languages=["mg", "fr"],
            phone=o.phone,
            whatsapp=o.whatsapp,
            email=o.email,
            hours=o.hours,
            website=body.website,
            official_pages=[p for p in pages if p.kind != "phone"],
        )
        values = await _fields(db, ws.id, officer)
        values["official_pages"] = [{**p, "verified": True} for p in values["official_pages"]]
        await _upsert(db, officer_id, ws, user_id, values, shared, now, stats, is_demo)
    ws.settings = {**(ws.settings or {}), "aliases": body.aliases}


async def _upsert(db, cid, ws, user_id, values, shared, now, stats, is_demo) -> None:
    c = await db.get(Contact, cid)
    if c is None:
        c = Contact(id=cid, workspace_id=ws.id, created_by=user_id)
        db.add(c)
    for key, value in values.items():
        setattr(c, key, value)
    c.shared, c.verified_at, c.verified_by = shared, now, user_id
    c.stats = {**(c.stats or {}), **stats}
    c.is_demo = is_demo
    await db.flush()


@router.put("/workspaces/{ws}/institution")
async def update_profile(body: ProfileIn, member: Institution, db: Db) -> ProfileOut:
    ws = await db.get(Workspace, member.workspace_id)
    await declare(db, ws, member.user.id, body, is_demo=bool((ws.settings or {}).get("demo")))
    await record(db, ws.id, member.user.id, "institution", ws.id, "declare")
    await db.commit()
    await db.refresh(ws)
    return await _profile_out(db, ws)


async def sync_shared(db: AsyncSession, ws: Workspace) -> None:
    """After a review: a verified institution's channels reach every newsroom, a refused one's
    reach nobody. The caller commits."""
    if ws.kind != "institution":
        return
    for c in await db.scalars(select(Contact).where(Contact.id.in_(_contact_ids(ws.id)))):
        c.shared = ws.verification == "approved"
        c.stats = {**(c.stats or {}), "declared_by": ws.name}


# --- demo --------------------------------------------------------------------------------------

DEMO_COMMUNIQUE = {
    "number": "2026-041",
    "issued_on": "2026-10-28",
    "title": "Campagne de vaccination dans les écoles d'Antananarivo du 4 au 8 novembre 2026 (démo)",
    "text": (
        "COMMUNIQUÉ N° 2026-041. Le Ministère de démo informe les parents d'élèves qu'une campagne "
        "de vaccination gratuite et volontaire contre la rougeole aura lieu dans les écoles "
        "primaires publiques d'Antananarivo du 4 au 8 novembre 2026. Aucun paiement n'est demandé "
        "aux familles. Les équipes de santé se présenteront avec un ordre de mission signé. Pour "
        "toute question, appelez le numéro officiel du ministère. Exemple fictif (démo)."
    ),
}
DEMO_FAKE = (
    "URGENT. Le Ministère de démo annonce que la vaccination dans les écoles d'Antananarivo est "
    "obligatoire et payante : 10 000 Ar par enfant, à verser par mobile money au 034 99 000 00 "
    "avant le 4 novembre. Partagez ! (exemple fictif, démo)"
)
DEMO_PROFILE = ProfileIn(
    aliases=["Ministeran'ny demo"],
    website="https://ministere-demo.example.org",
    pages=["https://www.facebook.com/ministere.demo.officiel"],
    phones=["+261 20 22 000 00"],
    topics=["santé", "éducation"],
    officer=OfficerIn(
        name="Hanta Rakoto (démo)",
        role="Chargée de communication",
        phone="+261 34 00 000 01",
        email="presse@ministere-demo.example.org",
        hours="Lun.–ven., 8 h–17 h",
    ),
)


def _admin_id(user_id: str) -> bool:
    entries = {e.strip() for e in get_settings().platform_admins.split(",") if e.strip()}
    return user_id in entries


async def seed_demo(db: AsyncSession, workspace_id, user_id, items) -> None:
    """ONE fictional institution beside the demo newsroom, « Ministère de démo (démo) », with a
    sealed communiqué, its declared channels and one fake alert. It is verified at once only when
    a member of the Checky team runs the reset; otherwise it waits in the review queue like any
    other institution. Idempotent: its demo entries are replaced."""
    iid = uuid.uuid5(uuid.NAMESPACE_URL, f"checky:demo-institution:{workspace_id}")
    ws = await db.get(Workspace, iid)
    if ws is None:
        ws = Workspace(
            id=iid,
            name=DEMO_NAME,
            slug=f"ministere-de-demo-{iid.hex[:6]}",
            kind="institution",
            is_public=True,
            settings={"demo": True, "country": "Madagascar"},
        )
        db.add(ws)
        await db.flush()
    if ws.verification != "approved":
        ws.verification = "approved" if _admin_id(user_id) else "pending"
    if ws.verification == "pending" and not await db.scalar(
        select(NewsroomRequest.id).where(NewsroomRequest.workspace_id == ws.id)
    ):
        db.add(
            NewsroomRequest(
                workspace_id=ws.id,
                outlet=DEMO_NAME,
                kind="institution",
                city="Antananarivo",
                region="Analamanga",
                country="MG",
                website="https://www.facebook.com/ministere.demo.officiel",
                full_name="Hanta Rakoto (démo)",
                job_title="Chargée de communication",
                phone="+261340000001",
                email="presse@ministere-demo.example.org",
                submitted_by=user_id,
            )
        )
    if not await db.scalar(
        select(Membership.id).where(Membership.workspace_id == ws.id, Membership.user_id == user_id)
    ):
        db.add(Membership(workspace_id=ws.id, user_id=user_id))
    await db.execute(
        delete(InstitutionAlert).where(
            InstitutionAlert.workspace_id == ws.id, InstitutionAlert.is_demo.is_(True)
        )
    )
    await db.execute(
        delete(Communique).where(Communique.workspace_id == ws.id, Communique.is_demo.is_(True))
    )
    await db.flush()
    await declare(db, ws, user_id, DEMO_PROFILE, is_demo=True)
    c = Communique(
        id=uuid.uuid5(uuid.NAMESPACE_URL, f"checky:demo-institution:{workspace_id}:041"),
        workspace_id=ws.id,
        added_by=user_id,
        issuer=ws.name,
        fingerprint=seal.fingerprint(DEMO_COMMUNIQUE["text"]),
        status="original",
        confirmed_by=[],
        location=places.gazetteer("Antananarivo") or {},
        is_demo=True,
        **DEMO_COMMUNIQUE,
    )
    db.add(c)
    await db.flush()
    if seal.available():
        await seal.seal(db, c, user_id, "issuer")
    from app.modules.registry import compare

    found = compare(c, DEMO_FAKE)
    db.add(
        InstitutionAlert(
            workspace_id=ws.id,
            status="modified",
            channel="public",
            text=DEMO_FAKE,
            fingerprint=seal.fingerprint(DEMO_FAKE),
            url="https://www.facebook.com/groups/exemple-fictif-demo",
            summary=found["summary"],
            number=c.number,
            original_id=c.id,
            count=3,
            is_demo=True,
        )
    )
    await db.flush()
