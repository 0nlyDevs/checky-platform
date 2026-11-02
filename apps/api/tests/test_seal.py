"""Sceau: an issuer's Ed25519 signature on its communiqué, checkable by anyone with the public key."""

import asyncio
import base64
import uuid

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.core import seal
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.errors import ApiError
from app.core.models import Communique, SealKey
from tests.test_workspaces import _workspace

SECRET = "test-seal-secret-that-is-long-enough"


@pytest.fixture
def secret(monkeypatch):
    monkeypatch.setattr(get_settings(), "seal_secret", SECRET)


def test_canonical_payload_and_signature_round_trip():
    payload = {"title": "Délestage", "issuer": "JIRAMA", "number": "2026-118"}
    assert seal.canonical(payload) == '{"issuer":"JIRAMA","number":"2026-118","title":"Délestage"}'
    private = Ed25519PrivateKey.generate()
    public = base64.b64encode(private.public_key().public_bytes_raw()).decode()
    signature = seal.b64u(private.sign(seal.canonical(payload).encode()))
    assert "=" not in signature and seal.verify(public, payload, signature)
    assert not seal.verify(public, {**payload, "number": "2026-119"}, signature)
    assert not seal.verify(public, payload, "not-a-signature")
    # Whitespace and Unicode composition do not change the fingerprint; a word does.
    assert seal.fingerprint("Un  texte\n signé") == seal.fingerprint("Un texte signé")
    assert seal.fingerprint("Un texte signé") != seal.fingerprint("Un texte signe")


def test_sealing_needs_the_secret(monkeypatch):
    monkeypatch.setattr(get_settings(), "seal_secret", "")
    assert not seal.available()
    with pytest.raises(ApiError) as caught:
        seal._fernet()
    assert caught.value.status_code == 503 and caught.value.code == "seal_unavailable"


def test_issuer_key_is_created_once_and_kept_encrypted(as_user, secret):
    ws = uuid.UUID(_workspace(as_user("alice")))

    async def go():
        async with SessionLocal() as db:
            c = Communique(
                workspace_id=ws,
                added_by="alice",
                issuer="JIRAMA",
                number="2026-118",
                issued_on="2026-11-01",
                title="Programme de délestage",
                text="Un délestage de 4 heures par jour et par quartier.",
                confirmed_by=[],
            )
            db.add(c)
            await db.flush()
            first = await seal.seal(db, c, "alice", "admin")
            again = await seal.seal(db, c, "alice", "admin")
            key = await db.get(SealKey, (await seal.issuer_key(db, ws, "JIRAMA")).id)
            await db.commit()
            return first, again, key, c

    first, again, key, c = asyncio.run(go())
    assert first["signature"] == again["signature"] and first["key_id"] == key.key_id
    assert first["payload"]["fingerprint"] == seal.fingerprint(c.text)
    # The private key is never stored in clear: 32 raw bytes would be 44 base64 characters.
    assert len(key.private_key_enc) > 44 and key.public_key not in key.private_key_enc
    assert seal.verify(key.public_key, first["payload"], first["signature"])
    assert seal.seal_url(c.id, first["signature"]).endswith(f"/sceau/{c.id}#{first['signature']}")
    svg = seal.qr_svg(seal.seal_url(c.id, first["signature"]))
    assert svg.startswith("<svg") and "#171a18" in svg
