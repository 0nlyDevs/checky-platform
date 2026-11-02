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
    out = alice.post(path, json={"review": review}).json()
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
    bad = alice.post(path, json={"review": {**review, "rating": "Satirique"}})
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "unknown_rating"


def test_ratings_map_to_our_four_verdicts():
    assert rating_verdict("Partly false") == "misleading"
    assert rating_verdict("Trompeur") == "misleading"
    assert rating_verdict("Pants on Fire") == "false"
    assert rating_verdict("Faux") == "false"
    assert rating_verdict("Incorrect") == "false"
    assert rating_verdict("Mostly True") == "true"
    assert rating_verdict("Vrai") == "true"
    assert rating_verdict("Non prouvé") == "unverifiable"
    assert rating_verdict("Sans objet") is None
