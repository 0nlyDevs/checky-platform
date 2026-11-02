import asyncio
import json
import time

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from jwt.algorithms import OKPAlgorithm

from app.core import security


def _jwk(private, kid):
    data = json.loads(OKPAlgorithm.to_jwk(private.public_key()))
    return {**data, "kid": kid, "alg": "EdDSA"}


def _token(private, kid, sub="alice"):
    s = security.get_settings()
    claims = {
        "sub": sub,
        "iss": s.auth_issuer,
        "aud": s.auth_audience,
        "exp": int(time.time()) + 60,
    }
    return jwt.encode(claims, private, algorithm="EdDSA", headers={"kid": kid})


@pytest.fixture
def served(monkeypatch):
    """A JWKS endpoint whose keys the test changes; counts the fetches."""
    state = {"keys": [], "fetches": 0}

    def answer(_request):
        state["fetches"] += 1
        return httpx.Response(200, json={"keys": state["keys"]})

    monkeypatch.setattr(security.Jwks, "transport", httpx.MockTransport(answer))
    monkeypatch.setattr(security, "_jwks_client", None)
    return state


def test_keys_are_fetched_once_and_shared_by_concurrent_requests(served):
    k1 = Ed25519PrivateKey.generate()
    served["keys"] = [_jwk(k1, "k1")]

    async def go():
        users = await asyncio.gather(*(security.decode_token(_token(k1, "k1")) for _ in range(5)))
        return [u.id for u in users]

    assert asyncio.run(go()) == ["alice"] * 5
    assert served["fetches"] == 1


def test_a_rotated_key_triggers_one_refetch_and_forged_kids_do_not_hammer(served):
    k1, k2 = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
    served["keys"] = [_jwk(k1, "k1")]

    async def go():
        jwks = security._jwks()
        await security.decode_token(_token(k1, "k1"))
        served["keys"] = [_jwk(k1, "k1"), _jwk(k2, "k2")]
        jwks._fetched -= 60  # past the refetch guard
        assert (await security.decode_token(_token(k2, "k2"))).id == "alice"
        assert served["fetches"] == 2
        # A token naming a key nobody published: refused, and no new fetch within the guard.
        for _ in range(3):
            with pytest.raises(security.ApiError):
                await security.decode_token(_token(Ed25519PrivateKey.generate(), "forged"))
        assert served["fetches"] == 2

    asyncio.run(go())


def test_an_unreachable_jwks_is_a_401_not_a_crash(monkeypatch):
    def down(_request):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(security.Jwks, "transport", httpx.MockTransport(down))
    monkeypatch.setattr(security, "_jwks_client", None)
    with pytest.raises(security.ApiError) as e:
        asyncio.run(security.decode_token(_token(Ed25519PrivateKey.generate(), "k1")))
    assert e.value.status_code == 401
