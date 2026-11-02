import pytest

from app.core import attest
from app.core.config import get_settings


def test_sign_and_verify_with_a_key_derived_from_the_secret(monkeypatch):
    monkeypatch.setattr(get_settings(), "seal_secret", "a long random test secret")
    signed = attest.sign({"ref": "FAN-0145", "verdict": "false", "titre": "Délestage"})
    assert attest.verify(signed["payload"], signed["signature"])
    assert len(signed["key_id"]) == 16 and len(signed["sha256"]) == 64
    # Same secret, same key: an attestation survives a restart.
    assert attest.public_key()["public_key"] == signed["public_key"]
    # Any change to the payload breaks the signature.
    assert not attest.verify({**signed["payload"], "verdict": "true"}, signed["signature"])
    assert not attest.verify(signed["payload"], "not base64 at all!")
    # A rotated secret no longer verifies older attestations.
    monkeypatch.setattr(get_settings(), "seal_secret", "another secret")
    assert not attest.verify(signed["payload"], signed["signature"])


def test_no_secret_means_no_attestation(monkeypatch):
    monkeypatch.setattr(get_settings(), "seal_secret", "")
    with pytest.raises(attest.AttestationUnavailable):
        attest.sign({"ref": "FAN-0001"})
