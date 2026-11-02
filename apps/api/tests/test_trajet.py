import asyncio
import uuid
from datetime import UTC, datetime, timedelta

from app.core.db import SessionLocal
from app.core.models import Item
from app.modules import trajet
from tests.ref_fixture import set_ref
from tests.test_workspaces import _verify, _workspace


def _claim(c, ws, **data):
    ref = data.pop("ref", None)
    r = c.post(
        f"/api/v1/workspaces/{ws}/items",
        json={"title": "72 heures de délestage à Antananarivo", "data": data},
    )
    assert r.status_code == 201
    item_id = r.json()["id"]
    if ref:
        set_ref(item_id, ref)
    return item_id


def _data(item_id):
    async def run():
        async with SessionLocal() as db:
            return (await db.get(Item, uuid.UUID(item_id))).data

    return asyncio.run(run())


def _stop(ws, item_id, **kw):
    async def run():
        async with SessionLocal() as db:
            route = await trajet.add_stop(db, uuid.UUID(ws), uuid.UUID(item_id), **kw)
            await db.commit()
            return route.id

    return asyncio.run(run())


def test_add_stop_counts_repeats_and_gaps_follow_channel_and_region(as_user):
    alice = as_user("alice")
    ws = _workspace(alice)
    item = _claim(alice, ws)
    base = f"/api/v1/workspaces/{ws}/items/{item}"
    _stop(ws, item, side="rumour", channel="facebook", place="Page « Tana Flash » (démo)")
    _stop(ws, item, side="rumour", channel="radio", place="Radio RDJ", location=None)
    first = _stop(ws, item, side="rumour", channel="sms", place="SMS Toliara")
    again = _stop(ws, item, side="rumour", channel="sms", place="SMS Toliara")
    assert first == again  # three SMS from one region are one stop « × n »
    out = alice.get(base + "/trajet").json()
    assert [s["channel"] for s in out["rumour"]] == ["facebook", "radio", "sms"]
    sms = out["rumour"][2]
    assert sms["proof"]["count"] == 2
    assert sms["location"]["region"] == "Atsimo-Andrefana"  # gazetteer from the place's words
    assert len(out["gaps"]) == 3 and out["covered"] == 0
    assert out["summary"] == "La rumeur est passée par 3 routes ; la vérité n'en a repris aucune."

    # A correction on the radio of another region does not cover it; a national one does.
    _stop(ws, item, side="truth", channel="sms", place="SMS Toamasina")
    _stop(ws, item, side="truth", channel="radio", place="Flash national", location={})
    out = alice.get(base + "/trajet").json()
    assert {g["channel"] for g in out["gaps"]} == {"facebook", "sms"}
    assert out["summary"] == "La rumeur est passée par 3 routes ; la vérité en a repris 1."
    assert [s["status"] for s in out["truth"]] == ["sent", "sent"]


def test_origin_and_first_seen_make_the_first_stop_when_none_is_noted(as_user):
    alice = as_user("alice")
    ws = _workspace(alice)
    seen = (datetime.now(UTC) - timedelta(hours=3)).isoformat()
    item = _claim(alice, ws, origin="whatsapp", first_seen_at=seen)
    out = alice.get(f"/api/v1/workspaces/{ws}/items/{item}/trajet").json()
    assert out["rumour"][0]["derived"] is True and out["rumour"][0]["channel"] == "whatsapp"
    assert out["summary"].startswith("La rumeur est passée par 1 route ;")
    assert as_user("bob").get(f"/api/v1/workspaces/{ws}/items/{item}/trajet").status_code == 404


def test_hand_entered_route_needs_a_past_time_and_a_published_verdict_for_truth(as_user):
    alice = as_user("alice")
    ws = _workspace(alice)
    item = _claim(alice, ws)
    path = f"/api/v1/workspaces/{ws}/items/{item}/routes"
    at = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()
    row = {"side": "rumour", "channel": "tiktok", "place": "Compte TikTok", "note": "Vu ce matin"}
    assert alice.post(path, json={**row, "at": at}).status_code == 201
    future = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    assert alice.post(path, json={**row, "at": future}).status_code == 422
    assert alice.post(path, json={**row, "side": "truth", "at": at}).status_code == 409
    assert [r["status"] for r in alice.get(path).json()] == ["reported"]


def test_public_trajet_shows_the_truth_side_of_published_verdicts_only(as_user, client):
    alice = as_user("alice")
    ws = _workspace(alice)
    item = _claim(alice, ws)
    _stop(ws, item, side="rumour", channel="facebook", place="Page")
    assert client.get(f"/api/v1/public/verdicts/{item}/trajet").status_code == 404
    alice.patch(f"/api/v1/workspaces/{ws}", json={"is_public": True})
    _verify(ws)
    alice.post(
        f"/api/v1/workspaces/{ws}/items/{item}/sign",
        json={
            "verdict": "false",
            "reason": "Le communiqué original dit 4 heures.",
            "publish": True,
        },
    )
    out = client.get(f"/api/v1/public/verdicts/{item}/trajet").json()
    assert out["rumour_routes"] == 1
    assert all("proof" not in s for s in out["truth"])


def test_demo_seed_draws_the_pitch_rumours_road(as_user):
    alice = as_user("alice")
    ws = _workspace(alice)
    assert alice.post(f"/api/v1/workspaces/{ws}/demo/reset").status_code == 200

    async def find():
        async with SessionLocal() as db:
            from sqlalchemy import select

            return await db.scalar(select(Item).where(Item.data["ref"].astext == "FAN-0145"))

    item = asyncio.run(find())
    out = alice.get(f"/api/v1/workspaces/{ws}/items/{item.id}/trajet").json()
    assert [s["channel"] for s in out["rumour"]] == ["facebook", "whatsapp", "radio", "sms"]
    assert out["rumour"][3]["proof"]["count"] == 3
    first = datetime.fromisoformat(out["rumour"][0]["at"])
    assert first == datetime.fromisoformat(item.data["first_seen_at"])
    # Running the seed again replaces the stops instead of doubling them.
    assert alice.post(f"/api/v1/workspaces/{ws}/demo/reset").status_code == 200
    item = asyncio.run(find())
    assert len(alice.get(f"/api/v1/workspaces/{ws}/items/{item.id}/trajet").json()["rumour"]) == 4


def test_public_trajet_hides_a_published_claim_without_a_confirmed_verdict(as_user, client):
    alice = as_user("alice")
    ws = _workspace(alice)
    alice.patch(f"/api/v1/workspaces/{ws}", json={"is_public": True})
    _verify(ws)
    item = _claim(alice, ws, verdict_suggested="false")

    async def force_published():
        async with SessionLocal() as db:
            row = await db.get(Item, uuid.UUID(item))
            row.status = "published"  # as an older route could leave it, with no verdict
            await db.commit()

    asyncio.run(force_published())
    assert client.get(f"/api/v1/public/verdicts/{item}/trajet").status_code == 404


# --- Diffuser -------------------------------------------------------------------------------

import json

import httpx
import pytest

from app.core import ai
from app.core.config import get_settings
from app.core.models import RadioPartner

REASON = "Le communiqué N° 2026-118 de la JIRAMA prévoit 4 heures par jour, pas 72 heures."


@pytest.fixture
def model(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "llm_providers", "groq")
    monkeypatch.setattr(s, "groq_api_key", "k")
    monkeypatch.setattr(s, "ai_cache", False)
    monkeypatch.setattr(s, "public_web_url", "https://checky.example")
    trajet._WRITTEN.clear()
    calls = []
    reply = {
        "radio_line": "La rédaction a vérifié : les 72 heures de délestage sont fausses, le communiqué dit 4 heures.",
        "flash": " ".join(["Flash"] + ["mot"] * 70),
        "sms": "FAUX : pas 72 heures de délestage, 4 heures par jour selon la JIRAMA.",
        # An invented figure: the template replaces this field.
        "text": "Faux. Plus de 300 000 foyers ont partagé ce message.",
        "institution_alert": "Bonjour, nous avons publié une vérification sur le délestage.",
        "mg": {"sms": "DISO : tsy 72 ora ny fahatapahan-jiro.", "text": "Diso ity vaovao ity."},
    }

    def handler(request):
        calls.append(json.loads(request.content))
        msg = {"role": "assistant", "content": json.dumps(reply, ensure_ascii=False)}
        return httpx.Response(200, json={"model": "m", "choices": [{"message": msg}]})

    monkeypatch.setattr(ai, "_transport", httpx.MockTransport(handler))
    return calls


def _published(alice, ws, **data):
    alice.patch(f"/api/v1/workspaces/{ws}", json={"is_public": True})
    _verify(ws)
    seen = (datetime.now(UTC) - timedelta(hours=8)).isoformat()
    item = _claim(alice, ws, ref="FAN-0145", origin="facebook", first_seen_at=seen, **data)
    r = alice.post(
        f"/api/v1/workspaces/{ws}/items/{item}/sign",
        json={"verdict": "false", "reason": REASON, "publish": True},
    )
    assert r.status_code == 200
    return item


def test_diffusion_needs_a_published_public_verdict(as_user, model):
    alice = as_user("alice")
    ws = _workspace(alice)
    item = _claim(alice, ws)
    path = f"/api/v1/workspaces/{ws}/items/{item}/diffusion"
    assert alice.get(path).json()["error"]["code"] == "not_published"
    alice.post(
        f"/api/v1/workspaces/{ws}/items/{item}/sign",
        json={"verdict": "false", "reason": REASON, "publish": True},
    )
    assert alice.get(path).json()["error"]["code"] == "not_verified"
    _verify(ws)
    assert alice.get(path).json()["error"]["code"] == "private_workspace"
    assert model == []


def test_formats_come_from_one_model_call_and_invented_numbers_fall_back(as_user, model):
    alice = as_user("alice")
    ws = _workspace(alice, "Rédaction démo")
    item = _published(alice, ws)
    path = f"/api/v1/workspaces/{ws}/items/{item}/diffusion"
    out = alice.get(path).json()
    assert out["written_by"] == "ai" and len(model) == 1
    assert out["short_link"] == "https://checky.example/v/145"
    assert out["permalink"] == f"https://checky.example/verifies/{item}"
    assert out["sms"].endswith(" https://checky.example/v/145") and len(out["sms"]) <= 160
    assert out["radio_line"].startswith("La rédaction a vérifié")
    assert "300 000" not in out["text"] and out["text"].startswith("Faux · Rédaction démo")
    assert out["flash"].startswith("Flash mot")  # 71 words: within the flash's length
    assert out["mg"]["sms"].startswith("DISO") and out["mg"]["text"] == "Diso ity vaovao ity."
    assert out["poster"]["verdict_word"] == "Faux" and out["poster"]["qr_url"] == out["permalink"]
    assert out["poster"]["date"]
    assert [g["channel"] for g in out["gaps"]] == ["facebook"]
    # Opening the panel again costs no second call.
    alice.get(path)
    assert len(model) == 1
    # « Mode sans IA »: the templates, never the model's text.
    alice.patch(f"/api/v1/workspaces/{ws}", json={"settings": {"ai_enabled": False}})
    off = alice.get(path).json()
    assert off["written_by"] == "template" and off["mg"] is None and len(model) == 1
    assert off["sms"].startswith("FAUX : ")
    # One verification number everywhere, written the same way.
    assert off["sms"].endswith("(vérification 145) https://checky.example/v/145")
    assert len(off["sms"]) <= 160
    assert "C'est la vérification 145, sur checky.example/v/145." in off["radio_line"]
    assert "vérification 145" in off["flash"] and "Vérification 145 : " in off["text"]
    # The model's lines get the number from code when they leave it out.
    assert out["radio_line"].endswith("(vérification 145)")
    assert "(vérification 145)" in out["sms"] and "(fanamarinana 145)" in out["mg"]["sms"]


def test_diffuse_draws_truth_stops_and_keeps_malagasy_until_reread(as_user, model):
    alice = as_user("alice")
    ws = _workspace(alice)
    item = _published(alice, ws)
    _stop(ws, item, side="rumour", channel="radio", place="Radio RDJ, Antananarivo")
    path = f"/api/v1/workspaces/{ws}/items/{item}/diffuse"
    body = {
        "routes": [
            {"channel": "radio", "place": "Radio RDJ, Antananarivo"},
            {"channel": "sms", "place": "Abonnés SMS Atsimo-Andrefana"},
        ],
        "formats": ["radio_line", "sms", "sms_mg"],
    }
    out = alice.post(path, json=body).json()
    assert out["formats"] == ["radio_line", "sms"] and out["dropped"] == ["sms_mg"]
    truth = out["trajet"]["truth"]
    assert [(s["channel"], s["status"]) for s in truth] == [
        ("web", "broadcast"),
        ("radio", "sent"),
        ("sms", "sent"),
    ]
    assert truth[1]["location"]["region"] == "Analamanga"
    assert {g["channel"] for g in out["trajet"]["gaps"]} == {"facebook"}
    # Ticking « Relu en malgache » counts only with the fingerprint of what was read.
    blind = alice.post(path, json={**body, "relu_mg": True}).json()
    assert blind["dropped"] == ["sms_mg"] and blind["mg"] == {}
    shown = alice.get(f"/api/v1/workspaces/{ws}/items/{item}/diffusion").json()
    reread = alice.post(path, json={**body, "relu_mg": True, "mg_hash": shown["mg_hash"]}).json()
    assert reread["formats"] == ["radio_line", "sms", "sms_mg"] and reread["dropped"] == []
    assert reread["mg"] == {"sms_mg": shown["mg"]["sms"]}
    actions = [
        a["action"] for a in alice.get(f"/api/v1/workspaces/{ws}/activity?entity_id={item}").json()
    ]
    assert actions.count("diffuse") == 3 and actions.count("relu_mg") == 1


def test_malagasy_formats_stay_locked_until_a_logged_reread(as_user, model):
    alice = as_user("alice")
    ws = _workspace(alice)
    item = _published(alice, ws)
    base = f"/api/v1/workspaces/{ws}/items/{item}"
    assert alice.get(base + "/relu-mg").json() == {"relu_mg": None}
    assert alice.get(base + "/diffusion").json()["relu_mg"] is None
    # The tick cannot be forged through the ordinary edit.
    forged = alice.patch(base, json={"data": {"relu_mg": {"by": "bob", "at": "2026-11-02"}}})
    assert forged.status_code in (403, 409, 422)
    shown = alice.get(base + "/diffusion").json()
    assert alice.post(base + "/relu-mg", json={}).status_code == 422  # say what was read
    tick = alice.post(base + "/relu-mg", json={"mg_hash": shown["mg_hash"]}).json()["relu_mg"]
    assert tick["by"] == "alice" and tick["name"] == "Alice Rabe" and tick["current"] is True
    assert tick["mg_hash"] == shown["mg_hash"]
    body = {"routes": [{"channel": "sms", "place": "Abonnés"}], "formats": ["sms_mg", "text_mg"]}
    assert alice.post(base + "/diffuse", json=body).json()["dropped"] == []
    carnet = alice.get(base + "/carnet").json()["entries"]
    assert any(e["text"] == "Formats en malgache relus par un locuteur" for e in carnet)
    # A new explanation needs a new reading.
    alice.post(
        base + "/sign", json={"verdict": "false", "reason": REASON + " Précision.", "publish": True}
    )
    assert alice.get(base + "/relu-mg").json()["relu_mg"]["current"] is False
    assert alice.post(base + "/diffuse", json=body).json()["dropped"] == ["sms_mg", "text_mg"]
    alice.post(
        base + "/relu-mg", json={"mg_hash": alice.get(base + "/diffusion").json()["mg_hash"]}
    )
    assert alice.delete(base + "/relu-mg").json() == {"relu_mg": None}
    actions = [
        a["action"] for a in alice.get(f"/api/v1/workspaces/{ws}/activity?entity_id={item}").json()
    ]
    assert actions.count("relu_mg") == 2 and actions.count("relu_mg_undo") == 1
    assert as_user("bob").post(base + "/relu-mg", json={"mg_hash": "0" * 64}).status_code == 404


def _model_writes(monkeypatch, mg):
    """The model's next diffusion call returns these Malagasy drafts (the cache forgotten, as after
    a restart or a new call)."""
    trajet._WRITTEN.clear()
    reply = {
        "radio_line": "La rédaction a vérifié : les 72 heures de délestage sont fausses.",
        "sms": "FAUX : pas 72 heures de délestage.",
        "mg": mg,
    }

    def handler(request):
        msg = {"role": "assistant", "content": json.dumps(reply, ensure_ascii=False)}
        return httpx.Response(200, json={"model": "m", "choices": [{"message": msg}]})

    monkeypatch.setattr(ai, "_transport", httpx.MockTransport(handler))


def test_reread_then_send_sends_the_attested_strings(as_user, model):
    alice = as_user("alice")
    ws = _workspace(alice)
    item = _published(alice, ws)
    base = f"/api/v1/workspaces/{ws}/items/{item}"
    shown = alice.get(base + "/diffusion").json()
    tick = alice.post(base + "/relu-mg", json={"mg_hash": shown["mg_hash"]}).json()["relu_mg"]
    assert tick["current"] is True
    # The attestation keeps the very strings that were read, and their fingerprint.
    kept = _data(item)["relu_mg"]
    assert kept["texts"] == {"sms_mg": shown["mg"]["sms"], "text_mg": shown["mg"]["text"]}
    assert kept["mg_hash"] == shown["mg_hash"] == trajet.mg_hash(kept["texts"])
    body = {"routes": [{"channel": "sms", "place": "Abonnés"}], "formats": ["sms_mg", "text_mg"]}
    out = alice.post(base + "/diffuse", json=body).json()
    assert out["formats"] == ["sms_mg", "text_mg"] and out["dropped"] == []
    # What goes out is exactly the attested text, character for character.
    assert out["mg"] == kept["texts"] and out["mg_hash"] == shown["mg_hash"]
    stop = next(s for s in out["trajet"]["truth"] if s["channel"] == "sms")
    assert stop["proof"]["mg_hash"] == shown["mg_hash"] and stop["proof"]["relu_mg"] is True


def test_a_change_after_the_reread_locks_the_malagasy_formats_again(as_user, model, monkeypatch):
    alice = as_user("alice")
    ws = _workspace(alice)
    item = _published(alice, ws)
    base = f"/api/v1/workspaces/{ws}/items/{item}"
    body = {"routes": [{"channel": "sms", "place": "Abonnés"}], "formats": ["sms_mg", "text_mg"]}
    read = alice.get(base + "/diffusion").json()
    alice.post(base + "/relu-mg", json={"mg_hash": read["mg_hash"]})
    # The model writes the Malagasy text again (cache lost): one word differs, same verdict.
    _model_writes(monkeypatch, {**read["mg"], "text": "Diso tanteraka ity vaovao ity."})
    now = alice.get(base + "/diffusion").json()
    assert now["mg_hash"] != read["mg_hash"] and now["relu_mg"]["current"] is False
    out = alice.post(base + "/diffuse", json=body).json()
    assert out["dropped"] == ["sms_mg", "text_mg"] and out["mg"] == {} and out["mg_hash"] is None
    # An old fingerprint cannot vouch for the new text.
    stale = alice.post(base + "/relu-mg", json={"mg_hash": read["mg_hash"]})
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "mg_changed"
    sneaky = alice.post(
        base + "/diffuse", json={**body, "relu_mg": True, "mg_hash": read["mg_hash"]}
    )
    assert sneaky.json()["dropped"] == ["sms_mg", "text_mg"]
    # A new reread of the new text unlocks it, and that text is what goes out.
    alice.post(base + "/relu-mg", json={"mg_hash": now["mg_hash"]})
    sent = alice.post(base + "/diffuse", json=body).json()
    assert sent["mg"]["text_mg"] == "Diso tanteraka ity vaovao ity." and sent["dropped"] == []
    # Editing the Malagasy card's post after the reread locks it all again too.
    r = alice.patch(base, json={"data": {"posts": {"mg": "Lahatsoratra vaovao."}}})
    assert r.status_code == 200, r.text
    after = alice.get(base + "/diffusion").json()
    assert after["relu_mg"]["current"] is False
    assert alice.post(base + "/diffuse", json=body).json()["dropped"] == ["sms_mg", "text_mg"]


def test_partner_radio_marks_a_flash_broadcast_with_its_token(as_user, client, model):
    alice = as_user("alice")
    ws = _workspace(alice)
    item = _published(alice, ws)

    async def partner():
        async with SessionLocal() as db:
            db.add(
                RadioPartner(
                    workspace_id=uuid.UUID(ws),
                    name="Radio RDJ (démo)",
                    frequency="99.1",
                    location={"name": "Antananarivo", "region": "Analamanga"},
                    token="radio-token",
                )
            )
            await db.commit()

    asyncio.run(partner())
    alice.post(
        f"/api/v1/workspaces/{ws}/items/{item}/diffuse",
        json={
            "routes": [{"channel": "radio", "place": "Radio RDJ (démo) 99.1"}],
            "formats": ["flash"],
        },
    )
    out = client.post("/api/v1/public/radios/radio-token/diffuse", json={"item_id": item})
    assert out.status_code == 200 and out.json()["status"] == "broadcast"
    truth = alice.get(f"/api/v1/workspaces/{ws}/items/{item}/trajet").json()["truth"]
    assert [(s["place"], s["status"]) for s in truth if s["channel"] == "radio"] == [
        ("Radio RDJ (démo) 99.1", "broadcast")
    ]
    assert (
        client.post("/api/v1/public/radios/nope/diffuse", json={"item_id": item}).status_code == 404
    )
    other = _claim(alice, ws)
    assert (
        client.post(
            "/api/v1/public/radios/radio-token/diffuse", json={"item_id": other}
        ).status_code
        == 404
    )


def test_a_public_tip_is_the_rumours_first_stop(as_user, client):
    alice = as_user("alice")
    ws = _workspace(alice)
    alice.patch(f"/api/v1/workspaces/{ws}", json={"is_public": True})
    _verify(ws)
    slug = alice.get(f"/api/v1/workspaces/{ws}").json()["slug"]
    tip = {
        "newsroom": slug,
        "text": "Coupure de 72 heures à Toamasina, partagé partout",
        "origin": "whatsapp",
    }
    assert client.post("/api/v1/public/tips", json=tip).status_code == 201
    item = alice.get(f"/api/v1/workspaces/{ws}/items").json()["items"][0]
    out = alice.get(f"/api/v1/workspaces/{ws}/items/{item['id']}/trajet").json()
    assert [(s["channel"], s["place"], s["derived"]) for s in out["rumour"]] == [
        ("whatsapp", "Signalement du public", False)
    ]
    assert out["rumour"][0]["location"]["region"] == "Atsinanana"
