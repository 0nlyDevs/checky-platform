"""Ma rubrique: preferences, the morning page and its brief, Angles and Documents."""

import asyncio
from datetime import UTC, datetime, timedelta

from app.core.db import SessionLocal
from app.modules import rubrique


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
