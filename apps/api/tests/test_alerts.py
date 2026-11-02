"""Fanairana: the adjusted danger level, alerts, their kit, live notices and the morning brief."""

from tests.test_public import _newsroom
from tests.test_workspaces import _join


def _dossier(c, ws, title, risk="medium", **data):
    r = c.post(
        f"/api/v1/workspaces/{ws}/items",
        json={
            "title": title,
            "status": "to_check",
            "data": {"risk": {"level": risk, "reasons": [], "by": "code"}, **data},
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


# --- danger level
def test_a_journalist_adjusts_the_danger_level_and_it_wins_everywhere(as_user):
    alice, bob = as_user("alice"), as_user("bob")
    ws, _ = _newsroom(alice)
    _join(alice, bob, ws)
    item = _dossier(alice, ws, "Un enlèvement d'enfant à Mahajanga", risk="medium")

    r = bob.put(
        f"/api/v1/workspaces/{ws}/items/{item}/risk",
        json={"level": "high", "reason": "Des parents gardent leurs enfants à la maison"},
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["risk"]["level"] == "medium"  # Checky's own level stays beside it
    assert data["risk_override"]["level"] == "high"
    assert data["risk_override"]["by"] == "bob" and data["risk_override"]["at"]

    from app.modules.veille import risk_level

    assert risk_level(data) == "high"
    assert risk_level({"risk": {"level": "low"}}) == "low"
    assert risk_level({}) is None

    carnet = alice.get(f"/api/v1/workspaces/{ws}/items/{item}/carnet").json()
    lines = [e["text"] for e in carnet["entries"]]
    assert any("Niveau de danger ajusté : élevé" in x and "parents" in x for x in lines)

    r = alice.delete(f"/api/v1/workspaces/{ws}/items/{item}/risk")
    assert "risk_override" not in r.json()["data"]
    lines = [
        e["text"]
        for e in alice.get(f"/api/v1/workspaces/{ws}/items/{item}/carnet").json()["entries"]
    ]
    assert any("rendu à Checky : moyen" in x for x in lines)


def test_the_danger_level_needs_a_reason_and_a_member(as_user):
    alice, bob = as_user("alice"), as_user("bob")
    ws, _ = _newsroom(alice)
    item = _dossier(alice, ws, "Une rumeur")
    url = f"/api/v1/workspaces/{ws}/items/{item}/risk"
    assert alice.put(url, json={"level": "high"}).status_code == 422
    assert alice.put(url, json={"level": "extreme", "reason": "parce que"}).status_code == 422
    assert bob.put(url, json={"level": "high", "reason": "parce que"}).status_code == 404
