import asyncio
import os
import subprocess
import time
from pathlib import Path

# Point the app at the test database before anything imports the settings.
_base = os.environ.get("DATABASE_URL") or next(
    (
        line.split("=", 1)[1].strip()
        for line in (Path(__file__).parents[3] / ".env").read_text().splitlines()
        if line.startswith("DATABASE_URL=")
    ),
    "postgresql://postgres@localhost:5432/fanilo",
)
os.environ["DATABASE_URL"] = (
    os.environ.get("TEST_DATABASE_URL") or _base.rsplit("/", 1)[0] + "/fanilo_test"
)
os.environ["DB_POOL"] = "false"
os.environ["JOB_WORKERS"] = "0"

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core import security
from app.core.config import get_settings
from app.core.db import engine
from app.main import api

TABLES = (
    "app.job, app.activity, app.comment, app.item, app.invitation, app.membership, app.workspace"
)


@pytest.fixture(scope="session", autouse=True)
def _migrate():
    subprocess.run(["alembic", "upgrade", "head"], check=True, cwd=Path(__file__).parents[1])


@pytest.fixture(autouse=True)
def _clean_db():
    yield

    async def truncate():
        async with engine.begin() as conn:
            await conn.execute(text(f"TRUNCATE {TABLES} CASCADE"))

    asyncio.run(truncate())


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


@pytest.fixture
def as_user(make_token):
    """as_user("alice") -> a client whose requests carry alice's JWT."""

    def _client(sub: str) -> TestClient:
        c = TestClient(api)
        c.headers["Authorization"] = f"Bearer {make_token(sub)}"
        return c

    return _client
