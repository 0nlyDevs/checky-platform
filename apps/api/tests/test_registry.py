"""Registre: originals, confirmations by another newsroom, fakes caught, and the word-by-word match."""

from tests.test_newsroom_resources import invite
from tests.test_workspaces import _workspace

ORIGINAL_TEXT = (
    "COMMUNIQUÉ N° 2026-118. La JIRAMA informe ses abonnés d'Antananarivo qu'en raison de travaux "
    "de maintenance sur la centrale d'Andekaleka, un délestage de 4 heures par jour et par quartier "
    "sera appliqué du 3 au 9 novembre 2026, selon un programme tournant publié chaque matin. "
    "La JIRAMA présente ses excuses pour la gêne occasionnée."
)
RUMOUR = (
    "URGENT ⚠️ COMMUNIQUÉ N° 2026-118 de la JIRAMA : délestage de 72 heures à partir du 3 novembre "
    "sur tout Antananarivo, hausse de 40 % du tarif en décembre. Partagez à tous vos contacts !!!"
)
ORIGINAL = {
    "issuer": "JIRAMA",
    "number": "2026-118",
    "issued_on": "2026-11-01",
    "title": "Programme de délestage à Antananarivo",
    "text": ORIGINAL_TEXT,
    "place": "Antananarivo",
}


def _public(client, ws):
    assert client.patch(f"/api/v1/workspaces/{ws}", json={"is_public": True}).status_code == 200


def test_an_original_is_registered_read_and_confirmed_by_another_newsroom(as_user):
    alice, bob = as_user("alice"), as_user("bob")
    ws, other = _workspace(alice), _workspace(bob, "Radio desk")
    created = alice.post(f"/api/v1/workspaces/{ws}/registry", json=ORIGINAL)
    assert created.status_code == 201
    entry = created.json()
    assert entry["status"] == "original" and entry["own"] and entry["confirmations"] == 1
    assert entry["location"]["region"] == "Analamanga"
    assert len(entry["fingerprint"]) == 64 and entry["sealed"] is None
    cid = entry["id"]
    assert alice.get(f"/api/v1/workspaces/{ws}/registry/{cid}").json()["title"] == ORIGINAL["title"]
    # A future date is refused; a newsroom that is not public keeps its registry to itself.
    future = {**ORIGINAL, "issued_on": "2999-01-01"}
    assert alice.post(f"/api/v1/workspaces/{ws}/registry", json=future).status_code == 422
    assert bob.get(f"/api/v1/workspaces/{other}/registry/{cid}").status_code == 404
    assert bob.get(f"/api/v1/workspaces/{other}/registry", params={"scope": "network"}).json() == []

    _public(alice, ws)
    network = bob.get(f"/api/v1/workspaces/{other}/registry", params={"scope": "network"}).json()
    assert [e["id"] for e in network] == [cid] and network[0]["newsroom"]["name"] == "Desk"
    assert alice.post(f"/api/v1/workspaces/{ws}/registry/{cid}/confirm").status_code == 409
    confirmed = bob.post(f"/api/v1/workspaces/{other}/registry/{cid}/confirm").json()
    assert confirmed["confirmations"] == 2 and confirmed["confirmed"]
    assert confirmed["confirmed_by_us"] and not confirmed["own"]
    again = bob.post(f"/api/v1/workspaces/{other}/registry/{cid}/confirm").json()
    assert again["confirmations"] == 2
    assert alice.get(f"/api/v1/workspaces/{ws}/registry").json()[0]["confirmed"]


def test_a_journalist_cannot_register_but_records_a_fake_with_its_diff(as_user):
    alice, bob = as_user("alice"), as_user("bob")
    ws = _workspace(alice)
    invite(alice, ws, bob, "journalist")
    base = f"/api/v1/workspaces/{ws}/registry"
    assert bob.post(base, json=ORIGINAL).status_code == 403
    cid = alice.post(base, json=ORIGINAL).json()["id"]
    assert bob.post(f"{base}/{cid}/fake", json={"text": ORIGINAL_TEXT}).status_code == 409
    fake = bob.post(f"{base}/{cid}/fake", json={"text": RUMOUR, "url": "https://example.org/post"})
    assert fake.status_code == 201
    caught = fake.json()
    assert caught["status"] == "fake_caught" and caught["original_id"] == cid
    assert caught["number"] == "2026-118" and caught["url"] == "https://example.org/post"
    assert {
        "original": "4 heures par jour",
        "submitted": "72 heures",
        "kind": "duration",
    } in caught["changed_numbers"]
    assert any(op["op"] != "equal" for op in caught["diff"])
    assert alice.get(f"{base}/{cid}").json()["fakes"] == 1
    assert [f["id"] for f in alice.get(f"{base}/{cid}/fakes").json()] == [caught["id"]]
    assert [e["id"] for e in alice.get(base, params={"status": "fake_caught"}).json()] == [
        caught["id"]
    ]


def test_the_pitch_rumour_is_matched_to_the_original_and_shows_what_changed(as_user):
    alice, bob = as_user("alice"), as_user("bob")
    ws, other = _workspace(alice), _workspace(bob, "Radio desk")
    cid = alice.post(f"/api/v1/workspaces/{ws}/registry", json=ORIGINAL).json()["id"]
    _public(alice, ws)
    # Another newsroom pastes the rumour: the public newsroom's original is found by its number.
    found = bob.post(f"/api/v1/workspaces/{other}/registry/match", json={"text": RUMOUR}).json()
    assert found["status"] == "modified"
    assert found["issuer"] == "JIRAMA" and found["number"] == "2026-118"
    assert found["communique"]["id"] == cid and found["communique"]["newsroom"]["name"] == "Desk"
    assert {"kind": "duration", "original": "4 heures par jour", "submitted": "72 heures"} in found[
        "changed_numbers"
    ]
    assert {"kind": "percent", "original": None, "submitted": "40 %"} in found["changed_numbers"]
    replaced = [op for op in found["diff"] if op["op"] == "replace"]
    assert any(op["a"] == "4" and op["b"] == "72" for op in replaced)
    assert {"op", "a", "b"} == set(found["diff"][0])
    assert "4 heures par jour" in found["summary"] and "1er novembre 2026" in found["summary"]


def test_match_statuses(as_user):
    alice = as_user("alice")
    ws = _workspace(alice)
    base = f"/api/v1/workspaces/{ws}/registry"
    alice.post(base, json=ORIGINAL)
    alice.post(
        base,
        json={
            **ORIGINAL,
            "number": "2026-090",
            "title": "Travaux sur le réseau d'eau",
            "text": "La JIRAMA annonce une coupure d'eau à Ivandry le mardi de 8 heures à midi.",
        },
    )

    def match(text):
        return alice.post(f"{base}/match", json={"text": text}).json()

    forwarded = match(f"Transféré plusieurs fois\n{ORIGINAL_TEXT}")
    assert forwarded["status"] == "authentic" and "mot pour mot" in forwarded["summary"]
    # Found by its words even when the number is left out.
    reworded = match(
        ORIGINAL_TEXT.replace("COMMUNIQUÉ N° 2026-118. ", "").replace("4 heures", "8 heures")
    )
    assert reworded["status"] == "modified" and reworded["number"] == "2026-118"

    unknown = match("Selon la CENI, communiqué N° 45/2026 : le scrutin est reporté.")
    assert unknown["status"] == "not_found" and unknown["issuer"] == "CENI"
    assert (
        unknown["number"] == "45/2026" and "Introuvable ne veut pas dire faux" in unknown["summary"]
    )
    assert "faux" not in unknown["summary"].replace("pas dire faux", "")
    odd = match("JIRAMA, communiqué n° 118/2026/DG : nouvelle grille tarifaire.")
    assert odd["status"] == "inconsistent" and "2026-" in odd["summary"]
    future = match("JIRAMA, communiqué N° 2031-001 : nouvelle grille tarifaire.")
    assert future["status"] == "inconsistent" and "année à venir" in future["summary"]
    ministry = match("Le Ministère de la Santé publique annonce la fermeture des écoles.")
    assert ministry["status"] == "not_found" and ministry["issuer"].startswith(
        "Ministère de la Santé"
    )
    assert match("Il pleut fort sur Toamasina ce matin, restez prudents.")["status"] == "none"


def test_annuaire_institutions_count_as_issuers_and_veilleurs_cannot_match(as_user):
    alice, eve = as_user("alice"), as_user("eve")
    ws = _workspace(alice)
    invite(alice, ws, eve, "veilleur")
    contact = {"name": "Service de presse", "institution": "Office des ports (démo)"}
    assert alice.post(f"/api/v1/workspaces/{ws}/contacts", json=contact).status_code == 201
    found = alice.post(
        f"/api/v1/workspaces/{ws}/registry/match",
        json={"text": "L'Office des ports annonce la fermeture du quai."},
    ).json()
    assert found["status"] == "not_found" and found["issuer"] == "Office des ports"
    # The Annuaire says who at the issuer can confirm it.
    assert [c["name"] for c in found["contacts"]] == ["Service de presse"]
    blocked = eve.post(f"/api/v1/workspaces/{ws}/registry/match", json={"text": "N° 12 de la CENI"})
    assert blocked.status_code == 403


def test_a_private_newsrooms_fakes_are_never_counted_or_listed_elsewhere(as_user):
    alice, bob = as_user("alice"), as_user("bob")
    ws, other = _workspace(alice), _workspace(bob, "Private desk")
    cid = alice.post(f"/api/v1/workspaces/{ws}/registry", json=ORIGINAL).json()["id"]
    _public(alice, ws)
    # Bob's newsroom is not public: the fake it records stays inside it.
    mine = bob.post(f"/api/v1/workspaces/{other}/registry/{cid}/fake", json={"text": RUMOUR})
    assert mine.status_code == 201
    assert bob.get(f"/api/v1/workspaces/{other}/registry/{cid}").json()["fakes"] == 1
    assert alice.get(f"/api/v1/workspaces/{ws}/registry/{cid}").json()["fakes"] == 0
    assert alice.get(f"/api/v1/workspaces/{ws}/registry").json()[0]["fakes"] == 0
    assert alice.get(f"/api/v1/workspaces/{ws}/registry/{cid}/fakes").json() == []
    assert alice.get(f"/api/v1/workspaces/{ws}/registry/{mine.json()['id']}").status_code == 404
    # Once Bob's newsroom publishes, its fakes become part of the shared record.
    _public(bob, other)
    assert alice.get(f"/api/v1/workspaces/{ws}/registry/{cid}").json()["fakes"] == 1


def test_the_official_feed_shows_public_originals_and_fakes_only(as_user):
    alice, bob = as_user("alice"), as_user("bob")
    ws, other = _workspace(alice), _workspace(bob, "Private desk")
    cid = alice.post(f"/api/v1/workspaces/{ws}/registry", json=ORIGINAL).json()["id"]
    bob.post(f"/api/v1/workspaces/{other}/registry", json={**ORIGINAL, "title": "Hidden notice"})
    anyone = as_user("nobody")
    anyone.headers.pop("Authorization")
    assert anyone.get("/api/v1/public/registry").json() == {"items": [], "total": 0}
    _public(alice, ws)
    fake = alice.post(f"/api/v1/workspaces/{ws}/registry/{cid}/fake", json={"text": RUMOUR}).json()
    # A private newsroom's fake of a public original stays private.
    bob.post(f"/api/v1/workspaces/{other}/registry/{cid}/fake", json={"text": RUMOUR + " Vite"})
    feed = anyone.get("/api/v1/public/registry").json()
    assert feed["total"] == 2 and [i["id"] for i in feed["items"]] == [fake["id"], cid]
    caught, original = feed["items"]
    assert caught["kind"] == "fake_caught" and caught["original"]["id"] == cid
    assert caught["changed_numbers"] and caught["summary"].startswith("Le communiqué N° 2026-118")
    assert original["kind"] == "original" and original["fakes"] == 1
    assert original["newsroom"]["name"] == "Desk" and original["sealed"] is False
    only = anyone.get("/api/v1/public/registry", params={"kind": "original", "q": "délestage"})
    assert [i["id"] for i in only.json()["items"]] == [cid]
    assert anyone.get("/api/v1/public/registry", params={"newsroom": "nope"}).json()["total"] == 0


def test_the_demo_reset_seeds_the_sealed_original_its_fake_and_the_pitch_figures(
    as_user, monkeypatch
):
    from app.core.config import get_settings
    from app.modules.demo import DEMO_RUMOUR_TEXT

    monkeypatch.setattr(get_settings(), "seal_secret", "demo-seal-secret")
    alice = as_user("alice")
    ws = _workspace(alice)
    base = f"/api/v1/workspaces/{ws}"
    for _ in range(2):  # idempotent
        assert alice.post(f"{base}/demo/reset").status_code == 200
    entries = alice.get(f"{base}/registry").json()
    assert sorted(e["status"] for e in entries) == ["fake_caught", "original", "original"]
    jirama = next(e for e in entries if e["number"] == "2026-118")
    assert jirama["is_demo"] and jirama["sealed"] and jirama["issued_on"] == "2026-11-01"
    assert "(démo)" in jirama["title"]
    exam = next(e for e in entries if e["number"] == "2026-311" and e["status"] == "original")
    assert exam["fakes"] == 1 and exam["sealed"] is None

    found = alice.post(f"{base}/registry/match", json={"text": DEMO_RUMOUR_TEXT}).json()
    assert found["status"] == "modified" and found["communique"]["id"] == jirama["id"]
    assert {"kind": "duration", "original": "4 heures par jour", "submitted": "72 heures"} in found[
        "changed_numbers"
    ]
    numbers = alice.post(f"{base}/figures/check", json={"text": DEMO_RUMOUR_TEXT}).json()
    assert [(n["claimed"], n["verdict"], n["figure"]["value"]) for n in numbers] == [
        ("72 heures", "differs", "4"),
        ("40 %", "differs", "+12"),
    ]
    figures = alice.get(f"{base}/figures", params={"q": "Délestage"}).json()
    assert len(figures) == 1 and figures[0]["is_demo"]
    assert figures[0]["communique_id"] == jirama["id"]
    assert figures[0]["source_url"] == jirama["sealed"]["url"]
    # The public can check the demo seal: the demo newsroom publishes.
    public = alice.get(f"/api/v1/public/sceau/{jirama['id']}").json()
    assert public["is_demo"] and public["payload"]["number"] == "2026-118"
    feed = alice.get("/api/v1/public/registry").json()
    assert feed["total"] == 3 and any(i["kind"] == "fake_caught" for i in feed["items"])


def test_the_demo_still_seeds_without_a_seal_secret(as_user, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "seal_secret", "")
    alice = as_user("alice")
    ws = _workspace(alice)
    alice.post(f"/api/v1/workspaces/{ws}/demo/reset")
    jirama = alice.get(f"/api/v1/workspaces/{ws}/registry", params={"q": "2026-118"}).json()
    assert len(jirama) == 1 and jirama[0]["sealed"] is None
