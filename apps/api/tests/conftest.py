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
# Indexing is opt-in per test (tests/test_rag.py), so other tests never call a real provider.
os.environ["EMBED_PROVIDER"] = "none"

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core import security
from app.core.config import get_settings
from app.core.db import engine
from app.main import api

TABLES = "app.ai_cache, app.chunk, app.transcript, app.source, app.file, app.ai_call, app.job, app.activity, app.comment, app.item, app.invitation, app.membership, app.workspace"


@pytest.fixture(scope="session", autouse=True)
def _migrate():
    subprocess.run(["alembic", "upgrade", "head"], check=True, cwd=Path(__file__).parents[1])

    # Better Auth owns better_auth."user" in real deployments; tests need a stand-in to join on.
    async def auth_table():
        async with engine.begin() as conn:
            await conn.execute(text("CREATE SCHEMA IF NOT EXISTS better_auth"))
            await conn.execute(
                text(
                    'CREATE TABLE IF NOT EXISTS better_auth."user" (id text PRIMARY KEY, name text, email text)'
                )
            )
            await conn.execute(
                text(
                    """INSERT INTO better_auth."user" (id, name, email) VALUES
                    ('alice', 'Alice Rabe', 'alice@example.test'), ('bob', 'Bob Rakoto', 'bob@example.test')
                    ON CONFLICT (id) DO NOTHING"""
                )
            )

    asyncio.run(auth_table())


@pytest.fixture(autouse=True)
def _no_paid_voice(monkeypatch):
    # The real .env may hold an ElevenLabs key: no test may spend its credits.
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "elevenlabs_api_key", "")
    # A developer's optional search key must never spend real credits in tests.
    monkeypatch.setattr(get_settings(), "tavily_api_key", "")
    monkeypatch.setattr(get_settings(), "sightengine_api_user", "")
    monkeypatch.setattr(get_settings(), "sightengine_api_secret", "")
    monkeypatch.setattr(get_settings(), "web_search_provider", "auto")


@pytest.fixture(autouse=True)
def _clean_db():
    from app.core import ai

    # The gateway keeps per-process key rotation and cooldowns; each test starts fresh.
    ai._turn.clear()
    ai._cooldown.clear()
    from app.modules import public

    public._TIPS.clear()
    public._ASKS.clear()
    public._VOICE.clear()
    public._SPEAKS.clear()
    public._AUDIO.clear()
    from app.modules import guide

    guide._GUIDES.clear()
    from app.modules import imagecheck

    imagecheck._IMAGES.clear()
    from app.core.public_checks import budget

    budget.reset()
    from app.core import websearch

    websearch._cache.clear()
    from app.core import query_plan

    query_plan._cache.clear()
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
