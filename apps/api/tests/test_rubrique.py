"""Ma rubrique: preferences, the morning page and its brief, Angles and Documents."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

from app.core.db import SessionLocal
from app.core.models import Contact, Figure
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
