"""Ma rubrique: preferences, the morning page and its brief, Angles and Documents."""

import asyncio
import json
import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.core import ai
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.models import Communique, Contact, Figure, PublicQuestion
from app.modules import rubrique
from tests.test_workspaces import _join, _workspace


def _db(fn):
    async def run():
        async with SessionLocal() as db:
            out = await fn(db)
            await db.commit()
            return out

    return asyncio.run(run())


def _ago(**kw) -> str:
    return (datetime.now(UTC) - timedelta(**kw)).isoformat()


@pytest.fixture
def model(monkeypatch):
    """The AI answers with whatever JSON the test puts in `answer`; `seen` keeps the requests."""
    s = get_settings()
    monkeypatch.setattr(s, "llm_providers", "groq")
    monkeypatch.setattr(s, "groq_api_key", "k")
    monkeypatch.setattr(s, "ai_cache", False)
    answer: dict = {}
    seen: list[dict] = []

    def handler(request):
        seen.append(json.loads(request.content))
        msg = {"role": "assistant", "content": json.dumps(answer["json"])}
        return httpx.Response(200, json={"model": "m", "choices": [{"message": msg}]})

    monkeypatch.setattr(ai, "_transport", httpx.MockTransport(handler))
    return answer, seen


def test_beats_are_found_by_their_usual_words():
    offered = ["énergie", "santé", "sécurité", "pêche"]
    assert rubrique.beats_for("72 heures de DÉLESTAGE selon la Jirama", offered) == ["énergie"]
    assert rubrique.beats_for("Hisy fahatapahan-jiro eto Toamasina", offered) == ["énergie"]
    assert rubrique.beats_for("Un enlèvement près du marché", offered) == ["sécurité"]
    assert rubrique.beats_for("La saison de pêche est ouverte", offered) == ["pêche"]
    assert rubrique.beats_for("Rien de particulier", offered) == []


def test_preferences_are_mine_and_places_are_understood(as_user):
    alice, eve = as_user("alice"), as_user("eve")
    ws = _workspace(alice)
    _join(alice, eve, ws, "veilleur")
    base = f"/api/v1/workspaces/{ws}/me/prefs"
    empty = alice.get(base).json()
    assert empty["beats"] == [] and "énergie" in empty["beats_offered"]
    assert "Analamanga" in empty["regions_offered"]
    saved = alice.put(
        base, json={"beats": ["énergie", "Énergie ", "santé"], "regions": ["tamatave", "Paris"]}
    ).json()
    assert saved["beats"] == ["énergie", "santé"] and saved["regions"] == ["Atsinanana", "Paris"]
    assert eve.put(base, json={"station": "RDJ"}).json()["station"] == "RDJ"
    assert eve.get(base).json()["beats"] == [] and alice.get(base).json()["station"] is None
    assert alice.put(base, json={"beats": ["x"], "colour": "red"}).status_code == 422


def test_the_morning_page_gathers_my_beats_and_places(as_user):
    alice = as_user("alice")
    ws = _workspace(alice)
    base = f"/api/v1/workspaces/{ws}"

    def claim(title, **data):
        r = alice.post(
            base + "/items", json={"title": title, "data": data, "tags": data.pop("tags", [])}
        )
        assert r.status_code == 201
        return r.json()

    energy = claim("72 heures de délestage à Antananarivo", first_seen_at=_ago(hours=2))
    claim("Trois cas de peste à Ambositra", first_seen_at=_ago(hours=1))
    mine = claim("Le maire de Mahajanga aurait démissionné", assignee_id="alice")
    suggested = claim("Hausse du tarif de l'électricité", verdict_suggested="false")
    alice.post(
        base + "/radio-clips",
        json={
            "station": "Radio Toamasina",
            "heard_text": "Un auditeur annonce un délestage de 12 heures à Toamasina.",
            "language": "fr",
            "recorded_at": _ago(minutes=40),
        },
    )

    async def shelves(db):
        ws_id = uuid.UUID(ws)
        db.add(
            Contact(
                workspace_id=ws_id,
                created_by="alice",
                name="Service presse (démo)",
                institution="JIRAMA (démo)",
                topics=["énergie"],
                is_demo=True,
            )
        )
        db.add(
            Contact(workspace_id=ws_id, created_by="alice", name="Hôpital (démo)", topics=["santé"])
        )
        db.add(
            Figure(
                workspace_id=None,
                topic="énergie",
                label="Délestage programmé",
                value="4",
                unit="h/jour",
                as_of="2026-11-01",
                source_name="JIRAMA (démo)",
                is_demo=True,
            )
        )
        db.add(
            Figure(
                workspace_id=None,
                topic="énergie",
                label="Accès à l'électricité",
                value="36",
                unit="%",
                as_of="2018",
                source_name="Banque mondiale",
            )
        )
        db.add(
            Figure(
                workspace_id=None,
                topic="santé",
                label="Médecins",
                value="2",
                as_of="2020",
                source_name="OMS",
            )
        )

    _db(shelves)
    alice.put(base + "/me/prefs", json={"beats": ["énergie"], "regions": ["Analamanga"]})
    page = alice.get(base + "/rubrique").json()
    assert page["beats"] == ["énergie"] and page["regions"] == ["Analamanga"]
    assert page["today_label"].split()[0] in rubrique.WEEKDAYS
    titles = [c["title"] for c in page["circulating"]]
    assert titles[0] == energy["title"]  # my beat and my place: first
    assert "Trois cas de peste à Ambositra" not in titles
    assert any(c["kind"] == "clip" and "Toamasina" in c["title"] for c in page["circulating"])
    first = page["circulating"][0]
    assert first["item"]["id"] == energy["id"] and first["place"]["region"] == "Analamanga"
    assert [i["id"] for i in page["mine"]] == [mine["id"]]
    assert [i["id"] for i in page["to_sign"]] == [suggested["id"]]
    assert [c["name"] for c in page["contacts"]] == ["Service presse (démo)"]
    figures = {f["label"]: f for f in page["figures"]}
    assert set(figures) == {"Délestage programmé", "Accès à l'électricité"}
    assert figures["Accès à l'électricité"]["old"] and not figures["Délestage programmé"]["old"]
    assert len(page["angles"]) <= 3 and all(a["kind"] == "piste" for a in page["angles"])
    assert "seasons" in page["meteo"] and page["antenne"][0]["stations"] == ["Radio Toamasina"]

    other = alice.get(base + "/rubrique?beat=santé&region=*").json()
    assert [c["title"] for c in other["circulating"]] == ["Trois cas de peste à Ambositra"]
    everything = alice.get(base + "/rubrique?beat=*&region=*").json()
    assert len(everything["circulating"]) == 5

    brief = alice.get(base + "/rubrique/brief").json()["text"]
    assert brief.startswith("Checky · Ma rubrique · ")
    assert "énergie · Analamanga" in brief and f"- {energy['title']} (Antananarivo)" in brief
    assert "À signer : 1 dossier." in brief


def test_angles_rest_on_numbered_facts_and_invent_nothing(as_user, model):
    answer, seen = model
    alice = as_user("alice")
    ws = _workspace(alice)
    base = f"/api/v1/workspaces/{ws}"
    claim = alice.post(
        base + "/items",
        json={"title": "72 heures de délestage à Antananarivo", "tags": ["énergie"]},
    ).json()
    _db(
        lambda db: _add(
            db,
            PublicQuestion(
                workspace_id=uuid.UUID(ws),
                text="Le délestage va durer combien de temps ?",
                channel="sms",
            ),
        )
    )

    # nothing on the topic: no model call, no angle
    empty = alice.post(base + "/angles", json={"topic": "pêche au thon"}).json()
    assert empty["angles"] == [] and empty["facts"] == [] and seen == []

    answer["json"] = {
        "angles": [
            {
                "title": "Qui décide des délestages ?",
                "why": "Le public demande la durée.",
                "rests_on": [1, "2"],
                "missing_figure": "La durée officielle",
            },
            {"title": "Un angle sans appui", "why": "…", "rests_on": [99]},
            {
                "title": "500 quartiers privés de courant",
                "why": "Chiffre inventé.",
                "rests_on": [1],
            },
        ]
    }
    out = alice.post(base + "/angles", json={"topic": "énergie"})
    assert out.status_code == 200, out.text
    out = out.json()
    assert [a["title"] for a in out["angles"]] == ["Qui décide des délestages ?"]
    angle = out["angles"][0]
    assert [f["kind"] for f in angle["rests_on"]] == ["claim", "question"]
    assert angle["rests_on"][0]["item_id"] == claim["id"] and out["dropped"] == 2
    prompt = seen[-1]["messages"]
    assert "Aujourd'hui" in prompt[0]["content"] and "[1] Dossier" in prompt[1]["content"]
    assert alice.post(base + "/angles", json={}).status_code == 422

    kept = alice.post(f"{base}/items/{claim['id']}/angles/keep", json={"angle": angle})
    assert kept.status_code == 200
    alice.post(f"{base}/items/{claim['id']}/angles/keep", json={"angle": angle})
    item = alice.get(f"{base}/items/{claim['id']}").json()
    assert len(item["data"]["angles"]) == 1 and item["data"]["angles"][0]["kept_by"] == "alice"
    alice.put(base + "/me/prefs", json={"beats": ["énergie"]})
    page = alice.get(base + "/rubrique").json()
    assert page["angles"][0]["kind"] == "kept" and page["angles"][0]["item_id"] == claim["id"]

    alice.patch(base, json={"settings": {"ai_enabled": False}})
    assert alice.post(base + "/angles", json={"topic": "énergie"}).status_code == 409


async def _add(db, row):
    db.add(row)


def test_documents_are_the_sources_that_name_a_document(as_user):
    alice, bob = as_user("alice"), as_user("bob")
    ws = _workspace(alice)
    base = f"/api/v1/workspaces/{ws}"
    for title, text in (
        ("Communiqué de la JIRAMA sur le délestage", "Délestage de 4 heures par quartier."),
        (
            "Démo · Décret n° 2026-12 relatif aux examens (exemple fictif)",
            "Le bac commence le 24 novembre.",
        ),
        ("Notes de terrain", "Vu au marché."),
        ("Rapport annuel de l'INSTAT", "Population et prix."),
        ("Calendrier des examens nationaux", "Le bac commence le 24 novembre."),
    ):
        assert alice.post(base + "/sources", json={"title": title, "text": text}).status_code == 201
    docs = alice.get(base + "/documents").json()
    assert sorted(d["doc_type"] for d in docs) == ["calendrier", "communiqué", "décret", "rapport"]
    jirama = next(d for d in docs if d["doc_type"] == "communiqué")
    assert jirama["issuer"] == "JIRAMA" and jirama["beats"] == ["énergie"] and not jirama["demo"]
    issuers = {d["doc_type"]: d["issuer"] for d in docs}
    assert (
        issuers["rapport"] == "INSTAT" and issuers["calendrier"] is None
    )  # a subject, not an issuer
    assert next(d for d in docs if d["doc_type"] == "décret")["demo"]
    assert [d["doc_type"] for d in alice.get(base + "/documents?topic=énergie").json()] == [
        "communiqué"
    ]
    assert [d["doc_type"] for d in alice.get(base + "/documents?q=population").json()] == [
        "rapport"
    ]
    assert bob.get(base + "/documents").status_code == 404
    assert _db(lambda db: _count(db)) == 0


async def _count(db):
    from sqlalchemy import func, select

    return await db.scalar(select(func.count()).select_from(Communique))


def test_the_demo_gives_the_admin_the_pitch_beat(as_user):
    alice = as_user("alice")
    ws = _workspace(alice)
    base = f"/api/v1/workspaces/{ws}"
    assert alice.post(base + "/demo/reset").status_code == 200
    prefs = alice.get(base + "/me/prefs").json()
    assert prefs["beats"] == ["énergie"] and prefs["regions"] == ["Analamanga"]
    page = alice.get(base + "/rubrique").json()
    refs = [(c["item"] or {}).get("data", {}).get("ref") for c in page["circulating"]]
    assert "FAN-0145" in refs
    assert any(
        c["kind"] == "clip" and c.get("station", "").startswith("Radio Fanambarana")
        for c in page["circulating"]
    )
