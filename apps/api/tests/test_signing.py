import asyncio
import uuid

from sqlalchemy import select

from app.core.db import SessionLocal
from app.core.models import Route, Source
from app.modules.signing import rating_verdict
from tests.test_newsroom_resources import invite
from tests.test_workspaces import _workspace


def _claim(c, ws, title="72 heures de délestage à Antananarivo", **data):
    r = c.post(f"/api/v1/workspaces/{ws}/items", json={"title": title, "data": data})
    assert r.status_code == 201
    return r.json()["id"]


def _routes(item_id):
    async def run():
        async with SessionLocal() as db:
            return list(await db.scalars(select(Route).where(Route.item_id == uuid.UUID(item_id))))

    return asyncio.run(run())


def test_sign_and_publish_writes_the_byline_and_the_first_truth_stop(as_user):
    alice = as_user("alice")
    ws = _workspace(alice, "Rédaction démo")
    alice.patch(f"/api/v1/workspaces/{ws}", json={"is_public": True})
    item = _claim(alice, ws)
    path = f"/api/v1/workspaces/{ws}/items/{item}"
    out = alice.post(
        path + "/sign",
        json={
            "verdict": "false",
            "reason": "Le communiqué original dit 4 heures.",
            "publish": True,
        },
    ).json()
    assert out["status"] == "published"
    assert out["data"]["byline"]["newsroom"] == "Rédaction démo"
    assert out["data"]["byline"]["journalist"] == "Alice Rabe"
    assert out["data"]["published_by"] == "alice"
    stops = _routes(item)
    assert [(s.side, s.channel, s.place, s.status) for s in stops] == [
        ("truth", "web", "Page publique", "broadcast")
    ]
    # Signing again does not draw a second « Page publique ».
    alice.post(
        path + "/sign",
        json={
            "verdict": "false",
            "reason": "Le communiqué original dit 4 heures.",
            "publish": True,
        },
    )
    assert len(_routes(item)) == 1
    # The byline cannot be forged through PATCH.
    assert alice.patch(path, json={"data": {"byline": {"newsroom": "x"}}}).status_code == 422
    actions = [
        a["action"] for a in alice.get(f"/api/v1/workspaces/{ws}/activity?entity_id={item}").json()
    ]
    assert "sign" in actions


def test_private_newsroom_publishes_without_a_public_page_stop(as_user):
    alice = as_user("alice")
    ws = _workspace(alice)
    item = _claim(alice, ws)
    alice.post(
        f"/api/v1/workspaces/{ws}/items/{item}/sign",
        json={"verdict": "true", "reason": "Le relevé officiel le confirme.", "publish": True},
    )
    assert _routes(item) == []


def test_double_signature_needs_another_editor_to_release(as_user):
    alice, bob = as_user("alice"), as_user("bob")
    ws = _workspace(alice)
    invite(alice, ws, bob, "editor")
    alice.patch(f"/api/v1/workspaces/{ws}", json={"settings": {"double_signature": True}})
    item = _claim(alice, ws)
    path = f"/api/v1/workspaces/{ws}/items/{item}"
    assert bob.post(path + "/release").status_code == 409  # nothing signed yet
    signed = alice.post(
        path + "/sign",
        json={
            "verdict": "false",
            "reason": "Le communiqué original dit 4 heures.",
            "publish": True,
        },
    ).json()
    assert signed["status"] == "verified"
    assert alice.post(path + "/release").json()["error"]["code"] == "second_signer_required"
    released = bob.post(path + "/release")
    assert released.status_code == 200 and released.json()["status"] == "published"
    assert released.json()["data"]["published_by"] == "bob"
    assert bob.post(path + "/release").json()["error"]["code"] == "already_published"


def test_batch_signs_suggestions_with_their_reason_and_says_why_others_wait(as_user):
    alice, carol = as_user("alice"), as_user("carol")
    ws = _workspace(alice)
    invite(alice, ws, carol, "journalist")
    base = f"/api/v1/workspaces/{ws}"
    ready = _claim(
        alice,
        ws,
        verdict_suggested="false",
        analysis={"reason": "Le communiqué N° 2026-118 annonce 4 heures par jour."},
    )
    no_reason = _claim(alice, ws, "Le bac est reporté", verdict_suggested="unverifiable")
    no_verdict = _claim(alice, ws, "Le pont est fermé")
    out = alice.post(
        base + "/items/sign", json={"ids": [ready, no_reason, no_verdict, str(uuid.uuid4())]}
    ).json()
    assert [i["id"] for i in out["signed"]] == [ready]
    assert out["signed"][0]["data"]["verdict"] == "false"
    assert out["signed"][0]["data"]["reason"].startswith("Le communiqué N° 2026-118")
    assert {s["code"] for s in out["skipped"]} == {"missing_reason", "no_verdict", "not_found"}
    # Signed already: a second batch leaves it alone. A journalist cannot sign others' dossiers.
    again = alice.post(base + "/items/sign", json={"ids": [ready]}).json()
    assert again["skipped"][0]["code"] == "already_signed"
    other = _claim(alice, ws, "Autre", verdict="true", reason="Une raison assez longue.")
    assert carol.post(base + "/items/sign", json={"ids": [other]}).json()["skipped"][0]["code"] == (
        "forbidden"
    )
    assert alice.post(base + "/items/sign", json={"ids": []}).status_code == 422


def test_adopt_relays_a_fact_checkers_review_as_source_one(as_user):
    alice = as_user("alice")
    ws = _workspace(alice, "Desk")
    item = _claim(alice, ws, "Madagascar a quitté l'OMS")
    path = f"/api/v1/workspaces/{ws}/items/{item}/adopt"
    review = {
        "publisher": "AFP Factuel",
        "url": "https://factuel.afp.com/exemple",
        "rating": "Faux",
        "date": "2026-10-30",
        "title": "Non, Madagascar n'a pas quitté l'OMS",
    }
    out = alice.post(path, json={"review": review, "publish": True}).json()
    assert out["data"]["verdict"] == "false" and out["status"] == "published"
    assert "AFP Factuel" in out["data"]["reason"] and "[1]" in out["data"]["reason"]
    assert out["data"]["adopted"]["publisher"] == "AFP Factuel"
    assert out["data"]["source_count"] == 1

    async def sources():
        async with SessionLocal() as db:
            return list(await db.scalars(select(Source).where(Source.item_id == uuid.UUID(item))))

    (source,) = asyncio.run(sources())
    assert source.url == "https://factuel.afp.com/exemple" and source.published_at == "2026-10-30"
    assert "30 octobre 2026" in source.text
    unclear = {"review": {**review, "rating": "Satirique"}}
    bad = alice.post(path, json=unclear)
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "unknown_rating"
    # The journalist picks the verdict for an unclear rating; by default it is signed, not published.
    other = _claim(alice, ws, "Une autre rumeur")
    chosen = alice.post(
        f"/api/v1/workspaces/{ws}/items/{other}/adopt", json={**unclear, "verdict": "misleading"}
    ).json()
    assert chosen["data"]["verdict"] == "misleading" and chosen["status"] == "verified"


def test_ratings_map_to_our_four_verdicts_on_whole_words():
    assert rating_verdict("Inaccurate") == "false"
    assert rating_verdict("Not true") == "false"
    assert rating_verdict("Not correct") == "false"
    assert rating_verdict("Mostly false") == "false"
    assert rating_verdict("Pants on Fire!") == "false"
    assert rating_verdict("Faux") == "false"
    assert rating_verdict("Partly false") == "misleading"
    assert rating_verdict("Half True") == "misleading"
    assert rating_verdict("Trompeur") == "misleading"
    assert rating_verdict("Missing context") == "misleading"
    assert rating_verdict("Non prouvé") == "unverifiable"
    assert rating_verdict("Mostly True") == "true"
    assert rating_verdict("Vrai") == "true"
    assert rating_verdict("Faux et trompeur") is None
    assert rating_verdict("Satirique") is None


def test_the_desk_sees_how_a_rating_is_read_before_signing(as_user):
    alice = as_user("alice")
    ws = _workspace(alice)
    url = f"/api/v1/workspaces/{ws}/ratings"
    assert alice.get(url, params={"rating": "Inaccurate"}).json() == {
        "rating": "Inaccurate",
        "verdict": "false",
    }
    assert alice.get(url, params={"rating": "Satire"}).json()["verdict"] is None
    assert as_user("bob").get(url, params={"rating": "Faux"}).status_code == 404


def test_carnet_lists_the_diligence_and_the_attestation_verifies(as_user, client, monkeypatch):
    from app.core.config import get_settings

    alice = as_user("alice")
    ws = _workspace(alice, "Rédaction démo")
    alice.patch(f"/api/v1/workspaces/{ws}", json={"is_public": True})
    item = _claim(alice, ws, ref="FAN-0145")
    base = f"/api/v1/workspaces/{ws}/items/{item}"
    alice.post(
        f"/api/v1/workspaces/{ws}/sources",
        json={
            "text": "Le communiqué dit 4 heures.",
            "title": "Communiqué N° 2026-118",
            "item_id": item,
        },
    )
    contact = alice.post(
        f"/api/v1/workspaces/{ws}/contacts", json={"name": "JIRAMA (démo)", "institution": "JIRAMA"}
    ).json()
    alice.post(
        base + "/questions", json={"contact_id": contact["id"], "question": "Confirmez-vous ?"}
    )
    assert alice.get(base + "/attestation").json()["error"]["code"] == "not_signed"
    alice.post(
        base + "/sign",
        json={
            "verdict": "false",
            "reason": "Le communiqué original dit 4 heures.",
            "publish": True,
        },
    )
    book = alice.get(base + "/carnet").json()
    texts = [e["text"] for e in book["entries"]]
    assert texts[0] == "Dossier ouvert"
    assert "Source ajoutée : Communiqué N° 2026-118" in texts
    assert "Question envoyée à JIRAMA (démo) (WhatsApp)" in texts
    assert "Verdict signé : Faux et publié" in texts
    assert "Correction envoyée : Web · Page publique" in texts
    assert book["sources"][0]["added_by"] == "Alice Rabe"
    assert book["questions"][0]["answered_at"] is None and book["routes"]["truth"] == 1

    monkeypatch.setattr(get_settings(), "seal_secret", "")
    assert alice.get(base + "/attestation").json()["error"]["code"] == "attestation_unavailable"
    monkeypatch.setattr(get_settings(), "seal_secret", "a long random test secret")
    att = alice.get(base + "/attestation").json()
    assert att["summary"].startswith("Rédaction démo atteste avoir vérifié")
    assert "1 source au dossier, 1 question envoyée et 0 réponse reçue" in att["summary"]
    assert att["summary"].endswith("par Alice Rabe : Faux.")
    ok = client.post(
        "/api/v1/public/attestations/verify",
        json={"payload": att["payload"], "signature": att["signature"]},
    ).json()
    assert ok["valid"] is True and ok["sha256"] == att["sha256"] and ok["key_id"] == att["key_id"]
    forged = client.post(
        "/api/v1/public/attestations/verify",
        json={"payload": {**att["payload"], "verdict": "true"}, "signature": att["signature"]},
    ).json()
    assert forged["valid"] is False and forged["summary"] is None
    assert as_user("bob").get(base + "/carnet").status_code == 404
