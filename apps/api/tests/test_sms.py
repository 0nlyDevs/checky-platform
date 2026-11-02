"""The SMS line: keywords, verdict replies in the sender's language, tips, and the outbox."""

import json

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app

CLAIM = "72 heures de délestage dès demain sur tout Antananarivo, selon la JIRAMA"
RUMOUR = "délestage de 72 heures sur tout Antananarivo selon la JIRAMA, partagez !"
# Never sent anywhere: the test outbox stops at the API.
PHONE = "+261 32 99 999 91"
GW = {"X-Gateway-Secret": "gw-test-secret"}
from tests.test_workspaces import _verify


@pytest.fixture(autouse=True)
def secrets(monkeypatch):
    monkeypatch.setattr(get_settings(), "sms_gateway_secret", "gw-test-secret")
    monkeypatch.setattr(get_settings(), "seal_secret", "test-seal-secret-for-contacts")
    monkeypatch.setattr(get_settings(), "public_web_url", "https://checky.example")


def _newsroom(c, name="Desk du matin", **settings):
    ws = c.post("/api/v1/workspaces", json={"name": name}).json()["id"]
    c.patch(f"/api/v1/workspaces/{ws}", json={"is_public": True, "settings": settings})
    _verify(ws)
    return ws


def _claim(c, ws, title, status="published", verdict="false", ref="FAN-0145", **data):
    data = {"ref": ref, **({"verdict": verdict} if verdict else {}), **data}
    r = c.post(
        f"/api/v1/workspaces/{ws}/items", json={"title": title, "status": status, "data": data}
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def sms(text, sender=PHONE, headers=GW):
    return TestClient(app).post(
        "/api/v1/public/sms/inbound", json={"from": sender, "text": text}, headers=headers
    )


def test_the_line_needs_its_gateway_secret(monkeypatch):
    assert sms("bonjour", headers={"X-Gateway-Secret": "nope"}).status_code == 401
    assert sms("bonjour", headers={}).status_code == 401
    monkeypatch.setattr(get_settings(), "sms_gateway_secret", "")
    assert sms("bonjour").status_code == 503
    assert TestClient(app).get("/api/v1/public/sms/outbox", headers=GW).status_code == 503


def test_a_published_verdict_comes_back_in_the_senders_language(as_user):
    alice = as_user("alice")
    ws = _newsroom(alice)
    item = _claim(
        alice, ws, CLAIM, reason="Le communiqué annonce 4 heures par jour. Il date du 1er novembre."
    )
    r = sms(RUMOUR)
    out = r.json()
    assert r.status_code == 200 and out["action"] == "verdict" and out["verdict_id"] == item
    assert out["reply"] == (
        "Faux — 72 heures de délestage dès demain sur tout Antananarivo, selon la JIRAMA. "
        "Le communiqué annonce 4 heures par jour. https://checky.example/v/145"
    )
    assert out["masked"] == "+261 32 •• ••• 91" and len(out["phone_hash"]) == 64
    mg = sms("Marina ve fa 72 heures delestage eto Antananarivo hono ny JIRAMA ?").json()
    assert mg["language"] == "mg" and mg["reply"].startswith("Diso — 72 heures")
    # the gateway takes the replies once, then they are sent
    box = TestClient(app).get("/api/v1/public/sms/outbox", headers=GW).json()
    assert [m["text"][:4] for m in box] == ["Faux", "Diso"]
    assert box[0]["masked"] == "+261 32 •• ••• 91" and box[0]["to"] is None
    assert TestClient(app).get("/api/v1/public/sms/outbox", headers=GW).json() == []


def test_an_unknown_rumour_becomes_a_tip_with_its_road(as_user, monkeypatch):
    from app.modules import trajet

    stops = []

    async def add_stop(db, workspace_id, item_id, **kw):
        stops.append(kw)

    monkeypatch.setattr(trajet, "add_stop", add_stop, raising=False)
    alice = as_user("alice")
    _newsroom(alice, name="Premier desk")
    toliara = _newsroom(alice, name="Desk du Sud", region="Atsimo-Andrefana")
    out = sms("Le pont de Toliara est coupé, appelez le 034 12 345 67 pour les détails").json()
    assert out["action"] == "received"
    assert out["reply"] == "Reçu. Une rédaction va vérifier. Vous recevrez la réponse par SMS."
    # it reached the newsroom of its region, with the number typed in it masked
    items = alice.get(f"/api/v1/workspaces/{toliara}/items").json()["items"]
    assert len(items) == 1
    tip = items[0]
    assert tip["status"] == "to_check" and tip["data"]["sms"] is True
    assert "345 67" not in json.dumps(tip) and "[contact masqué]" in tip["body"]
    assert tip["data"]["location"]["region"] == "Atsimo-Andrefana"
    assert stops == [
        {
            "side": "rumour",
            "channel": "sms",
            "place": "SMS",
            "location": tip["data"]["location"],
        }
    ]
    groups = alice.get(f"/api/v1/workspaces/{toliara}/questions").json()
    assert groups[0]["channels"] == {"sms": 1} and groups[0]["waiting"] == 1


def test_a_rumour_a_newsroom_follows_joins_its_claim(as_user):
    alice = as_user("alice")
    ws = _newsroom(alice)
    item = _claim(alice, ws, CLAIM, status="to_check", verdict=None)
    out = sms(f"CHECKY {CLAIM}").json()
    assert out["action"] == "followed" and out["verdict_id"] is None
    assert alice.get(f"/api/v1/workspaces/{ws}/items").json()["total"] == 1
    groups = alice.get(f"/api/v1/workspaces/{ws}/questions").json()
    assert groups[0]["item_id"] == item and groups[0]["count"] == 1


def test_subscribe_stop_help_and_the_daily_limit():
    out = sms("ABONNE Toliara").json()
    assert out["action"] == "subscribed" and "Atsimo-Andrefana" in out["reply"]
    assert sms("STOP").json()["action"] == "stopped"
    assert sms("AIDE").json()["action"] == "help"
    assert sms("ok").json()["action"] == "help"
    nobody = sms("Le prix du riz a doublé à Antananarivo").json()
    assert nobody["reply"] == "Reçu. Aucune rédaction ne reçoit de SMS pour l'instant."
    r = sms("encore une question sur le riz")
    assert r.status_code == 429 and r.json()["error"]["code"] == "too_many_sms"


def _publish(c, ws, item):
    r = c.patch(f"/api/v1/workspaces/{ws}/items/{item}", json={"status": "published"})
    assert r.status_code == 200, r.text


async def _notify(item_id):
    from app.core.db import SessionLocal
    from app.core.models import Item
    from app.modules.sms import notify_signed

    async with SessionLocal() as db:
        return await notify_signed(db, await db.get(Item, item_id))


def test_a_signed_verdict_goes_back_to_askers_and_the_regions_it_crossed(as_user):
    import asyncio

    from app.core.db import SessionLocal
    from app.core.models import Route

    alice = as_user("alice")
    ws = _newsroom(alice)
    item = _claim(alice, ws, CLAIM, status="verified", verdict="false", reason="Quatre heures.")
    assert sms(f"CHECKY {CLAIM}").json()["action"] == "followed"  # an asker by SMS
    assert sms("ABONNE Toliara", sender="+261 32 99 999 92").json()["action"] == "subscribed"
    assert sms("ABONNE Toamasina", sender="+261 32 99 999 93").json()["action"] == "subscribed"
    r = TestClient(app).post(
        "/api/v1/public/notify",
        json={"text": CLAIM, "contact": "asker@example.org", "item_id": item},
    )
    assert r.status_code == 201

    async def road():
        async with SessionLocal() as db:
            db.add(
                Route(
                    workspace_id=ws,
                    item_id=item,
                    added_by="alice",
                    side="rumour",
                    channel="whatsapp",
                    location={"name": "Toliara", "region": "Atsimo-Andrefana"},
                )
            )
            await db.commit()

    asyncio.run(road())
    TestClient(app).get("/api/v1/public/sms/outbox", headers=GW)  # the earlier replies leave
    assert asyncio.run(_notify(item)) == 0  # signed is not published: nothing leaves yet
    _publish(alice, ws, item)
    # the SMS asker and the Toliara subscriber; not Toamasina, and not the e-mail asker
    assert asyncio.run(_notify(item)) == 2
    assert asyncio.run(_notify(item)) == 0  # once per number
    box = TestClient(app).get("/api/v1/public/sms/outbox", headers=GW).json()
    assert {m["masked"] for m in box} == {"+261 32 •• ••• 91", "+261 32 •• ••• 92"}
    assert all(m["text"].startswith("Faux — 72 heures") for m in box)
    groups = alice.get(f"/api/v1/workspaces/{ws}/questions").json()
    assert groups[0]["waiting"] == 1  # the e-mail asker: no mail service yet


def test_a_number_left_on_the_site_is_handed_to_the_gateway(as_user):
    import asyncio

    alice = as_user("alice")
    ws = _newsroom(alice)
    item = _claim(alice, ws, CLAIM, status="to_check", verdict=None)
    body = {"text": CLAIM, "contact": "032 99 999 94", "item_id": item}
    assert TestClient(app).post("/api/v1/public/notify", json=body).status_code == 201
    alice.patch(
        f"/api/v1/workspaces/{ws}/items/{item}",
        json={"status": "published", "data": {"verdict": "false"}},
    )
    assert asyncio.run(_notify(item)) == 1
    box = TestClient(app).get("/api/v1/public/sms/outbox", headers=GW).json()
    assert [m["to"] for m in box] == ["+261329999994"]


def test_the_simulator_answers_from_a_fictional_number_and_never_sends(as_user, monkeypatch):
    alice, bob = as_user("alice"), as_user("bob")
    ws = _newsroom(alice)
    item = _claim(alice, ws, CLAIM, reason="Le communiqué annonce 4 heures par jour.")
    url = f"/api/v1/workspaces/{ws}/sms/simulate"
    out = alice.post(url, json={"text": RUMOUR}).json()
    assert out["inbound"]["action"] == "verdict" and out["inbound"]["verdict_id"] == item
    assert out["inbound"]["masked"] == "+261 34 •• ••• 09"
    assert [m["status"] for m in out["replies"]] == ["simulated"]
    assert out["replies"][0]["text"].startswith("Faux — ")
    for _ in range(6):  # rehearsals are not limited
        assert alice.post(url, json={"text": "AIDE"}).status_code == 200
    # the gateway never receives what was written to the fictional block
    assert TestClient(app).get("/api/v1/public/sms/outbox", headers=GW).json() == []
    real = {"from": "+261 32 99 999 95", "text": "AIDE"}
    assert alice.post(url, json=real).json()["error"]["code"] == "fictional_only"
    log = alice.get(f"/api/v1/workspaces/{ws}/sms/messages").json()
    assert {m["direction"] for m in log} == {"in", "out"}
    # any journalist of the newsroom, nobody else
    assert bob.post(url, json={"text": "AIDE"}).status_code == 404
    monkeypatch.setattr(get_settings(), "sms_gateway_secret", "")
    assert alice.post(url, json={"text": "AIDE"}).status_code == 503


def test_demo_reset_seeds_the_line_twice_without_duplicates(as_user):
    import asyncio

    alice = as_user("alice")
    ws = alice.post("/api/v1/workspaces", json={"name": "Démo"}).json()["id"]
    for _ in range(2):
        assert alice.post(f"/api/v1/workspaces/{ws}/demo/reset").status_code == 200
    radios = alice.get(f"/api/v1/workspaces/{ws}/radios").json()
    assert [r["name"] for r in radios] == ["Radio Fanambarana (démo)"] and radios[0]["is_demo"]
    groups = alice.get(f"/api/v1/workspaces/{ws}/questions").json()
    rumour = next(g for g in groups if g["item_ref"] == "FAN-0145")
    assert rumour["count"] == 4 and rumour["regions"]["Atsimo-Andrefana"] == 3
    assert rumour["channels"] == {"sms": 3, "web": 1}
    # publishing the pitch rumour texts the askers and the subscribers of the regions its demo
    # road crosses (Antananarivo's radio, then SMS from Atsimo-Andrefana)
    item = rumour["item_id"]
    _verify(ws)  # the demo reset never verifies a newsroom: only the Checky team does
    alice.patch(
        f"/api/v1/workspaces/{ws}/items/{item}",
        json={"status": "published", "data": {"verdict": "false", "reason": "Quatre heures."}},
    )
    assert asyncio.run(_notify(item)) == 6  # 4 askers + the 2 demo subscribers on the road
    assert asyncio.run(_notify(item)) == 0  # once per number
    log = alice.get(f"/api/v1/workspaces/{ws}/sms/messages").json()
    assert {m["status"] for m in log} == {"simulated"}  # fictional numbers: never sent
