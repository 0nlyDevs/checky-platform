"""Official sites: the rule for government domains, and the per-country list newsrooms keep."""

import asyncio

from app.core.confidence import is_official
from app.core.db import SessionLocal
from app.modules.official import country_hosts
from tests.test_workspaces import _verify, _workspace


def test_government_domains_are_official_in_every_country():
    for url in (
        "https://www.sante.gov.mg/",
        "https://primature.gouv.sn",
        "https://health.go.ke",
        "https://www.gob.mx/salud",
        "https://data.worldbank.org/x",
        "https://www.who.int",
    ):
        assert is_official(url), url
    for url in (
        "https://govtech.com",
        "https://example.mg",
        "https://gov.example.com",
        "https://gov.ly-example.ly",
        "https://www.go.example.io",
    ):
        assert not is_official(url), url


def _hosts(ws):
    async def run():
        async with SessionLocal() as db:
            return await country_hosts(db, ws)

    return asyncio.run(run())


def test_a_country_list_is_shared_only_from_verified_newsrooms(as_user):
    alice, bob, sara = as_user("alice"), as_user("bob"), as_user("sara")
    a, b = _workspace(alice, "Tana"), _workspace(bob, "Toamasina")
    s = _workspace(sara, "Dakar")
    sara.patch(f"/api/v1/workspaces/{s}", json={"settings": {"country": "Sénégal"}})
    r = alice.post(
        f"/api/v1/workspaces/{a}/official-sources",
        json={"url": "https://www.jirama.mg/communiques", "name": "Jirama"},
    )
    assert r.status_code == 201
    assert r.json() | {"id": None} == {
        "id": None,
        "host": "jirama.mg",
        "name": "Jirama",
        "country": "Madagascar",
        "mine": True,
        "shared": False,
    }
    # Counted at once for the newsroom that added it, for the others once it is verified.
    assert _hosts(a) == {"jirama.mg"} and _hosts(b) == set()
    assert bob.get(f"/api/v1/workspaces/{b}/official-sources").json() == []
    _verify(a)
    assert _hosts(b) == {"jirama.mg"}
    assert [o["host"] for o in bob.get(f"/api/v1/workspaces/{b}/official-sources").json()] == [
        "jirama.mg"
    ]
    # Another country does not see it.
    assert _hosts(s) == set()
    # Already official by rule, or already listed: refused. Only its newsroom removes it.
    gov = {"url": "sante.gov.mg", "name": "Ministère de la Santé"}
    assert bob.post(f"/api/v1/workspaces/{b}/official-sources", json=gov).status_code == 409
    again = {"url": "jirama.mg", "name": "Jirama"}
    assert alice.post(f"/api/v1/workspaces/{a}/official-sources", json=again).status_code == 409
    # Another newsroom may list it too (no squatting); the list shows it once.
    assert bob.post(f"/api/v1/workspaces/{b}/official-sources", json=again).status_code == 201
    assert len(bob.get(f"/api/v1/workspaces/{b}/official-sources").json()) == 1
    for platform in ("facebook.com/jirama", "jirama.wordpress.com", "com.mg", "x.github.io"):
        r2 = bob.post(
            f"/api/v1/workspaces/{b}/official-sources", json={"url": platform, "name": "Faux"}
        )
        assert r2.status_code == 422, platform
    oid = r.json()["id"]
    assert bob.delete(f"/api/v1/workspaces/{b}/official-sources/{oid}").status_code == 404
    assert alice.delete(f"/api/v1/workspaces/{a}/official-sources/{oid}").status_code == 204
    assert _hosts(a) == set() and _hosts(b) == {"jirama.mg"}
