import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

from app.core import security
from app.core.config import get_settings
from app.main import api


class _StaticJWKS:
    def __init__(self, public_key):
        self._key = public_key

    def get_signing_key_from_jwt(self, _token):
        return type("K", (), {"key": self._key})()


@pytest.fixture
def signing_key(monkeypatch):
    """Stand in for the web app's JWKS with a local Ed25519 key."""
    private = Ed25519PrivateKey.generate()
    monkeypatch.setattr(security, "_jwks_client", _StaticJWKS(private.public_key()))
    return private


@pytest.fixture
def make_token(signing_key):
    s = get_settings()

    def _make(sub="user-1", exp_in=300, **overrides):
        claims = {
            "sub": sub,
            "email": f"{sub}@example.test",
            "iss": s.auth_issuer,
            "aud": s.auth_audience,
            "exp": int(time.time()) + exp_in,
            **overrides,
        }
        return jwt.encode(claims, signing_key, algorithm="EdDSA")

    return _make


@pytest.fixture
def client():
    return TestClient(api)
