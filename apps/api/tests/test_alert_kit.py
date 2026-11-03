"""« Kit d'alerte » (6.4): drafted from the alert's evidence, guarded by code, approved by a
journalist, sent to the desk and the partner radios of its regions; the closing rules; live
alerts in the desk (8.4)."""

import asyncio
import json

import httpx
import pytest

from app.core import ai
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.modules.sms import _reach
from tests.test_alerts import KIDNAP_FR, KIDNAP_MG, _clip, _dossier, _scan
from tests.test_public import _newsroom
from tests.test_veille import _ago

ACCUSING = (
    "Le voleur d'enfants serait Rakotomalala, il a enlevé une fillette au marché de Mahajanga."
)


@pytest.fixture(autouse=True)
def seal_secret(monkeypatch):
    """A radio's SMS number is sealed with SEAL_SECRET before it is queued (core/contact.py);
    without one the send answers 503, so these tests passed only where a local .env had it."""
    monkeypatch.setattr(get_settings(), "seal_secret", "alert-kit-test-seal-secret")


@pytest.fixture
def model(monkeypatch):
    """A model that tries everything the guards must catch: the accused's name, a number found
    nowhere in the evidence, alarm words."""
    s = get_settings()
    monkeypatch.setattr(s, "llm_providers", "groq")
    monkeypatch.setattr(s, "groq_api_key", "k")
    monkeypatch.setattr(s, "ai_cache", False)
    seen = []
    answer = {
        "known": [
            "Des auditeurs de deux radios rapportent un enlèvement d'enfant.",
            "Rakotomalala est désigné comme le voleur.",
            "12 enfants auraient disparu.",
        ],
        "unknown": ["Aucune plainte n'est connue à ce stade."],
        "script_fr": (
            "Une rumeur d'enlèvement d'enfant circule à Mahajanga. Rien ne confirme à ce stade "
            "qu'elle soit vraie. URGENT : partagez à tous vos contacts ! Rakotomalala n'a été mis "
            "en cause par aucune autorité. 12 enfants seraient concernés. Ne vous faites pas "
            "justice vous-même."
        ),
        "script_mg": "Misy tsaho miely any Mahajanga. Tsy misy manamarina izany hatreto.",
        "dont_say": ["Ne citez pas de chiffre de victimes."],
    }

    def handler(request):
        seen.append(json.loads(request.content))
        msg = {"role": "assistant", "content": json.dumps(answer, ensure_ascii=False)}
        return httpx.Response(200, json={"model": "m", "choices": [{"message": msg}]})

    monkeypatch.setattr(ai, "_transport", httpx.MockTransport(handler))
    return seen


def _alert(c, ws):
    _clip(c, ws, KIDNAP_FR, "Radio Boeny (démo)", region="Boeny")
    _clip(c, ws, KIDNAP_MG, "Radio Sofia (démo)", language="mg", region="Sofia")
    item = _dossier(c, ws, ACCUSING, risk="high")
    assert _scan(c, ws)["created"] == 1
    [alert] = c.get(f"/api/v1/workspaces/{ws}/alerts").json()
    return alert, item


def _annuaire(c, ws):
    def contact(**fields):
        body = {"kind": "institution", "languages": ["fr", "mg"], **fields}
        r = c.post(f"/api/v1/workspaces/{ws}/contacts", json=body)
        assert r.status_code == 201, r.text
        return r.json()["id"]

    return {
        "police": contact(
            name="Commissariat central (démo)", institution="Police nationale",
            place="Mahajanga", phone="+261 34 00 000 11",
        ),
        "gendarmerie": contact(
            name="Gendarmerie nationale (démo)", institution="Gendarmerie", phone="+261 34 00 000 12"
        ),
        "far_police": contact(
            name="Commissariat de Toamasina (démo)", institution="Police nationale",
            place="Toamasina", phone="+261 34 00 000 13",
        ),
        "jirama": contact(name="JIRAMA (démo)", institution="JIRAMA", topics=["énergie"]),
    }  # fmt: skip


def _radio(c, ws, name, region, **extra):
    body = {"name": name, "frequency": "FM 98.0", "region": region, **extra}
    r = c.post(f"/api/v1/workspaces/{ws}/radios", json=body)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_the_model_drafts_the_kit_and_code_guards_it(as_user, model):
    alice = as_user("alice")
    ws, _ = _newsroom(alice)
    alert, _ = _alert(alice, ws)
    ids = _annuaire(alice, ws)
    url = f"/api/v1/workspaces/{ws}/alerts/{alert['id']}/kit"

    assert alice.get(url).json()["kit"] is None
    r = alice.post(url, json={})
    assert r.status_code == 200, r.text
    kit = r.json()["kit"]
    assert kit["status"] == "draft" and kit["written_by"] == "model"
    # one model call, in JSON mode, on the alert's own reports
    assert len(model) == 1 and model[0]["response_format"] == {"type": "json_object"}
    assert "Mahajanga" in model[0]["messages"][1]["content"]

    everything = json.dumps(kit, ensure_ascii=False)
    assert "Rakotomalala" not in everything  # never the accused's name, in any part
    assert "la personne mise en cause" in " ".join(kit["known"])
    texts = " ".join([*kit["known"], *kit["unknown"], *kit["script"].values()])
    assert "12" not in texts  # a number found nowhere in the evidence
    script = kit["script"]["fr"]
    assert "Rien ne confirme à ce stade" in script
    assert "URGENT" not in script and "partagez" not in script.lower()
    assert "Ne vous faites pas justice" in script
    assert kit["guards"]["names"] >= 2 and kit["guards"]["numbers"] >= 2
    assert kit["guards"]["alarm"] >= 1
    assert kit["script"]["mg"].startswith("Misy tsaho")
    # « À ne pas dire » always carries the rules
    assert any("nom de la personne mise en cause" in x for x in kit["dont_say"])

    # « Qui appeler » comes from the Annuaire, for the alert's regions, never from the model
    calls = {c["contact_id"]: c for c in kit["call"]}
    assert ids["police"] in calls and ids["gendarmerie"] in calls
    assert ids["far_police"] not in calls and ids["jirama"] not in calls
    assert calls[ids["police"]]["phone"] == "+261 34 00 000 11"
    assert calls[ids["police"]]["why"] == "police · Boeny"
    assert calls[ids["gendarmerie"]]["why"] == "gendarmerie · national"

    acts = alice.get(f"/api/v1/workspaces/{ws}/activity?entity_id={alert['id']}").json()
    assert "kit_draft" in [a["action"] for a in acts]
    assert alice.get(f"/api/v1/workspaces/{ws}/alerts").json()[0]["kit"]["status"] == "draft"


def test_without_ai_the_kit_is_a_template_from_the_facts(as_user, model):
    alice = as_user("alice")
    ws, _ = _newsroom(alice)
    alert, _ = _alert(alice, ws)
    url = f"/api/v1/workspaces/{ws}/alerts/{alert['id']}/kit"

    kit = alice.post(url, json={"ai": False}).json()["kit"]
    assert model == []  # « Mode sans IA »: no model call
    assert kit["written_by"] == "template" and not kit["fallback"]
    assert "Rakotomalala" not in json.dumps(kit, ensure_ascii=False)
    assert "3 éléments regroupés" in kit["known"][0]
    assert "Rien ne confirme à ce stade" in kit["script"]["fr"]
    assert "Boeny" in kit["script"]["fr"] and "Sofia" in kit["script"]["fr"]
    assert kit["call"] == []  # an empty Annuaire: nobody is invented
    # the newsroom's own « Mode sans IA » wins over the button
    alice.patch(f"/api/v1/workspaces/{ws}", json={"settings": {"ai_enabled": False}})
    assert alice.post(url, json={}).json()["kit"]["written_by"] == "template"
    assert model == []


def test_emergency_kit_never_copies_another_newsrooms_shared_contact(as_user):
    alice, bob = as_user("alice"), as_user("bob")
    ws, _ = _newsroom(alice)
    other, _ = _newsroom(bob)
    alert, _ = _alert(alice, ws)
    shared = bob.post(
        f"/api/v1/workspaces/{other}/contacts",
        json={
            "kind": "institution",
            "name": "Commissariat partagé (démo)",
            "institution": "Police nationale",
            "place": "Mahajanga",
            "phone": "+261 34 00 000 98",
            "whatsapp": "+261 34 00 000 99",
            "languages": ["fr"],
            "shared": True,
        },
    )
    assert shared.status_code == 201, shared.text
    assert any(
        c["id"] == shared.json()["id"]
        for c in alice.get(f"/api/v1/workspaces/{ws}/contacts").json()
    )
    kit = alice.post(
        f"/api/v1/workspaces/{ws}/alerts/{alert['id']}/kit", json={"ai": False}
    ).json()["kit"]
    assert kit["call"] == []
    assert "+261 34 00 000 98" not in json.dumps(kit)
    assert "+261 34 00 000 99" not in json.dumps(kit)


def test_with_no_model_answering_the_template_takes_over(as_user, monkeypatch):
    monkeypatch.setattr(get_settings(), "llm_providers", "groq")
    monkeypatch.setattr(get_settings(), "groq_api_key", "")
    alice = as_user("alice")
    ws, _ = _newsroom(alice)
    alert, _ = _alert(alice, ws)
    kit = alice.post(f"/api/v1/workspaces/{ws}/alerts/{alert['id']}/kit", json={}).json()["kit"]
    assert kit["written_by"] == "template" and kit["fallback"]


def test_approve_send_and_the_malagasy_reread(as_user, model):
    alice, bob = as_user("alice"), as_user("bob")
    ws, _ = _newsroom(alice)
    alert, _ = _alert(alice, ws)
    boeny = _radio(alice, ws, "Radio Boeny (démo)", "Mahajanga", whatsapp="+261 34 00 000 21")
    far = _radio(alice, ws, "Radio Est (démo)", "Toamasina")
    base = f"/api/v1/workspaces/{ws}/alerts/{alert['id']}"
    alice.post(base + "/kit", json={})
    assert bob.get(base + "/kit").status_code == 404  # another newsroom

    state = alice.get(base + "/kit").json()
    radios = {r["id"]: r for r in state["radios"]}
    assert radios[boeny]["in_region"] and not radios[far]["in_region"]
    assert state["radios"][0]["id"] == boeny  # the region's radios first

    # a draft is not sent
    r = alice.post(base + "/kit/send", json={"radio_ids": [boeny]})
    assert r.status_code == 409 and r.json()["error"]["code"] == "kit_not_approved"

    # the journalist edits: the accused's name still never stays
    r = alice.put(
        base + "/kit",
        json={"script_fr": "Rien ne confirme à ce stade ce que l'on dit de Rakotomalala."},
    )
    assert r.status_code == 200, r.text
    kit = r.json()["kit"]
    assert kit["status"] == "approved" and kit["edited"] and kit["approved_by"] == "alice"
    assert kit["approved_name"] == "Alice Rabe"
    assert "Rakotomalala" not in kit["script"]["fr"]
    assert "la personne mise en cause" in kit["script"]["fr"]
    assert alice.put(base + "/kit", json={"script_fr": "  "}).status_code == 422

    # sent before the Malagasy reread: French only
    r = alice.post(base + "/kit/send", json={"radio_ids": [boeny]})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["mg"] is False and "Amin'ny teny malagasy" not in out["message"]
    assert "ALR-0001 · Kit d'alerte" in out["message"]
    [link] = out["links"]
    assert link["whatsapp"].startswith(f"/public/alert-kit/whatsapp/{alert['id']}/")
    opened = alice.get("/api/v1" + link["whatsapp"], follow_redirects=False)
    assert opened.status_code == 302
    assert opened.headers["location"].startswith("https://wa.me/261340000021?text=")
    assert opened.headers["cache-control"] == "no-store"
    assert link["sms"] is None
    [stop] = out["state"]["trajet"]
    assert stop["channel"] == "radio" and stop["status"] == "sent"
    assert stop["place"] == "Radio Boeny (démo) FM 98.0"
    assert out["state"]["kit"]["sent"][0]["desks"] is True
    assert [r["sent"] for r in out["state"]["radios"]] == [True, False]

    # « Relu en malgache » is bound to the exact text on screen
    h = out["state"]["kit"]["mg_hash"]
    assert alice.post(base + "/kit/relu-mg", json={"mg_hash": "0" * 64}).status_code == 409
    kit = alice.post(base + "/kit/relu-mg", json={"mg_hash": h}).json()["kit"]
    assert kit["relu_mg"]["current"] and kit["relu_mg"]["name"] == "Alice Rabe"
    out = alice.post(base + "/kit/send", json={"radio_ids": [boeny, far]}).json()
    assert out["mg"] is True and "Amin'ny teny malagasy" in out["message"]
    # a changed Malagasy script needs a new reread
    kit = alice.put(base + "/kit", json={"script_mg": "Tsy misy manamarina."}).json()["kit"]
    assert kit["relu_mg"]["current"] is False
    assert alice.post(base + "/kit/send", json={"radio_ids": [far]}).json()["mg"] is False

    actions = [
        a["action"]
        for a in alice.get(f"/api/v1/workspaces/{ws}/activity?entity_id={alert['id']}").json()
    ]
    assert {"kit_draft", "kit_approve", "kit_send", "kit_relu_mg"} <= set(actions)
    assert alice.get(f"/api/v1/workspaces/{ws}/alerts").json()[0]["kit"]["radios"] == 2


def test_radio_sms_is_queued_once_with_a_masked_number(as_user):
    alice = as_user("alice")
    ws, _ = _newsroom(alice)
    alert, _ = _alert(alice, ws)
    radio = _radio(alice, ws, "Radio SMS (démo)", "Mahajanga", sms="+261 34 00 000 22")
    base = f"/api/v1/workspaces/{ws}/alerts/{alert['id']}/kit"
    alice.post(base, json={"ai": False})
    alice.put(base, json={})
    first = alice.post(base + "/send", json={"radio_ids": [radio]}).json()
    assert first["links"][0]["sms"] is None
    assert first["links"][0]["sms_queued"] is True
    assert "+261340000022" not in json.dumps(first)
    assert "+261 34 00 000 22" not in json.dumps(first)
    alice.post(base + "/send", json={"radio_ids": [radio]})
    messages = alice.get(f"/api/v1/workspaces/{ws}/sms/messages").json()
    assert len(messages) == 1
    assert messages[0]["status"] == "simulated"
    assert "••" in messages[0]["masked"]
    assert messages[0]["to"] is None


def test_radio_sms_gateway_can_read_sealed_outbound_destination(as_user):
    alice = as_user("alice")
    ws, _ = _newsroom(alice)
    alert, _ = _alert(alice, ws)
    radio = _radio(alice, ws, "Radio test", "Mahajanga", sms="+261 34 12 345 67")
    base = f"/api/v1/workspaces/{ws}/alerts/{alert['id']}/kit"
    alice.post(base, json={"ai": False})
    alice.put(base, json={})
    out = alice.post(base + "/send", json={"radio_ids": [radio]}).json()
    assert out["links"][0]["sms_queued"] is True
    assert "+261341234567" not in json.dumps(out)
    [message] = alice.get(f"/api/v1/workspaces/{ws}/sms/messages").json()
    assert message["status"] == "queued"

    async def destination():
        async with SessionLocal() as db:
            return await _reach(db, message["phone_hash"])

    assert asyncio.run(destination()) == "+261341234567"


def test_a_journalist_closes_an_alert_with_a_reason_and_diffuser_proposes_its_radios(
    as_user, model
):
    alice = as_user("alice")
    ws, _ = _newsroom(alice)
    alert, item = _alert(alice, ws)
    boeny = _radio(alice, ws, "Radio Boeny (démo)", "Mahajanga")
    _radio(alice, ws, "Radio Sofia (démo)", "Antsohihy")
    _radio(alice, ws, "Radio Est (démo)", "Toamasina")
    base = f"/api/v1/workspaces/{ws}/alerts/{alert['id']}"

    # before any kit: Diffuser proposes the partner radios of the alert's regions
    [proposed] = alice.get(f"/api/v1/workspaces/{ws}/items/{item}/alert-radios").json()
    assert sorted(r["place"] for r in proposed["routes"]) == [
        "Radio Boeny (démo) FM 98.0",
        "Radio Sofia (démo) FM 98.0",
    ]
    alice.post(base + "/kit", json={})
    alice.put(base + "/kit", json={})
    alice.post(base + "/kit/send", json={"radio_ids": [boeny]})

    assert alice.post(base + "/close", json={}).status_code == 422
    assert alice.post(base + "/close", json={"reason": "  "}).status_code == 422
    r = alice.post(base + "/close", json={"reason": "La gendarmerie a démenti sur place"})
    assert r.status_code == 200, r.text
    closed = r.json()
    assert closed["state"] == "closed" and closed["closed"]["reason"] == "journalist"
    assert closed["closed"]["note"] == "La gendarmerie a démenti sur place"
    assert alice.post(base + "/close", json={"reason": "encore"}).status_code == 409
    assert alice.post(base + "/kit", json={}).status_code == 409
    assert alice.get(f"/api/v1/workspaces/{ws}/alerts").json() == []
    assert alice.get(f"/api/v1/workspaces/{ws}/alerts?state=closed").json()[0]["id"] == alert["id"]

    # then « Diffuser » proposes the radios the kit went to
    [proposed] = alice.get(f"/api/v1/workspaces/{ws}/items/{item}/alert-radios").json()
    assert proposed["state"] == "closed" and proposed["ref"] == "ALR-0001"
    assert [r["place"] for r in proposed["routes"]] == ["Radio Boeny (démo) FM 98.0"]
    assert proposed["routes"][0]["channel"] == "radio"
    assert proposed["routes"][0]["location"]["region"] == "Boeny"
    acts = alice.get(f"/api/v1/workspaces/{ws}/activity?entity_id={alert['id']}").json()
    assert any(a["action"] == "close" and a["diff"]["reason"] == "journalist" for a in acts)


def test_a_published_verdict_on_a_linked_dossier_closes_the_alert(as_user):
    alice = as_user("alice")
    ws, _ = _newsroom(alice)
    alert, item = _alert(alice, ws)
    r = alice.post(
        f"/api/v1/workspaces/{ws}/items/{item}/sign",
        json={"verdict": "false", "reason": "La gendarmerie de Mahajanga dément.", "publish": True},
    )
    assert r.status_code == 200 and r.json()["status"] == "published", r.text
    [closed] = alice.get(f"/api/v1/workspaces/{ws}/alerts?state=closed").json()
    assert closed["id"] == alert["id"]
    assert closed["closed"]["reason"] == "verdict" and closed["closed"]["item_id"] == item
    assert closed["closed"]["verdict"] == "false"
    assert alice.get(f"/api/v1/workspaces/{ws}/alerts").json() == []


def test_the_grouping_sweep_closes_alerts_whose_dossier_was_published_otherwise(as_user):
    alice = as_user("alice")
    ws, _ = _newsroom(alice)
    _, item = _alert(alice, ws)
    # published through the plain status route
    alice.patch(
        f"/api/v1/workspaces/{ws}/items/{item}",
        json={"status": "published", "data": {"verdict": "false"}},
    )
    _scan(alice, ws)
    assert alice.get(f"/api/v1/workspaces/{ws}/alerts").json() == []


def test_live_notices_in_the_desk(as_user, model):
    alice, bob = as_user("alice"), as_user("bob")
    ws, _ = _newsroom(alice)
    base = f"/api/v1/workspaces/{ws}"
    alice.patch(base, json={"settings": {"region": "Boeny"}})
    alice.post(base + "/signals", json={"word": "fillette"})
    alert, item = _alert(alice, ws)
    # a rumour route seen 30 hours ago, the truth never followed
    late = _dossier(alice, ws, "Pénurie de riz annoncée à Mahajanga")
    r = alice.post(
        f"{base}/items/{late}/routes",
        json={
            "side": "rumour", "channel": "facebook", "place": "Groupe Mahajanga Infos",
            "note": "Vu dans un groupe public", "at": _ago(hours=30),
        },
    )  # fmt: skip
    assert r.status_code == 201, r.text
    alice.post(
        f"{base}/items/{late}/routes",
        json={
            "side": "rumour", "channel": "whatsapp", "place": "Groupe récent",
            "note": "Vu il y a peu", "at": _ago(hours=2),
        },
    )  # fmt: skip

    notices = alice.get(base + "/live").json()
    kinds = {n["kind"]: n for n in notices}
    assert kinds["high_risk"]["id"] == f"alert:{alert['id']}"
    assert kinds["high_risk"]["href"] == f"/veille#alerte-{alert['id']}"
    assert kinds["high_risk"]["ref"] == "ALR-0001"
    assert kinds["on_air"]["title"] == "fillette"
    assert "Radio Boeny" in kinds["on_air"]["detail"]
    [gap] = [n for n in notices if n["kind"] == "truth_late"]
    assert gap["detail"] == "Groupe Mahajanga Infos" and gap["href"].endswith("#trajet")
    # the dossier inside the alert is not announced twice
    assert f"item:{item}" not in {n["id"] for n in notices}
    assert bob.get(base + "/live").status_code == 404

    akit = f"{base}/alerts/{alert['id']}/kit"
    alice.post(akit, json={})
    alice.put(akit, json={})
    alice.post(akit + "/send", json={"desks": True})
    assert "kit_sent" in {n["kind"] for n in alice.get(base + "/live").json()}


def test_live_high_risk_stays_in_the_newsrooms_regions(as_user):
    alice = as_user("alice")
    ws, _ = _newsroom(alice)
    base = f"/api/v1/workspaces/{ws}"
    alice.patch(base, json={"settings": {"region": "Atsinanana"}})
    _alert(alice, ws)  # Boeny and Sofia
    assert [n for n in alice.get(base + "/live").json() if n["kind"] == "high_risk"] == []
