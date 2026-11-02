"""The newsroom's seal on a published verdict: a signature a phone checks offline from the QR."""

import asyncio
import uuid
from datetime import UTC, datetime

import pytest

from app.core import seal
from app.core.config import get_settings
from app.core.db import SessionLocal
from tests.test_workspaces import _workspace

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
