"""Verified newsrooms: a request, the Checky team's review, and nothing public before approval."""

from tests.test_public import _claim
from tests.test_workspaces import _join, _workspace

REQUEST = {
    "outlet": "Radio Exemple (démo)",
    "kind": "radio",
    "city": "Antsirabe",
    "region": "Vakinankaratra",
    "country": "mg",
    "website": "facebook.com/radio-exemple-demo",
    "full_name": "Hery Démo",
    "job_title": "Rédacteur en chef",
    "phone": "034 12 345 67",
    "email": "Redaction@Radio-Exemple.test",
}


def _admin(as_user, make_token):
    c = as_user("checky")
    c.headers["Authorization"] = f"Bearer {make_token('checky')}"
    return c


def test_request_then_approval_opens_the_public_side(as_user, make_token, client):
    alice = as_user("alice")
    ws = _workspace(alice)
    assert alice.get(f"/api/v1/workspaces/{ws}/verification").json()["status"] == "none"

    r = alice.put(f"/api/v1/workspaces/{ws}/verification", json=REQUEST)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "pending"
    assert body["request"]["phone"] == "+261341234567"
    assert body["request"]["country"] == "MG"
    assert body["request"]["website"] == "https://facebook.com/radio-exemple-demo"
    assert body["request"]["email"] == "redaction@radio-exemple.test"
    assert alice.get(f"/api/v1/workspaces/{ws}").json()["settings"]["country"] == "Madagascar"

    # Opted in and a verdict published, but not verified yet: nothing leaves.
    alice.patch(f"/api/v1/workspaces/{ws}", json={"is_public": True})
    _claim(alice, ws, "Le riz coûte 10 000 Ar", status="published", verdict="false")
    assert client.get("/api/v1/public/verdicts").json()["total"] == 0
    assert client.get("/api/v1/public/newsrooms").json() == []

    admin = _admin(as_user, make_token)
    assert admin.get("/api/v1/me").json()["platform_admin"] is True
    rows = admin.get("/api/v1/platform/requests?status=pending").json()
    assert [r["workspace_id"] for r in rows] == [ws]
    assert rows[0]["request"]["full_name"] == "Hery Démo"
    assert rows[0]["members"] == 1

    assert admin.post(f"/api/v1/platform/requests/{ws}/approve").json()["status"] == "approved"
    assert client.get("/api/v1/public/verdicts").json()["total"] == 1
    assert alice.get("/api/v1/me").json()["memberships"][0]["verification"] == "approved"
    # Approved stays approved: the newsroom cannot reopen its own request.
    assert alice.put(f"/api/v1/workspaces/{ws}/verification", json=REQUEST).status_code == 409


def test_refusal_carries_a_reason_and_can_be_answered(as_user, make_token):
    alice = as_user("alice")
    ws = _workspace(alice)
    alice.put(f"/api/v1/workspaces/{ws}/verification", json=REQUEST)
    admin = _admin(as_user, make_token)
    r = admin.post(f"/api/v1/platform/requests/{ws}/refuse", json={"reason": "Numéro injoignable"})
    assert r.json()["status"] == "refused"
    mine = alice.get(f"/api/v1/workspaces/{ws}/verification").json()
    assert mine == mine | {"status": "refused", "reason": "Numéro injoignable"}
    # Corrected and sent again: pending, reason cleared.
    again = alice.put(
        f"/api/v1/workspaces/{ws}/verification", json=REQUEST | {"phone": "0321234567"}
    )
    assert again.json()["status"] == "pending"
    assert again.json()["reason"] is None


def test_only_the_checky_team_reviews(as_user):
    alice, bob = as_user("alice"), as_user("bob")
    ws = _workspace(alice)
    _join(alice, bob, ws)
    alice.put(f"/api/v1/workspaces/{ws}/verification", json=REQUEST)
    assert alice.get("/api/v1/me").json()["platform_admin"] is False
    assert alice.get("/api/v1/platform/requests").status_code == 404
    assert alice.post(f"/api/v1/platform/requests/{ws}/approve").status_code == 404
    # A colleague sees the request; an outsider does not.
    assert bob.get(f"/api/v1/workspaces/{ws}/verification").json()["status"] == "pending"
    assert as_user("eve").get(f"/api/v1/workspaces/{ws}/verification").status_code == 404


def test_request_checks_phone_country_and_page(as_user):
    alice = as_user("alice")
    ws = _workspace(alice)
    url = f"/api/v1/workspaces/{ws}/verification"
    assert alice.put(url, json=REQUEST | {"phone": "12"}).status_code == 422
    assert alice.put(url, json=REQUEST | {"phone": "0612345678"}).json()["error"]["code"] == (
        "invalid_phone"
    )
    assert alice.put(url, json=REQUEST | {"country": "ZZ"}).status_code == 422
    assert alice.put(url, json=REQUEST | {"website": "pas une page"}).status_code == 422
    # A French number for a French newsroom is fine: Checky is not tied to one country.
    ok = alice.put(url, json=REQUEST | {"country": "FR", "phone": "06 12 34 56 78"})
    assert ok.json()["request"]["phone"] == "+33612345678"


def test_countries_are_listed_in_french(client):
    rows = client.get("/api/v1/public/countries").json()
    assert {"code": "MG", "name": "Madagascar"} in rows
    assert {"code": "SN", "name": "Sénégal"} in rows


def test_a_listed_email_counts_only_once_confirmed(make_token):
    from fastapi.testclient import TestClient

    from app.main import api

    def me(**claims):
        c = TestClient(api)
        c.headers["Authorization"] = f"Bearer {make_token('mallory', **claims)}"
        return c.get("/api/v1/me").json()["platform_admin"]

    assert me(email="boss@example.test") is False
    assert me(email="boss@example.test", emailVerified=False) is False
    assert me(email="BOSS@example.test", emailVerified=True) is True


def test_a_verified_newsroom_keeps_its_name(as_user, make_token):
    alice = as_user("alice")
    ws = _workspace(alice)
    alice.put(f"/api/v1/workspaces/{ws}/verification", json=REQUEST)
    assert alice.patch(f"/api/v1/workspaces/{ws}", json={"name": "Avant"}).status_code == 200
    _admin(as_user, make_token).post(f"/api/v1/platform/requests/{ws}/approve")
    r = alice.patch(f"/api/v1/workspaces/{ws}", json={"name": "Autre nom"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "verified_name_locked"
    assert alice.patch(f"/api/v1/workspaces/{ws}", json={"name": "Avant"}).status_code == 200
