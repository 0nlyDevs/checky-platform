"""Verification attestations: the summary of a dossier's diligence, signed by the server.

The Ed25519 key is derived from `SEAL_SECRET` with HKDF-SHA256, so it needs no table, survives
restarts and changes when the secret changes (old attestations then stop verifying, which is the
honest outcome of a rotated secret). It is a different key from the issuers' seals (app/core/seal.py):
an attestation says what a newsroom did on a dossier, never that an institution wrote a text.

    signed = sign({"ref": "FAN-0145", ...})
    verify(signed["payload"], signed["signature"])  # True
"""

import base64
import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.core.config import get_settings

SALT = b"checky-attestation"
INFO = b"ed25519 attestation key v1"


class AttestationUnavailable(Exception):
    """No SEAL_SECRET: the server has no key to sign with."""


def _private() -> Ed25519PrivateKey:
    secret = get_settings().seal_secret
    if not secret:
        raise AttestationUnavailable("SEAL_SECRET is not set")
    seed = HKDF(algorithm=hashes.SHA256(), length=32, salt=SALT, info=INFO).derive(secret.encode())
    return Ed25519PrivateKey.from_private_bytes(seed)


def _raw(public: Ed25519PublicKey) -> bytes:
    return public.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)


def public_key() -> dict[str, str]:
    """The server's public key (base64 raw 32 bytes) and its id (first 16 hex of its SHA-256)."""
    raw = _raw(_private().public_key())
    return {
        "key_id": hashlib.sha256(raw).hexdigest()[:16],
        "public_key": base64.b64encode(raw).decode(),
    }


def canonical(payload: dict[str, Any]) -> bytes:
    """The exact bytes that are signed: sorted keys, no spaces, UTF-8."""
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()


def sign(payload: dict[str, Any]) -> dict[str, Any]:
    body = canonical(payload)
    signature = _private().sign(body)
    return {
        "payload": payload,
        "sha256": hashlib.sha256(body).hexdigest(),
        "signature": base64.b64encode(signature).decode(),
        **public_key(),
        "issued_at": datetime.now(UTC).isoformat(),
    }


def verify(payload: dict[str, Any], signature: str) -> bool:
    """True when `signature` (base64) is this server's signature of `payload`."""
    try:
        raw = base64.b64decode(signature, validate=True)
        _private().public_key().verify(raw, canonical(payload))
    except (InvalidSignature, ValueError):
        return False
    return True
