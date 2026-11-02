"""Ma rubrique: preferences, the morning page and its brief, Angles and Documents."""

import asyncio
from datetime import UTC, datetime, timedelta

from app.core.db import SessionLocal
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
