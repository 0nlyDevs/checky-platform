"""Issuers' seals: an institution signs its own communiqué with an Ed25519 key, and anyone checks
the signature with the published public key, offline if need be (a phone scanning the QR on paper).

A seal proves *who signed* and *that these words were signed*, never that the content is true.
Each issuer of a newsroom gets one key pair on its first seal; the private key is stored encrypted
with a Fernet key derived from `SEAL_SECRET` (nothing can be sealed while it is empty), the public
key is published. A revoked key's seals still verify mathematically but are shown as revoked.
"""

import base64
import hashlib
import io
import json
import re
import unicodedata
import uuid
from datetime import UTC, datetime
from typing import Any

import segno
from cryptography.exceptions import InvalidSignature
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import ApiError
from app.core.models import Communique, SealKey

ALG = "Ed25519"
# The fields an issuer signs: enough to compare with the paper in hand, and the text's fingerprint.
FIELDS = ("issuer", "number", "issued_on", "title", "fingerprint")


def normalise(text: str) -> str:
    """The text as it is fingerprinted: Unicode NFC, runs of whitespace collapsed, trimmed."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text or "")).strip()


def fingerprint(text: str) -> str:
    return hashlib.sha256(normalise(text).encode()).hexdigest()


def b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def unb64u(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def canonical(payload: dict[str, Any]) -> str:
    """The exact string that is signed: sorted keys, no spaces, UTF-8 kept as is. The public page
    shows the fields parsed back from this string, so what is displayed is what was signed."""
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def payload_of(c: Communique) -> dict[str, Any]:
    return {
        "issuer": c.issuer,
        "number": c.number,
        "issued_on": c.issued_on,
        "title": c.title,
        "fingerprint": c.fingerprint or fingerprint(c.text),
    }


def available() -> bool:
    return bool(get_settings().seal_secret)


def _fernet() -> Fernet:
    secret = get_settings().seal_secret
    if not secret:
        raise ApiError(
            503,
            "seal_unavailable",
            "Sealing is not configured on this server (SEAL_SECRET is empty)",
        )
    key = HKDF(
        algorithm=hashes.SHA256(), length=32, salt=b"checky-seal-v1", info=b"issuer-keys"
    ).derive(secret.encode())
    return Fernet(base64.urlsafe_b64encode(key))


def key_id_of(public_raw: bytes) -> str:
    return "k_" + hashlib.sha256(public_raw).hexdigest()[:16]


async def issuer_key(db: AsyncSession, workspace_id: uuid.UUID, issuer: str) -> SealKey:
    """The issuer's active key in this newsroom, created on first use. Reserved names (the
    newsroom's verdict key) are refused here: only `sign_verdict` reaches that key."""
    if reserved_issuer(issuer):
        raise ApiError(422, "reserved_issuer", "This issuer name is reserved")
    return await _key_for(db, workspace_id, issuer)


async def _key_for(db: AsyncSession, workspace_id: uuid.UUID, issuer: str) -> SealKey:
    fernet = _fernet()
    key = await db.scalar(
        select(SealKey)
        .where(
            SealKey.workspace_id == workspace_id,
            SealKey.issuer == issuer,
            SealKey.revoked_at.is_(None),
        )
        .order_by(SealKey.created_at.desc())
        .limit(1)
    )
    if key:
        return key
    private = Ed25519PrivateKey.generate()
    public_raw = private.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    private_raw = private.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    key = SealKey(
        workspace_id=workspace_id,
        issuer=issuer,
        key_id=key_id_of(public_raw),
        public_key=base64.b64encode(public_raw).decode(),
        private_key_enc=fernet.encrypt(private_raw).decode(),
    )
    db.add(key)
    await db.flush()
    return key


async def seal(db: AsyncSession, c: Communique, by: str, role: str) -> dict[str, Any]:
    """Sign the communiqué with its issuer's key; stores and returns `sealed`. Sealing again with
    the same key and fields gives the same signature (Ed25519 is deterministic)."""
    key = await issuer_key(db, c.workspace_id, c.issuer)
    private = Ed25519PrivateKey.from_private_bytes(_fernet().decrypt(key.private_key_enc.encode()))
    if not c.fingerprint:
        c.fingerprint = fingerprint(c.text)
    payload = payload_of(c)
    signature = b64u(private.sign(canonical(payload).encode()))
    c.sealed = {
        "key_id": key.key_id,
        "payload": payload,
        "signature": signature,
        "sealed_at": datetime.now(UTC).isoformat(),
        "by": by,
        "role": role,
    }
    return c.sealed


def verify(public_key_b64: str, payload: dict[str, Any], signature: str) -> bool:
    try:
        public = Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key_b64))
        public.verify(unb64u(signature), canonical(payload).encode())
    except (InvalidSignature, ValueError, TypeError):
        return False
    return True


def seal_url(communique_id: uuid.UUID, sealed: dict[str, Any]) -> str:
    """What the QR encodes: the public page, with everything needed to check it offline after `#`
    (`<b64u(canonical payload)>.<signature>.<key_id>`, like a verdict card), so a phone with the
    issuers' keys checks the paper with no network and the fragment never reaches a server.
    QRs printed before 3 Nov 2026 carry only `#<signature>`; the page still reads them."""
    base = get_settings().public_web_url.rstrip("/")
    packed = b64u(canonical(sealed["payload"]).encode())
    return f"{base}/sceau/{communique_id}#{packed}.{sealed['signature']}.{sealed['key_id']}"


def read_communique_fragment(fragment: str) -> tuple[dict[str, Any], str, str, str] | None:
    """A communiqué QR's `#message.signature.key_id` back into (payload, message, signature,
    key_id); None for an old `#signature` fragment or anything carrying a `type` (a verdict)."""
    try:
        packed, signature, key_id = fragment.lstrip("#").split(".")
        message = unb64u(packed).decode()
        payload = json.loads(message)
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(payload, dict) or "type" in payload or set(payload) != set(FIELDS):
        return None
    return payload, message, signature, key_id


def qr_svg(url: str) -> str:
    """A printable SVG QR code (ink on white, medium error correction for a creased paper)."""
    out = io.BytesIO()
    segno.make(url, error="m").save(
        out, kind="svg", scale=6, border=3, dark="#171a18", light="#ffffff", xmldecl=False
    )
    return out.getvalue().decode()


# --- the newsroom's own seal on a signed verdict (cards, story, poster) -----------------------

# The newsroom's own verdict key lives in a namespace of its own: issuer names starting with
# `checky:` (after NFKC, casefold, whitespace removed) are refused by the registry, never listed
# among the issuers' keys and never revoked from there, so no communiqué issuer can share it.
RESERVED_PREFIX = "checky:"
NEWSROOM_ISSUER = "checky:verdicts"
# Domain separation: a verdict seal says what it is, and verification requires it.
VERDICT_TYPE = "verdict"


def reserved_issuer(name: str | None) -> bool:
    """`checky:` in any guise: compatibility forms folded (NFKC: full-width letters), case folded,
    whitespace ignored."""
    folded = re.sub(r"\s+", "", unicodedata.normalize("NFKC", name or "")).casefold()
    return folded.startswith(RESERVED_PREFIX)


VERDICTS = ("true", "misleading", "false", "unverifiable")
TITLE_MAX = 100  # the signed title travels inside a QR code: a card's title, clipped by code


def check_number(ref: str | None) -> int | None:
    """« vérification 145 » for FAN-0145: the number said on air, typed on a phone, in /v/145."""
    m = re.search(r"(\d{1,8})$", str(ref or "").strip())
    return int(m[1]) if m else None


def check_label(ref: str | None, lang: str = "fr") -> str | None:
    """The verification number written the same way everywhere (card, story, poster, radio line,
    SMS, voice line). The Malagasy word is machine-chosen: à relire par un locuteur."""
    n = check_number(ref)
    if n is None:
        return None
    return f"fanamarinana {n}" if lang == "mg" else f"vérification {n}"


def clip_title(title: str, limit: int = TITLE_MAX) -> str:
    flat = normalise(title)
    if len(flat) <= limit:
        return flat
    return flat[: limit - 1].rsplit(" ", 1)[0].rstrip(" ,;:.") + "…"


def minute(moment: datetime) -> str:
    """UTC to the minute (`2026-11-02T05:15Z`): short enough for a QR, exact enough to compare."""
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%MZ")


def verdict_payload(
    *,
    item_id: uuid.UUID,
    ref: str | None,
    verdict: str,
    title: str,
    signed_at: datetime,
    digest: str,
) -> dict[str, Any]:
    """What the newsroom signs for a published verdict: which dossier, its number, the verdict, the
    title as the card prints it, when it was signed, and the fingerprint of the signed version (the
    first 128 bits of `signing.digest`, which covers title, body, verdict and explanation)."""
    if verdict not in VERDICTS:
        raise ValueError(f"Unknown verdict: {verdict}")
    return {
        "type": VERDICT_TYPE,
        "id": str(item_id),
        "ref": ref,
        "verdict": verdict,
        "title": clip_title(title),
        "signed_at": minute(signed_at),
        "digest": digest[:32],
    }


def verdict_seal_url(item_id: uuid.UUID, message: str, signature: str, key_id: str) -> str:
    """What the card's QR encodes: the verdict's public page, with everything needed to check it
    offline after `#` (the signed message, the signature, the key id), so the fragment never
    reaches a server; the page checks it against `/public/sceau/v/{id}`."""
    base = get_settings().public_web_url.rstrip("/")
    return f"{base}/verifies/{item_id}#{b64u(message.encode())}.{signature}.{key_id}"


async def sign_verdict(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    *,
    item_id: uuid.UUID,
    ref: str | None,
    verdict: str,
    title: str,
    signed_at: datetime,
    digest: str,
) -> dict[str, Any]:
    """Seal a published verdict with the newsroom's key (created on first use, flushed: the caller
    commits). Ed25519 is deterministic, so the same version always gives the same seal and nothing
    needs storing on the dossier. Raises 503 `seal_unavailable` without SEAL_SECRET."""
    key = await _key_for(db, workspace_id, NEWSROOM_ISSUER)
    private = Ed25519PrivateKey.from_private_bytes(_fernet().decrypt(key.private_key_enc.encode()))
    payload = verdict_payload(
        item_id=item_id,
        ref=ref,
        verdict=verdict,
        title=title,
        signed_at=signed_at,
        digest=digest,
    )
    message = canonical(payload)
    signature = b64u(private.sign(message.encode()))
    return {
        "alg": ALG,
        "key_id": key.key_id,
        "public_key": key.public_key,
        "payload": payload,
        "message": message,
        "signature": signature,
        "url": verdict_seal_url(item_id, message, signature, key.key_id),
        "number": check_number(ref),
    }


def read_fragment(fragment: str) -> tuple[dict[str, Any], str, str, str] | None:
    """The QR's `#message.signature.key_id` back into (payload, message, signature, key_id); None
    for anything that is not a verdict seal (`"type": "verdict"`)."""
    try:
        packed, signature, key_id = fragment.lstrip("#").split(".")
        message = unb64u(packed).decode()
        payload = json.loads(message)
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get("type") != VERDICT_TYPE:
        return None
    return payload, message, signature, key_id


def verify_message(public_key_b64: str, message: str, signature: str) -> bool:
    """Like `verify`, on the exact signed string (what a QR carries)."""
    try:
        public = Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key_b64))
        public.verify(unb64u(signature), message.encode())
    except (InvalidSignature, ValueError, TypeError):
        return False
    return True
