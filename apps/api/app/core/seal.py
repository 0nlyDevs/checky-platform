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
    """The issuer's active key in this newsroom, created on first use."""
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


def seal_url(communique_id: uuid.UUID, signature: str) -> str:
    """What the QR encodes: the public page, with the signature after `#` so a phone can check it
    without the signature ever being sent to a server."""
    base = get_settings().public_web_url.rstrip("/")
    return f"{base}/sceau/{communique_id}#{signature}"


def qr_svg(url: str) -> str:
    """A printable SVG QR code (ink on white, medium error correction for a creased paper)."""
    out = io.BytesIO()
    segno.make(url, error="m").save(
        out, kind="svg", scale=6, border=3, dark="#171a18", light="#ffffff", xmldecl=False
    )
    return out.getvalue().decode()
