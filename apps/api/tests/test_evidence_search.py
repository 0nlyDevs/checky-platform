import asyncio

import httpx

from app.core import evidence_search, query_plan, websearch
from app.workers import ingest
from tests.test_query_plan import PARC


def plan():
    return query_plan.Preparation(
        method="ai",
        claims=["La compétition se tiendra du 3 au 7 novembre."],
        entities=["MAZAVALOHA", "PARC", "2026"],
        queries=["MAZAVALOHA PARC 2026"],
    )


def test_failure_is_not_an_empty_success(monkeypatch):
    async def blocked(*args):
        raise websearch.SearchUnavailable("challenge", reason="blocked")

    for name in ("web", "fact_checks", "wikipedia"):
        monkeypatch.setattr(websearch, name, blocked)
    report = asyncio.run(evidence_search.search(plan()))
    assert report.status == "unavailable" and report.sources == []
    assert {attempt.status for attempt in report.attempts} == {"blocked"}


def test_parc_robotics_search_does_not_keep_unrelated_golf_competitions():
    prepared = plan().model_copy(
        update={
            "entities": [
                "MAZAVALOHA",
                "Pan-African Robotics Competition (PARC) 2026",
                "Dakar",
                "Madagascar",
            ]
        }
    )
    golf = evidence_search.ResearchSource(
        n=1,
        kind="web",
        title="Golf Parc compétition 2026",
        url="https://golf.example/2026",
        snippet="Calendrier des compétitions de golf de mars à novembre.",
    )
    robotics = golf.model_copy(
        update={
            "title": "PARC 2026 Pan-African Robotics Competition",
            "snippet": "Robotics in Dakar November 3–7.",
        }
    )
    assert not evidence_search.relevant(golf, prepared)
    assert evidence_search.relevant(robotics, prepared)


def test_successful_empty_results_and_partial_searches_are_distinct(monkeypatch):
    async def empty(*args):
        return []

    for name in ("web", "fact_checks", "wikipedia"):
        monkeypatch.setattr(websearch, name, empty)
    assert asyncio.run(evidence_search.search(plan())).status == "empty"

    async def web(*args):
        return [
            {
                "url": "https://news.example/a?utm_source=x",
                "title": "MAZAVALOHA PARC 2026",
                "snippet": "A source to read.",
            },
            {"url": "https://news.example/a", "title": "Same source", "snippet": "x"},
        ]

    async def failed(*args):
        raise websearch.SearchUnavailable("timeout", reason="timeout")

    monkeypatch.setattr(websearch, "web", web)
    monkeypatch.setattr(websearch, "wikipedia", failed)
    report = asyncio.run(evidence_search.search(plan()))
    assert report.status == "partial" and len(report.sources) == 1
    assert report.sources[0].url == "https://news.example/a"


def test_source_reading_returns_literal_passages_and_flags_republication(monkeypatch):
    text = query_plan.clean_text(PARC)
    monkeypatch.setattr(ingest, "_resolve", lambda _: ["93.184.216.34"])
    monkeypatch.setattr(
        ingest,
        "_transport",
        httpx.MockTransport(
            lambda _: httpx.Response(200, text=text, headers={"Content-Type": "text/plain"})
        ),
    )
    sources = [
        evidence_search.ResearchSource(
            n=n, kind="web", title="PARC", url=f"https://news{n}.example/a", snippet="x"
        )
        for n in (1, 2)
    ]
    asyncio.run(evidence_search.read_sources(sources, plan(), text))
    assert all(source.read_status == "read" and source.wording_overlap for source in sources)
    assert sources[0].similar_to == [2] and sources[1].similar_to == [1]
    assert all(passage in text for source in sources for passage in source.passages)


def test_an_unreadable_source_keeps_its_search_snippet_without_claiming_it_was_read(monkeypatch):
    monkeypatch.setattr(ingest, "_resolve", lambda _: ["93.184.216.34"])
    monkeypatch.setattr(ingest, "_transport", httpx.MockTransport(lambda _: httpx.Response(403)))
    source = evidence_search.ResearchSource(
        n=1, kind="web", title="PARC", url="https://news.example/a", snippet="Search snippet"
    )
    asyncio.run(evidence_search.read_sources([source], plan(), "original"))
    assert (
        source.read_status == "blocked"
        and source.passages == []
        and source.snippet == "Search snippet"
    )
