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
