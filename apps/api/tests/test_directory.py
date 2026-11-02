import asyncio
import uuid

from sqlalchemy import select

from app.core.db import SessionLocal
from app.core.models import Contact, Job, Source
from app.modules import directory
from app.workers import queue
from tests.test_newsroom_resources import invite
from tests.test_workspaces import _workspace

JIRAMA = {
    "name": "Chargée de communication, JIRAMA (démo)",
    "kind": "officer",
    "institution": "JIRAMA",
    "role": "Relations presse",
    "topics": ["énergie"],
    "languages": ["fr", "mg"],
    "place": "Antananarivo",
    "phone": "+261 34 00 000 01",
    "email": "contact01@example.org",
    "official_pages": [{"kind": "site", "url": "https://www.jirama.mg"}],
}


def _contact(c, ws, **fields):
    r = c.post(f"/api/v1/workspaces/{ws}/contacts", json={**JIRAMA, **fields})
    assert r.status_code == 201, r.text
    return r.json()


def _claim(c, ws, title, **data):
    r = c.post(
        f"/api/v1/workspaces/{ws}/items", json={"title": title, "tags": ["énergie"], "data": data}
    )
    return r.json()["id"]


def test_contacts_carry_beats_places_languages_and_pages(as_user):
    alice, bob = as_user("alice"), as_user("bob")
    ws = _workspace(alice)
    invite(alice, ws, bob, "journalist")
    made = _contact(alice, ws)
    assert made["location"]["region"] == "Analamanga"
    assert made["official_pages"][0]["verified"] is False and made["own"] is True
    base = f"/api/v1/workspaces/{ws}/contacts"
    assert [c["name"] for c in alice.get(base, params={"topic": "énergie"}).json()] == [
        JIRAMA["name"]
    ]
    assert alice.get(base, params={"region": "Atsinanana"}).json() == []
    # Declared is not verified: no official host until an editor checked the page.

    async def hosts():
        async with SessionLocal() as db:
            return await directory.official_hosts(db, uuid.UUID(ws))

    assert asyncio.run(hosts()) == set()
    path = f"{base}/{made['id']}"
    assert bob.post(path + "/verify").status_code == 403
    assert alice.post(path + "/verify").json()["verified_at"]
    assert asyncio.run(hosts()) == {"jirama.mg"}
    # Editing channels drops the verification again.
    edited = alice.patch(path, json={"name": JIRAMA["name"], "phone": "+261 34 00 000 09"}).json()
    assert edited["verified_at"] is None and edited["phone"] == "+261 34 00 000 09"
    assert edited["topics"] == ["énergie"]  # a partial edit keeps the rest
    assert asyncio.run(hosts()) == set()
    assert alice.delete(path).status_code == 204


def test_who_matches_missing_points_to_the_best_placed_people(as_user):
    alice = as_user("alice")
    ws = _workspace(alice, "Rédaction démo")
    _contact(alice, ws)
    _contact(
        alice, ws, name="JIRAMA Toamasina (démo)", place="Toamasina", phone="+261 34 00 000 02"
    )
    _contact(alice, ws, name="INSTAT (démo)", institution="INSTAT", topics=["économie"], place=None)
    item = _claim(
        alice,
        ws,
        "72 heures de délestage dès demain sur tout Antananarivo, selon la JIRAMA",
        analysis={
            "missing": "Le communiqué original de la JIRAMA. La durée réelle des coupures prévues."
        },
    )
    out = alice.get(f"/api/v1/workspaces/{ws}/items/{item}/who").json()
    assert [p["point"] for p in out["points"]] == [
        "Le communiqué original de la JIRAMA.",
        "La durée réelle des coupures prévues.",
    ]
    best = out["points"][0]["contacts"]
    assert [c["contact"]["name"] for c in best] == [JIRAMA["name"], "JIRAMA Toamasina (démo)"]
    assert "énergie" in best[0]["why"] and "Analamanga" in best[0]["why"]
    assert "parle malgache" in best[0]["why"]
    assert best[0]["question"].startswith("Bonjour, ici la rédaction Rédaction démo.")
    assert "Confirmez-vous cette information ?" in best[0]["question"]
    assert out["place"]["region"] == "Analamanga" and "energie" in out["beats"]


def test_a_question_goes_out_as_links_and_comes_back_as_a_dated_source(
    as_user, client, monkeypatch
):
    alice = as_user("alice")
    ws = _workspace(alice)
    contact = _contact(alice, ws)
    item = _claim(alice, ws, "72 heures de délestage à Antananarivo, selon la JIRAMA")
    path = f"/api/v1/workspaces/{ws}/items/{item}/questions"
    sent = alice.post(
        path,
        json={
            "contact_id": contact["id"],
            "question": "Confirmez-vous ces 72 heures ?",
            "channel": "whatsapp",
        },
    )
    assert sent.status_code == 201
    q = sent.json()
    assert q["links"]["whatsapp"].startswith("https://wa.me/261340000001?text=Confirmez-vous")
    assert q["links"]["mailto"].startswith("mailto:contact01@example.org?subject=")
    assert "/reponse/" in q["message"]
    token = q["answer_url"].rsplit("/", 1)[1]

    page = client.get(f"/api/v1/public/reponse/{token}").json()
    assert page["claim"].startswith("72 heures") and page["answered_at"] is None
    assert page["institution"] == "JIRAMA"
    assert client.get("/api/v1/public/reponse/nope").status_code == 404

    answer = {
        "stance": "denies",
        "text": "Le communiqué prévoit 4 heures par jour.",
        "name": "Service presse",
    }
    done = client.post(f"/api/v1/public/reponse/{token}", json=answer)
    assert done.status_code == 200 and done.json()["stance"] == "denies"
    assert client.post(f"/api/v1/public/reponse/{token}", json=answer).status_code == 409

    async def check():
        async with SessionLocal() as db:
            source = await db.scalar(select(Source).where(Source.item_id == uuid.UUID(item)))
            row = await db.get(Contact, uuid.UUID(contact["id"]))
            jobs = list(await db.scalars(select(Job.kind)))
            return source, row.stats, jobs

    source, stats, jobs = asyncio.run(check())
    assert source.title == f"Réponse de {JIRAMA['name']} (JIRAMA)"
    assert source.text.startswith("Dément l'information.") and source.published_at
    assert stats["asked"] == 1 and stats["answered"] == 1 and "last_answer_hours" in stats
    assert "analyze_claim" in jobs
    listed = alice.get(path).json()
    assert listed[0]["answer"]["stance"] == "denies" and listed[0]["source_id"] == str(source.id)
    item_data = alice.get(f"/api/v1/workspaces/{ws}/items/{item}").json()["data"]
    assert item_data["source_count"] == 1
    actions = [
        a["action"] for a in alice.get(f"/api/v1/workspaces/{ws}/activity?entity_id={item}").json()
    ]
    assert "question" in actions and "answer" in actions


def test_without_ai_the_answer_is_kept_but_not_reread_and_reminders_skip_answered(as_user, client):
    alice = as_user("alice")
    ws = _workspace(alice)
    alice.patch(f"/api/v1/workspaces/{ws}", json={"settings": {"ai_enabled": False}})
    contact = _contact(alice, ws)
    item = _claim(alice, ws, "Délestage")
    q = alice.post(
        f"/api/v1/workspaces/{ws}/items/{item}/questions",
        json={"contact_id": contact["id"], "question": "Confirmez-vous ce délestage ?"},
    ).json()

    async def remind():
        async with SessionLocal() as db:
            await queue.enqueue(
                db, uuid.UUID(ws), "alice", "remind_question", {"request_id": q["id"]}
            )
        assert await queue.run_once()
        async with SessionLocal() as db:
            job = await db.scalar(
                select(Job).where(Job.kind == "remind_question").order_by(Job.created_at.desc())
            )
            return job.result

    assert asyncio.run(remind())["reminded"] is True
    token = q["answer_url"].rsplit("/", 1)[1]
    client.post(
        f"/api/v1/public/reponse/{token}", json={"stance": "confirms", "text": "Oui.", "name": "X"}
    )
    assert asyncio.run(remind()) == {"skipped": "answered"}

    async def kinds():
        async with SessionLocal() as db:
            return set(await db.scalars(select(Job.kind)))

    assert "analyze_claim" not in asyncio.run(kinds())


def test_other_newsrooms_cannot_ask_through_my_contacts(as_user):
    alice, bob = as_user("alice"), as_user("bob")
    ws, other = _workspace(alice), _workspace(bob)
    contact = _contact(alice, ws)
    item = _claim(bob, other, "Délestage")
    r = bob.post(
        f"/api/v1/workspaces/{other}/items/{item}/questions",
        json={"contact_id": contact["id"], "question": "Confirmez-vous ce délestage ?"},
    )
    assert r.status_code == 404
    # A contact the newsroom shares is readable by others, never editable by them.
    alice.patch(
        f"/api/v1/workspaces/{ws}/contacts/{contact['id']}",
        json={"name": contact["name"], "shared": True},
    )
    seen = bob.get(f"/api/v1/workspaces/{other}/contacts").json()
    assert [c["own"] for c in seen] == [False]
    assert (
        bob.patch(
            f"/api/v1/workspaces/{other}/contacts/{contact['id']}", json={"name": "x"}
        ).status_code
        == 404
    )


def test_demo_contacts_are_fictional_and_replaced_on_reset(as_user):
    alice = as_user("alice")
    ws = _workspace(alice)
    alice.post(f"/api/v1/workspaces/{ws}/demo/reset")
    alice.post(f"/api/v1/workspaces/{ws}/demo/reset")
    rows = alice.get(f"/api/v1/workspaces/{ws}/contacts").json()
    assert 10 <= len(rows) <= 15
    assert all(r["is_demo"] and "(démo)" in r["name"] for r in rows)
    assert all(r["phone"].startswith("+261 34 00 000 ") for r in rows)
    assert all(r["email"].endswith("@example.org") for r in rows)

    async def hosts():
        async with SessionLocal() as db:
            return await directory.official_hosts(db, uuid.UUID(ws))

    assert {"jirama.mg", "instat.mg", "bngrc.mg"} <= asyncio.run(hosts())
