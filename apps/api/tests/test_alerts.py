"""Fanairana: the adjusted danger level, and alerts grouping rumour variants (split, merge)."""

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


# --- grouping
KIDNAP_FR = (
    "Un auditeur affirme que des voleurs d'enfants ont enlevé une fillette près du marché de "
    "Mahajanga hier soir."
)
KIDNAP_FR_2 = (
    "Enlèvement d'enfant au marché : des voleurs d'enfants rôderaient à Antsohihy, gardez les "
    "enfants à la maison."
)
KIDNAP_MG = (
    "Nilaza ny mpihaino iray fa nisy ankizy nalaina an-keriny teo akaikin'ny tsena tany "
    "Antsohihy, mpangalatra ankizy no nanao izany."
)
RICE = "Le prix du riz a encore augmenté au marché de Toamasina cette semaine selon un auditeur."
RICE_2 = "Le prix du riz augmente au marché de Toamasina, disent les commerçants."


def _clip(c, ws, text, station, language="fr", region=None):
    from tests.test_veille import _clip as clip

    extra = {"location": {"region": region}} if region else {}
    return clip(c, ws, text, station=station, language=language, **extra)


def _alerts(c, ws, state="open"):
    r = c.get(f"/api/v1/workspaces/{ws}/alerts?state={state}")
    assert r.status_code == 200, r.text
    return r.json()


def _scan(c, ws):
    r = c.post(f"/api/v1/workspaces/{ws}/alerts/scan")
    assert r.status_code == 200, r.text
    return r.json()


def test_concepts_make_french_and_malagasy_variants_meet():
    from app.modules.alerts import concepts, word_overlap

    fr, mg = concepts(KIDNAP_FR), concepts(KIDNAP_MG)
    assert {"enlevement", "enfant", "marche"} <= fr & mg
    assert "mahajanga" not in fr and "antsohihy" not in mg  # another town is the same story
    assert word_overlap(fr, mg) >= 0.34
    assert word_overlap(concepts(RICE), fr) < 0.34


def test_variants_across_radios_and_regions_become_one_alert(as_user):
    alice = as_user("alice")
    ws, _ = _newsroom(alice)
    _clip(alice, ws, KIDNAP_FR, "Radio Boeny (démo)", region="Boeny")
    _clip(alice, ws, KIDNAP_MG, "Radio Sofia (démo)", language="mg", region="Sofia")
    _dossier(alice, ws, KIDNAP_FR_2, risk="high")
    _clip(alice, ws, RICE, "Radio Boeny (démo)")
    _clip(alice, ws, RICE_2, "Radio Toamasina (démo)")

    assert _scan(alice, ws) == {"created": 1, "updated": 0}
    [alert] = _alerts(alice, ws)
    assert alert["ref"] == "ALR-0001" and alert["state"] == "open"
    assert alert["level"] == "high"
    # the alert reads like the desk's dossier, not like the first radio sentence
    assert alert["title"].startswith(KIDNAP_FR_2.split(".")[0][:40])
    facts = alert["facts"]
    assert facts["reports"] == 3
    assert sorted(facts["stations"]) == ["Radio Boeny (démo)", "Radio Sofia (démo)"]
    assert sorted(facts["regions"]) == ["Boeny", "Sofia"]
    assert facts["kinds"] == {"clip": 2, "item": 1}
    assert facts["hours"] is not None
    assert any(r["kind"] == "accusation" for r in alert["reasons"])
    # the rice price circulates too, but it puts nobody in danger: no alert
    assert all("riz" not in m["title"] for m in alert["members"])
    # alerts stay out of the dossiers list
    listed = alice.get(f"/api/v1/workspaces/{ws}/items?type=claim").json()["items"]
    assert all(i["type"] == "claim" for i in listed)
    # scanning again changes nothing; a new variant joins the open alert
    assert _scan(alice, ws) == {"created": 0, "updated": 0}
    _clip(alice, ws, KIDNAP_FR_2 + " Encore un appel.", "Radio Boeny (démo)", region="Boeny")
    assert _scan(alice, ws) == {"created": 0, "updated": 1}
    assert _alerts(alice, ws)[0]["facts"]["reports"] == 4


def test_a_journalists_adjusted_level_raises_an_alert(as_user):
    alice = as_user("alice")
    ws, _ = _newsroom(alice)
    a = _dossier(alice, ws, "Coupure d'eau de trois jours annoncée à Toamasina", risk="low")
    _dossier(alice, ws, "Trois jours sans eau à Toamasina, coupure annoncée", risk="low")
    assert _scan(alice, ws)["created"] == 0
    alice.put(
        f"/api/v1/workspaces/{ws}/items/{a}/risk",
        json={"level": "high", "reason": "Ruée sur les bidons dans les quartiers"},
    )
    assert _scan(alice, ws)["created"] == 1


def test_journalists_split_and_merge_and_code_respects_it(as_user):
    alice = as_user("alice")
    ws, _ = _newsroom(alice)
    _clip(alice, ws, KIDNAP_FR, "Radio Boeny (démo)", region="Boeny")
    _clip(alice, ws, KIDNAP_MG, "Radio Sofia (démo)", language="mg", region="Sofia")
    _dossier(alice, ws, KIDNAP_FR_2, risk="high")
    _scan(alice, ws)
    [alert] = _alerts(alice, ws)
    mg = next(m["key"] for m in alert["members"] if m["station"] == "Radio Sofia (démo)")
    url = f"/api/v1/workspaces/{ws}/alerts/{alert['id']}"

    r = alice.post(f"{url}/split", json={"keys": [mg]})
    assert r.status_code == 201, r.text
    other = r.json()
    assert [m["key"] for m in other["members"]] == [mg] and other["ref"] == "ALR-0002"
    first = alice.get(url).json()
    assert mg in first["excluded"] and first["facts"]["reports"] == 2
    _scan(alice, ws)
    assert mg not in {m["key"] for m in alice.get(url).json()["members"]}
    assert alice.post(f"{url}/split", json={"keys": ["clip:nope"]}).status_code == 422

    r = alice.post(f"{url}/merge", json={"other_id": other["id"]})
    assert r.status_code == 200
    assert r.json()["facts"]["reports"] == 3 and mg not in r.json()["excluded"]
    closed = alice.get(f"/api/v1/workspaces/{ws}/alerts/{other['id']}").json()
    assert closed["state"] == "closed" and closed["closed"]["reason"] == "merged"
    assert len(_alerts(alice, ws)) == 1


def test_embeddings_group_variants_with_no_word_in_common(as_user, monkeypatch):
    from app.core import embed
    from app.modules import alerts

    alerts._vectors.clear()
    alice = as_user("alice")
    ws, _ = _newsroom(alice)
    _dossier(alice, ws, "Des voleurs d'enfants rôdent près des écoles", risk="high")
    _dossier(alice, ws, "Mpangalatra zaza mivezivezy manodidina ny sekoly", risk="high")
    monkeypatch.setattr(alerts, "concepts", lambda text: set(text.lower().split()))

    async def fake(texts):
        return [[1.0, 0.1] for _ in texts]

    monkeypatch.setattr(embed, "configured", lambda: True)
    monkeypatch.setattr(embed, "embed", fake)
    assert _scan(alice, ws)["created"] == 1


def test_alerts_are_private_to_the_newsroom(as_user):
    alice, bob = as_user("alice"), as_user("bob")
    ws, _ = _newsroom(alice)
    _clip(alice, ws, KIDNAP_FR, "Radio Boeny (démo)", region="Boeny")
    _dossier(alice, ws, KIDNAP_FR_2, risk="high")
    _scan(alice, ws)
    [alert] = _alerts(alice, ws)
    assert bob.get(f"/api/v1/workspaces/{ws}/alerts").status_code == 404
    assert bob.get(f"/api/v1/workspaces/{ws}/alerts/{alert['id']}").status_code == 404


def test_veille_and_alerts_tell_one_story(as_user):
    """A clip the desk attached to a dossier goes with it even with no word in common, and each
    « À l'antenne » row names the alert its reports belong to."""
    alice = as_user("alice")
    ws, _ = _newsroom(alice)
    base = f"/api/v1/workspaces/{ws}"
    dossier = _dossier(alice, ws, KIDNAP_FR_2, risk="high")
    _clip(alice, ws, KIDNAP_FR, "Radio Boeny (démo)", region="Boeny")
    odd = _clip(alice, ws, "Les gens de Mahajanga restent chez eux ce matin.", "Radio Sofia (démo)")
    r = alice.post(f"{base}/radio-clips/{odd['id']}/follow", json={"item_id": dossier})
    assert r.status_code == 200, r.text
    _clip(alice, ws, RICE, "Radio Boeny (démo)")

    _scan(alice, ws)
    [alert] = _alerts(alice, ws)
    assert f"clip:{odd['id']}" in {m["key"] for m in alert["members"]}
    assert alert["facts"]["reports"] == 3

    rows = alice.get(f"{base}/antenne").json()
    tagged = [r for r in rows if r["alert"]]
    assert tagged and all(r["alert"]["ref"] == "ALR-0001" for r in tagged)
    assert all(r["alert"]["level"] == "high" for r in tagged)
    assert any(r["item_id"] == dossier for r in tagged)
    assert all(r["alert"] is None for r in rows if "riz" in r["claim"])

    # the dossier detail asks for the alerts it belongs to
    mine = alice.get(f"{base}/alerts?item_id={dossier}").json()
    assert [a["id"] for a in mine] == [alert["id"]]
    other = _dossier(alice, ws, "Une autre histoire sans rapport", risk="low")
    assert alice.get(f"{base}/alerts?item_id={other}").json() == []


def test_alerts_stay_out_of_the_items_list(as_user):
    alice = as_user("alice")
    ws, _ = _newsroom(alice)
    _clip(alice, ws, KIDNAP_FR, "Radio Boeny (démo)", region="Boeny")
    _dossier(alice, ws, KIDNAP_FR_2, risk="high")
    _scan(alice, ws)
    base = f"/api/v1/workspaces/{ws}/items"
    assert {i["type"] for i in alice.get(base).json()["items"]} == {"claim"}
    assert [i["type"] for i in alice.get(f"{base}?type=alert").json()["items"]] == ["alert"]


def test_a_journalist_adjusts_an_alerts_level(as_user):
    alice = as_user("alice")
    ws, _ = _newsroom(alice)
    _clip(alice, ws, KIDNAP_FR, "Radio Boeny (démo)", region="Boeny")
    _dossier(alice, ws, KIDNAP_FR_2, risk="high")
    _scan(alice, ws)
    [alert] = _alerts(alice, ws)
    r = alice.put(
        f"/api/v1/workspaces/{ws}/items/{alert['id']}/risk",
        json={"level": "medium", "reason": "La gendarmerie a démenti à l'antenne"},
    )
    assert r.status_code == 200, r.text
    [after] = _alerts(alice, ws)
    assert after["level"] == "medium" and after["code_level"] == "high"
    assert after["override"]["reason"] == "La gendarmerie a démenti à l'antenne"
    # a new scan keeps the journalist's level
    _clip(alice, ws, KIDNAP_FR_2 + " Encore.", "Radio Boeny (démo)", region="Boeny")
    _scan(alice, ws)
    assert _alerts(alice, ws)[0]["level"] == "medium"
