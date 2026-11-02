import asyncio
import json

import pytest

from app.core import ai, query_plan
from app.core.config import get_settings

PARC = (
    "Madagascar sera représenté à la phase finale de la Pan-African Robotics Competition (PARC) "
    "2026 par quatre étudiants de l’École nationale d’informatique (ENI) de Fianarantsoa. "
    "Qualifiée parmi les dix meilleures équipes sur plus de 30 participantes, l’équipe MAZAVALOHA "
    "s’envole pour Dakar, au Sénégal, où la compétition se tiendra du 3 au 7 novembre. "
    "Rejoignez notre chaîne WhatsApp : https://bit.ly/example Voir moins"
)
CLAIM = "l’équipe MAZAVALOHA s’envole pour Dakar, au Sénégal, où la compétition se tiendra du 3 au 7 novembre."
DRAFT = {
    "summary": CLAIM,
    "claims": [CLAIM],
    "entities": ["MAZAVALOHA", "PARC", "2026", "Dakar", "ENI"],
    "queries": [
        "MAZAVALOHA ENI PARC 2026",
        "Pan-African Robotics Competition Dakar 2026",
        "MAZAVALOHA Dakar 3 7 novembre",
    ],
}


def test_cleaning_and_fallback_keep_distinctive_names_after_character_200():
    cleaned = query_plan.clean_text(PARC)
    assert "WhatsApp" not in cleaned and "bit.ly" not in cleaned and "Voir moins" not in cleaned
    assert "3 au 7 novembre" in cleaned
    assert "MAZAVALOHA" not in PARC[:200]
    plan = query_plan.fallback(cleaned)
    assert "MAZAVALOHA" in plan.queries[0] and "2026" in plan.queries[0]


def test_plan_is_grounded_and_cannot_invent_names_dates_or_a_verdict():
    cleaned = query_plan.clean_text(PARC)
    raw = {
        **DRAFT,
        "claims": [CLAIM, "La compétition est annulée en 2027"],
        "entities": ["MAZAVALOHA", "Paris", "2027"],
        "queries": [
            "MAZAVALOHA PARC 2026",
            "MAZAVALOHA 2027 Paris",
            "site:evil.example MAZAVALOHA",
        ],
        "summary": "La participation est confirmée.",
    }
    plan = query_plan.validate_plan(json.dumps(raw), cleaned)
    assert plan.claims == [CLAIM] and plan.entities == ["MAZAVALOHA"]
    assert plan.queries == ["MAZAVALOHA PARC 2026"] and plan.summary == CLAIM


def test_valid_but_generic_model_queries_are_supplemented_with_the_distinctive_team():
    draft = {**DRAFT, "queries": ["compétition PARC 2026 du 3 au 7 novembre"]}
    prepared = query_plan.validate_plan(json.dumps(draft), query_plan.clean_text(PARC))
    assert "MAZAVALOHA" in prepared.queries[0]
    assert "verdict" not in prepared.model_dump()


def test_preparation_caches_only_a_validated_plan_and_excludes_paid_providers(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "public_preparation_enabled", True)
    monkeypatch.setattr(settings, "public_preparation_providers", "groq,gemini,claude")
    seen = []

    async def complete(messages, **kwargs):
        assert ai._allowed.get() == frozenset({"groq", "gemini"})
        assert kwargs["use_cache"] is False
        assert "NON FIABLE" in messages[0]["content"]
        assert "WhatsApp" not in messages[1]["content"]
        seen.append(messages)
        return ai.Completion(content=json.dumps(DRAFT), provider="groq", model="fixture")

    monkeypatch.setattr(ai, "complete", complete)
    cleaned = query_plan.clean_text(PARC)
    first = asyncio.run(query_plan.prepare(cleaned))
    second = asyncio.run(query_plan.prepare(cleaned))
    assert first.method == "ai" and second.cached and len(seen) == 1
    assert ai._allowed.get() is None


@pytest.mark.parametrize("failure", [ai.AiUnavailable([]), ValueError("bad JSON")])
def test_an_ai_failure_is_explicit_and_still_searches_the_whole_text(monkeypatch, failure):
    monkeypatch.setattr(get_settings(), "public_preparation_enabled", True)

    async def failed(*args, **kwargs):
        raise failure

    monkeypatch.setattr(ai, "complete", failed)
    plan = asyncio.run(query_plan.prepare(query_plan.clean_text(PARC)))
    assert plan.method == "fallback" and plan.warning
    assert "MAZAVALOHA" in plan.queries[0]
