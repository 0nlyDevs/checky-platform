"""The newsroom's seal on a published verdict: a signature a phone checks offline from the QR."""

import asyncio
import uuid
from datetime import UTC, datetime

import pytest

from app.core import seal
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.errors import ApiError
from tests.ref_fixture import set_ref
from tests.test_workspaces import _verify, _workspace

SECRET = "test-seal-secret-that-is-long-enough"


@pytest.fixture
def secret(monkeypatch):
    monkeypatch.setattr(get_settings(), "seal_secret", SECRET)
    monkeypatch.setattr(get_settings(), "public_web_url", "https://checky.example")


def test_verification_number_is_written_the_same_way():
    assert seal.check_number("FAN-0145") == 145
    assert seal.check_label("FAN-0145") == "vérification 145"
    assert seal.check_label("FAN-0145", "mg") == "fanamarinana 145"
    assert seal.check_number(None) is None and seal.check_label("sans numéro") is None


def test_sealed_verdict_round_trips_through_the_qr_fragment(as_user, secret):
    ws = uuid.UUID(_workspace(as_user("alice")))
    item_id = uuid.uuid4()
    title = "72 heures de délestage dès demain sur tout Antananarivo, selon la JIRAMA " * 3

    async def go():
        async with SessionLocal() as db:
            out = await seal.sign_verdict(
                db,
                ws,
                item_id=item_id,
                ref="FAN-0145",
                verdict="false",
                title=title,
                signed_at=datetime(2026, 11, 2, 5, 15, 42, tzinfo=UTC),
                digest="ab" * 32,
            )
            again = await seal.sign_verdict(
                db,
                ws,
                item_id=item_id,
                ref="FAN-0145",
                verdict="false",
                title=title,
                signed_at=datetime(2026, 11, 2, 5, 15, 42, tzinfo=UTC),
                digest="ab" * 32,
            )
            await db.commit()
            return out, again

    out, again = asyncio.run(go())
    assert out["signature"] == again["signature"]  # deterministic: nothing to store
    p = out["payload"]
    assert p["signed_at"] == "2026-11-02T05:15Z" and p["digest"] == "ab" * 16
    assert len(p["title"]) <= seal.TITLE_MAX and p["title"].endswith("…")
    assert out["url"].startswith(f"https://checky.example/sceau/v/{item_id}#")
    payload, message, signature, key_id = seal.read_fragment(out["url"].split("#", 1)[1])
    assert payload == p and key_id == out["key_id"]
    assert seal.verify_message(out["public_key"], message, signature)
    # A card whose verdict was changed in the QR fails.
    forged = message.replace('"false"', '"true"')
    assert not seal.verify_message(out["public_key"], forged, signature)
    assert seal.read_fragment("not-a-fragment") is None


REASON = "Le communiqué N° 2026-118 de la JIRAMA prévoit 4 heures par jour, pas 72 heures."


def _published(alice, ws, title="72 heures de délestage dès demain sur tout Antananarivo"):
    alice.patch(f"/api/v1/workspaces/{ws}", json={"is_public": True})
    _verify(ws)
    item = alice.post(f"/api/v1/workspaces/{ws}/items", json={"title": title}).json()["id"]
    set_ref(item, "FAN-0145")
    r = alice.post(
        f"/api/v1/workspaces/{ws}/items/{item}/sign",
        json={"verdict": "false", "reason": REASON, "publish": True},
    )
    assert r.status_code == 200, r.text
    return item


def test_card_seal_is_checked_offline_and_fails_once_the_verdict_changes(as_user, client, secret):
    alice = as_user("alice")
    ws = _workspace(alice)
    item = _published(alice, ws)
    sealed = alice.get(f"/api/v1/workspaces/{ws}/items/{item}/seal").json()
    assert sealed["number"] == 145 and sealed["payload"]["verdict"] == "false"
    # The public keys list carries the newsroom's key, so a phone checks with no network.
    keys = client.get("/api/v1/public/seal-keys").json()["keys"]
    assert any(k["key_id"] == sealed["key_id"] and k["kind"] == "verdict" for k in keys)
    assert sealed["payload"]["type"] == "verdict"
    _payload, message, signature, key_id = seal.read_fragment(sealed["url"].split("#")[1])
    assert seal.verify_message(sealed["public_key"], message, signature)

    pub = client.get(f"/api/v1/public/sceau/v/{item}").json()
    assert pub["message"] == message and pub["check_label"] == "vérification 145"
    assert pub["newsroom"]["name"] and pub["published_url"].endswith(f"/verifies/{item}")
    body = {"message": message, "signature": signature, "key_id": key_id}
    check = client.post(f"/api/v1/public/sceau/v/{item}/verify", json=body).json()
    assert check == {**check, "valid": True, "current": True, "revoked": False}
    forged = {**body, "message": message.replace('"false"', '"true"')}
    assert (
        client.post(f"/api/v1/public/sceau/v/{item}/verify", json=forged).json()["valid"] is False
    )
    # Another verdict's genuine seal does not vouch for this page.
    other = _published(alice, ws, "Une vidéo montre l'inondation d'Analakely ce matin")
    assert client.post(f"/api/v1/public/sceau/v/{other}/verify", json=body).json()["valid"] is False

    # The explanation is re-signed: the old card still verifies, but is no longer current.
    alice.post(
        f"/api/v1/workspaces/{ws}/items/{item}/sign",
        json={"verdict": "misleading", "reason": REASON + " Nuance.", "publish": True},
    )
    check = client.post(f"/api/v1/public/sceau/v/{item}/verify", json=body).json()
    assert check["valid"] is True and check["current"] is False
    # The diffusion's poster carries the seal, not just the page.
    formats = alice.get(f"/api/v1/workspaces/{ws}/items/{item}/diffusion").json()
    assert formats["poster"]["qr_url"].startswith(f"https://checky.example/sceau/v/{item}#")
    assert (
        formats["seal"]["number"] == 145 and formats["poster"]["check_label"] == "vérification 145"
    )


def test_unpublished_or_private_verdicts_have_no_public_seal(as_user, client, secret):
    alice = as_user("alice")
    ws = _workspace(alice)
    draft = alice.post(f"/api/v1/workspaces/{ws}/items", json={"title": "Brouillon privé"}).json()
    assert alice.get(f"/api/v1/workspaces/{ws}/items/{draft['id']}/seal").status_code == 409
    assert client.get(f"/api/v1/public/sceau/v/{draft['id']}").status_code == 404
    item = _published(alice, ws)
    alice.patch(f"/api/v1/workspaces/{ws}", json={"is_public": False})
    assert client.get(f"/api/v1/public/sceau/v/{item}").status_code == 404
    assert alice.get(f"/api/v1/workspaces/{ws}/items/{item}/seal").status_code == 409
    assert as_user("bob").get(f"/api/v1/workspaces/{ws}/items/{item}/seal").status_code == 404


def test_only_a_verified_newsroom_seals_or_vouches(as_user, client, secret):
    """Public verdicts and their seals leave only a newsroom Checky verified (`publishes`)."""
    alice = as_user("alice")
    ws = _workspace(alice)
    item = _published(alice, ws)
    sealed = alice.get(f"/api/v1/workspaces/{ws}/items/{item}/seal").json()
    _p, message, signature, key_id = seal.read_fragment(sealed["url"].split("#")[1])
    body = {"message": message, "signature": signature, "key_id": key_id}
    assert client.post(f"/api/v1/public/sceau/v/{item}/verify", json=body).json()["valid"] is True

    async def unverify():
        from sqlalchemy import text

        from app.core.db import engine

        async with engine.begin() as conn:
            await conn.execute(
                text("UPDATE app.workspace SET verification = 'refused' WHERE id = :id"), {"id": ws}
            )

    asyncio.run(unverify())
    # Still `is_public`, but no longer verified: no seal, no public check, no key published.
    assert alice.get(f"/api/v1/workspaces/{ws}/items/{item}/seal").status_code == 409
    assert client.get(f"/api/v1/public/sceau/v/{item}").status_code == 404
    check = client.post(f"/api/v1/public/sceau/v/{item}/verify", json=body).json()
    assert check["valid"] is False and check["newsroom"] is None
    keys = client.get("/api/v1/public/seal-keys").json()["keys"]
    assert all(k["key_id"] != key_id for k in keys)


def test_seal_needs_the_secret(as_user, client, monkeypatch):
    monkeypatch.setattr(get_settings(), "seal_secret", "")
    alice = as_user("alice")
    ws = _workspace(alice)
    item = _published(alice, ws)
    r = alice.get(f"/api/v1/workspaces/{ws}/items/{item}/seal")
    assert r.status_code == 503 and r.json()["error"]["code"] == "seal_unavailable"
    assert client.get(f"/api/v1/public/sceau/v/{item}").status_code == 404


def test_verdict_key_lives_in_its_own_namespace(as_user, client, secret):
    alice = as_user("alice")
    ws = _workspace(alice)
    item = _published(alice, ws)
    sealed = alice.get(f"/api/v1/workspaces/{ws}/items/{item}/seal").json()
    # A registry entry cannot take the reserved name, whatever its case or spacing.
    for name in ("checky:verdicts", "CHECKY:Verdicts", "  Checky:  autre", "ｃhecky:x"):
        r = alice.post(
            f"/api/v1/workspaces/{ws}/registry",
            json={"issuer": name, "title": "Faux", "text": "Un texte assez long pour le registre."},
        )
        assert r.status_code == 422, name
    # The issuers' key list and its revocation never reach the verdict key.
    keys = alice.get(f"/api/v1/workspaces/{ws}/registry/keys").json()
    assert all(k["key_id"] != sealed["key_id"] for k in keys)
    revoke = alice.post(f"/api/v1/workspaces/{ws}/registry/keys/{sealed['key_id']}/revoke")
    assert revoke.status_code == 404

    async def issuer_key_refuses():
        async with SessionLocal() as db:
            with pytest.raises(ApiError):
                await seal.issuer_key(db, uuid.UUID(ws), "Checky:Verdicts")

    asyncio.run(issuer_key_refuses())
    # Verification requires the verdict type: a signed message without it is refused.
    payload = {k: v for k, v in sealed["payload"].items() if k != "type"}
    assert seal.read_fragment(f"{seal.b64u(seal.canonical(payload).encode())}.s.k") is None
