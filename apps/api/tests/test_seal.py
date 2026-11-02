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


def test_seal_routes_qr_public_check_and_revocation(as_user, monkeypatch):
    from tests.test_newsroom_resources import invite
    from tests.test_registry import ORIGINAL

    alice, bob, carol, outsider = as_user("alice"), as_user("bob"), as_user("carol"), as_user("x")
    ws = _workspace(alice)
    invite(alice, ws, bob)
    invite(alice, ws, carol)
    base = f"/api/v1/workspaces/{ws}/registry"
    cid = carol.post(base, json=ORIGINAL).json()["id"]

    monkeypatch.setattr(get_settings(), "seal_secret", "")
    refused = alice.post(f"{base}/{cid}/seal")
    assert refused.status_code == 503 and refused.json()["error"]["code"] == "seal_unavailable"
    monkeypatch.setattr(get_settings(), "seal_secret", SECRET)
    assert outsider.post(f"{base}/{cid}/seal").status_code == 404

    sealed = carol.post(f"{base}/{cid}/seal").json()
    signature = sealed["sealed"]["signature"]
    assert sealed["sealed"]["url"].endswith(f"/sceau/{cid}#{signature}")
    assert sealed["qr_svg"].startswith("<svg") and sealed["public"] is False
    assert sealed["payload"]["number"] == "2026-118"
    assert carol.post(f"{base}/{cid}/seal").json()["sealed"]["signature"] == signature
    assert alice.get(f"{base}/{cid}/seal").json()["sealed"]["signature"] == signature
    assert alice.get(base).json()[0]["sealed"]["key_id"] == sealed["sealed"]["key_id"]

    # A private newsroom's seal is not served to the public.
    anyone = as_user("nobody")
    anyone.headers.pop("Authorization")
    assert anyone.get(f"/api/v1/public/sceau/{cid}").status_code == 404
    assert anyone.get("/api/v1/public/seal-keys").json() == {"keys": [], "revoked": []}
    alice.patch(f"/api/v1/workspaces/{ws}", json={"is_public": True})
    public = anyone.get(f"/api/v1/public/sceau/{cid}").json()
    assert public["alg"] == "Ed25519" and public["sealed_by"] == "newsroom"
    assert public["message"] == seal.canonical(public["payload"]) and public["revoked_at"] is None
    assert seal.verify(public["public_key"], public["payload"], public["signature"])
    check = f"/api/v1/public/sceau/{cid}/verify"
    assert anyone.post(check, json={"signature": signature}).json()["valid"] is True
    forged = anyone.post(check, json={"signature": signature[:-4] + "AAAA"}).json()
    assert forged["valid"] is False and forged["matches_record"] is True
    assert [k["issuer"] for k in anyone.get("/api/v1/public/seal-keys").json()["keys"]] == [
        "JIRAMA"
    ]

    keys = carol.get(f"{base}/keys").json()
    assert len(keys) == 1 and keys[0]["seals"] == 1
    key_id = keys[0]["key_id"]
    revoked = bob.post(f"{base}/keys/{key_id}/revoke").json()
    assert revoked["revoked_at"]
    assert anyone.get(f"/api/v1/public/sceau/{cid}").json()["revoked_at"]
    assert anyone.post(check, json={}).json()["revoked"] is True
    assert anyone.get("/api/v1/public/seal-keys").json()["revoked"][0]["key_id"] == key_id
    # Sealing again after a revocation makes a new key.
    fresh = carol.post(f"{base}/{cid}/seal").json()
    assert fresh["sealed"]["key_id"] != key_id
    assert anyone.post(check, json={}).json() == {
        "valid": True,
        "revoked": False,
        "matches_record": True,
        "key_id": fresh["sealed"]["key_id"],
    }
