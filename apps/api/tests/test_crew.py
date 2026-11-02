"""The verification crew on Vérifier: facts without a model, three model calls at most, quotes
bound to what was read, one targeted loop, a confidence computed in code, and fail-soft nodes."""

import asyncio
import json
from types import SimpleNamespace

import pytest

from app.core import ai, evidence_search, websearch
from app.core.db import SessionLocal
from app.modules import crew, linkcheck
from app.modules.demo import DEMO_RUMOUR_TEXT
from tests.test_agent import _events
from tests.test_public import _claim, _newsroom
from tests.test_workspaces import _workspace

PORT = "Le port de Rio est fermé."


@pytest.fixture
def research(monkeypatch):
    calls = {"search": 0, "web": [], "fact_checks": []}

    async def search(plan, skip=None):
        calls["search"] += 1
        calls["queries"] = list(plan.queries)
        return evidence_search.SearchReport(
            status="ok",
            attempts=[],
            sources=[
                evidence_search.ResearchSource(
                    n=1,
                    kind="web",
                    title="Annonce du port",
                    url="https://example.org/port",
                    snippet="Le port de Rio est ouvert.",
                    date="2026-01-01",
                )
            ],
        )

    async def read(sources, plan, text):
        for s in sources:
            s.read_status = "read"
            s.passages = ["Le port de Rio est ouvert."]

    async def fact_checks(query, k=6):
        calls["fact_checks"].append(query)
        return [
            {
                "title": "Le port de Rio n'est pas fermé",
                "url": "https://factuel.afp.com/doc.afp.com.rio",
                "snippet": "AFP Factuel : « Faux ». Affirmation : le port de Rio est fermé.",
                "date": "2026-10-30",
            },
            {
                "title": "Un tout autre sujet",
                "url": "https://factuel.afp.com/doc.afp.com.autre",
                "snippet": "Rien à voir.",
            },
        ]

    async def web(query, k=6):
        calls["web"].append(query)
        return [
            {"title": "Capitainerie", "url": "https://example.org/capitainerie", "snippet": "x"}
        ]

    monkeypatch.setattr(evidence_search, "search", search)
    monkeypatch.setattr(evidence_search, "read_sources", read)
    monkeypatch.setattr(websearch, "fact_checks", fact_checks)
    monkeypatch.setattr(websearch, "web", web)
    linkcheck._CHECKS.clear()
    return calls


def _forbid_models(monkeypatch):
    async def forbidden(*args, **kwargs):
        raise AssertionError("No model call allowed")

    monkeypatch.setattr(ai, "complete", forbidden)


def _run(client, ws, **body):
    events = _events(client.post(f"/api/v1/workspaces/{ws}/crew", json=body).text)
    assert events[-1][0] == "done"
    return events, next((d for e, d in events if e == "result"), None)


def _trace(result):
    return {t["agent"]: t for t in result["trace"]}


def test_without_ai_the_facts_still_show(as_user, monkeypatch, research):
    _forbid_models(monkeypatch)
    alice, bob = as_user("alice"), as_user("bob")
    ws, other = _workspace(alice), _workspace(bob)
    for c, w, title in [(alice, ws, "Our archive"), (bob, other, "Secret archive")]:
        c.post(
            f"/api/v1/workspaces/{w}/sources",
            json={
                "title": title,
                "text": "Le port de Rio n'est pas fermé, selon le service maritime.",
            },
        )
    events, result = _run(alice, ws, text=PORT, ai_enabled=False)
    assert "analysis" not in result and result["ai_enabled"] is False
    assert result["results"] and [r["title"] for r in result["archives"]] == ["Our archive"]
    assert all(t["status"] == "no_ai" for t in result["trace"] if t["llm"])
    review = result["fact_checks"]
    assert [r["publisher"] for r in review] == ["AFP Factuel"] and review[0]["rating"] == "Faux"
    # the fact-checker's « Faux » backs the confidence without a model
    assert result["confidence"]["direction"] == "contradicts"
    assert result["tone"]["level"] == "neutre"
    agents = {d["agent"] for e, d in events if e == "agent"}
    assert {"Provenance", "Registre", "Chiffres", "Fact-checkers", "Web", "Archives"} <= agents
    assert {"Fiabilité", "Ton", "Éléments", "Confiance"} <= agents
    verdict_step = [d for e, d in events if e == "step" and d["key"] == "verdict"][-1]
    assert verdict_step == {"key": "verdict", "status": "waiting", "summary": "no_ai"}
    # the elements are counted once collected: fact-checkers' reviews and archives included
    search = [d for e, d in events if e == "step" and d["key"] == "search"]
    assert [d["status"] for d in search] == ["running", "done"]
    assert search[-1]["summary"] == f"{len(result['numbered'])} éléments trouvés"
    assert bob.post(f"/api/v1/workspaces/{ws}/crew", json={"text": "hello"}).status_code == 404


def test_pitch_rumour_without_registry_or_figures_modules(as_user, monkeypatch, research):
    _forbid_models(monkeypatch)
    alice = as_user("alice")
    ws = _workspace(alice)
    _, result = _run(alice, ws, text=DEMO_RUMOUR_TEXT, ai_enabled=False)
    trace = _trace(result)
    assert trace["Registre"]["status"] == "skipped"  # match_text is not wired yet
    assert trace["Chiffres"]["status"] == "skipped"
    assert result["tone"]["level"] == "sensationnaliste"
    quotes = {s["quote"] for s in result["signals"]}
    assert {"URGENT", "Partagez"} <= quotes
    assert result["risk"]["level"] == "high"
    assert "72 heures" in result["reading"]["numbers"] and "40 %" in result["reading"]["numbers"]
    assert "JIRAMA" in result["reading"]["institutions"]
    assert result["reading"]["location"]["region"] == "Analamanga"


def test_the_newsroom_setting_wins_over_the_run(as_user, monkeypatch, research):
    _forbid_models(monkeypatch)
    alice = as_user("alice")
    ws = _workspace(alice)
    alice.patch(f"/api/v1/workspaces/{ws}", json={"settings": {"ai_enabled": False}})
    _, result = _run(alice, ws, text=PORT, ai_enabled=True)
    assert result["ai_enabled"] is False and result["newsroom_ai"] is False


def test_model_failure_keeps_facts_visible(as_user, monkeypatch, research):
    async def unavailable(*args, **kwargs):
        raise ai.AiUnavailable(["groq: down"])

    monkeypatch.setattr(ai, "complete", unavailable)
    alice = as_user("alice")
    ws = _workspace(alice)
    events, result = _run(alice, ws, text=PORT)
    assert result["results"][0]["read_status"] == "read" and "analysis" not in result
    lecteur = _trace(result)["Lecteur"]
    assert lecteur["status"] == "failed" and lecteur["summary"] == "Modèles d'IA indisponibles"
    assert "groq" not in json.dumps(result["trace"])
    verdict = [d for e, d in events if e == "step" and d["key"] == "verdict"][-1]
    assert verdict == {"key": "verdict", "status": "waiting", "summary": "ai_failed"}


def test_a_failing_fact_node_never_breaks_the_stream(as_user, monkeypatch, research):
    _forbid_models(monkeypatch)

    async def broken(query, k=6):
        raise RuntimeError("boom")

    monkeypatch.setattr(websearch, "fact_checks", broken)
    alice = as_user("alice")
    ws = _workspace(alice)
    events, result = _run(alice, ws, text=PORT, ai_enabled=False)
    failed = _trace(result)["Fact-checkers"]
    assert failed["status"] == "failed" and failed["summary"] == "Échec (RuntimeError)"
    assert result["results"] and not any(e == "error" for e, _ in events)


@pytest.fixture
def scripted(monkeypatch):
    calls = []

    async def complete(messages, **kwargs):
        system = messages[0]["content"]
        calls.append(system[:20])
        if system.startswith("Tu es le Lecteur"):
            data = {
                "summary": PORT,
                "claims": [PORT],
                "entities": ["Rio"],
                "queries": ["port Rio fermé"],
                "numbers": ["99 %"],  # not in the text: dropped
                "places": ["Rio"],
                "language": "fr",
                "risk": {
                    "level": "medium",
                    "reasons": [
                        {"kind": "panic", "quote": "port de Rio est fermé"},
                        {"kind": "violence", "quote": "invented"},
                    ],
                },
                "framing": [],
            }
        elif system.startswith("Tu proposes"):
            data = {
                "verdict": "false",
                "reason": "Le port est annoncé ouvert.",
                "evidence": [
                    {"result": 1, "stance": "contradicts", "quote": "Le port de Rio est ouvert."},
                    {"result": 99, "stance": "supports", "quote": "Invented"},
                ],
                "missing": "Date de la fermeture alléguée.",
            }
        else:
            data = {
                "concerns": [
                    {"result": 1, "quote": "Le port de Rio est ouvert.", "why": "Date inconnue."},
                    {"result": 1, "quote": "Invented concern", "why": "fabricated"},
                ],
                "query": "capitainerie Rio fermeture port",
            }
        return SimpleNamespace(content=json.dumps(data), model="test-model", provider="test")

    async def no_geocode(db, text):
        return None

    monkeypatch.setattr(ai, "complete", complete)
    monkeypatch.setattr(crew.places, "geocode", no_geocode)
    return calls


def test_three_model_calls_quotes_bound_and_one_targeted_loop(
    as_user, monkeypatch, research, scripted
):
    alice = as_user("alice")
    ws = _workspace(alice)
    events, result = _run(alice, ws, text=PORT)
    assert len(scripted) == 3  # Lecteur, Synthèse, Contradicteur: the loop adds no model call
    analysis = result["analysis"]
    assert analysis["verdict"] == "false" and analysis["dropped_quotes"] == 1
    [evidence] = analysis["evidence"]
    assert evidence["source_title"] == "Annonce du port" and evidence["source_date"]
    assert analysis["claims"][0]["text"] == PORT and analysis["confidence"]["score"] > 0
    assert result["critique"] == [
        {"result": 1, "quote": "Le port de Rio est ouvert.", "why": "Date inconnue."}
    ]
    # the Contradicteur sent the Web search back once, with its own query
    assert result["loops"] == 1
    assert research["web"] == ["capitainerie Rio fermeture port"]
    assert result["recheck"]["results"][0]["url"] == "https://example.org/capitainerie"
    assert research["search"] == 1  # the first search is not run again
    assert research["queries"] == ["port Rio fermé", "port Rio fermé démenti"]
    synthesis = [d for e, d in events if e == "agent" and d["agent"] == "Synthèse"][-1]
    assert synthesis["summary"] == "Lecture suggérée : Faux"
    runs = [d["agent"] for e, d in events if e == "agent" and d["status"] == "running"]
    assert runs.count("Web") == 2 and runs.count("Registre") == 1 and runs.count("Synthèse") == 1
    # the risk keeps only reasons quoted from the text
    assert result["risk"]["by"] == "ai"
    assert {r["kind"] for r in result["risk"]["reasons"]} == {"panic"}
    assert "99 %" not in result["reading"]["numbers"]
    assert alice.get(f"/api/v1/workspaces/{ws}/items").json()["total"] == 0
    steps = [d for e, d in events if e == "step"]
    assert {"key": "verdict", "status": "done", "summary": "false"} in steps


def test_registry_and_figures_contracts_feed_the_facts(as_user, monkeypatch, research):
    _forbid_models(monkeypatch)
    from app.modules import figures, registry

    original = "Délestage de 4 heures par jour et par quartier du 3 au 9 novembre à Antananarivo."

    async def match_text(db, workspace_id, text):
        return {
            "status": "modified",
            "issuer": "JIRAMA",
            "number": "2026-118",
            "communique": {
                "text": original,
                "url": "https://www.jirama.mg/118",
                "issued_on": "2026-11-01",
            },
            "diff": [{"op": "replace", "a": "4 heures par jour", "b": "72 heures"}],
            "summary": "Le communiqué N° 2026-118 dit 4 heures par jour, pas 72 heures",
        }

    async def check_numbers(db, workspace_id, text, location=None):
        return [
            {
                "claimed": "40 %",
                "context": "hausse de 40 % du tarif",
                "figure": {
                    "label": "Tarif électricité",
                    "value": "+12",
                    "unit": "%",
                    "as_of": "2026-10-15",
                    "source_name": "ORE (démo)",
                    "source_url": "https://ore.mg/tarifs",
                    "age_days": 18,
                    "old": False,
                },
                "verdict": "differs",
            }
        ]

    monkeypatch.setattr(registry, "match_text", match_text, raising=False)
    monkeypatch.setattr(figures, "check_numbers", check_numbers, raising=False)
    alice = as_user("alice")
    ws = _workspace(alice)
    _, result = _run(alice, ws, text=DEMO_RUMOUR_TEXT, ai_enabled=False)
    trace = _trace(result)
    assert trace["Registre"]["summary"].startswith("Le communiqué N° 2026-118")
    assert trace["Chiffres"]["summary"] == "1 chiffre(s) différent(s) du chiffre officiel"
    kinds = {r["kind"]: r for r in result["numbered"]}
    assert kinds["registry"]["passages"] == [original]
    assert kinds["figure"]["snippet"] == "Tarif électricité : +12 % (ORE (démo))"
    score = result["confidence"]
    assert score["direction"] == "contradicts" and score["level"] in ("eleve", "moyen")
    assert {c["key"]: c["points"] for c in score["components"]}["official"] == 25


def test_provenance_flags_an_old_picture_shared_as_new():
    page = {
        "kind": "image",
        "final_url": "https://images.example/delestage.jpg",
        "image": {"exif": {"DateTimeOriginal": "2023:03:14 21:10:00"}, "ai_markers": []},
    }
    found = asyncio.run(crew.provenance_of(page, "Ce soir tout Tana est dans le noir"))
    assert found["first_seen"] == "2023-03-14" and found["first_seen_basis"] == "exif"
    assert found["verdict_hint"] == "old_media_new_caption"
    assert [link["name"] for link in found["reverse_links"]] == ["Google Lens", "TinEye", "Yandex"]
    assert asyncio.run(crew.provenance_of({"kind": "text"}, "Bonjour")) is None


def test_public_facts_has_no_reading_and_finds_signed_verdicts(as_user, research):
    alice = as_user("alice")
    ws, _ = _newsroom(alice)
    _claim(alice, ws, "Le port de Rio est fermé", verdict="false", reason="Le port est ouvert.")

    async def run():
        async with SessionLocal() as db:
            return await crew.public_facts(db, PORT)

    facts = asyncio.run(run())
    assert "analysis" not in facts and "confidence" not in facts
    assert facts["published"][0]["verdict"] == "false"
    assert facts["published"][0]["newsroom"] == "Desk du matin"
    assert facts["fact_checks"][0]["publisher"] == "AFP Factuel"
    assert facts["tone"]["level"] == "neutre" and facts["registry"] is None


def test_a_reason_the_model_quotes_longer_replaces_the_codes_shorter_one():
    from app.core import tone

    code = tone.risk(DEMO_RUMOUR_TEXT)
    model = {
        "level": "high",
        "reasons": [{"kind": "fake_order", "quote": "COMMUNIQUÉ N° 2026-118 de la JIRAMA"}],
    }
    merged = crew.merge_risk(code, model, DEMO_RUMOUR_TEXT)
    orders = [r["quote"] for r in merged["reasons"] if r["kind"] == "fake_order"]
    assert orders == ["COMMUNIQUÉ N° 2026-118 de la JIRAMA"]
    assert {r["kind"] for r in merged["reasons"]} == {"fake_order", "panic"}


def test_a_failed_recheck_keeps_the_first_search(as_user, monkeypatch, research, scripted):
    async def down(query, k=6):
        raise websearch.SearchUnavailable("blocked")

    monkeypatch.setattr(websearch, "web", down)
    alice = as_user("alice")
    ws = _workspace(alice)
    events, result = _run(alice, ws, text=PORT)
    web = [d for e, d in events if e == "agent" and d["agent"] == "Web"]
    assert [d["status"] for d in web] == ["running", "done", "running", "skipped"]
    assert web[-1]["summary"] == "Recherche ciblée indisponible"
    assert result["results"][0]["read_status"] == "read" and "recheck" not in result


def test_archives_share_a_name_with_the_message(as_user, monkeypatch, research):
    _forbid_models(monkeypatch)
    alice = as_user("alice")
    ws = _workspace(alice)
    for title, text in [
        ("Calendrier", "Les épreuves commencent à partir du 24 novembre 2026, sur tout le pays."),
        ("Toamasina", "La JIRAMA annonce un délestage de 4 heures à Toamasina."),
    ]:
        alice.post(f"/api/v1/workspaces/{ws}/sources", json={"title": title, "text": text})
    _, result = _run(alice, ws, text=DEMO_RUMOUR_TEXT, ai_enabled=False)
    assert [a["title"] for a in result["archives"]] == ["Toamasina"]
