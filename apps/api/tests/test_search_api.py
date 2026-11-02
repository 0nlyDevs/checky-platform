import asyncio
import json

import httpx
import pytest

from app.core import websearch
from app.core.config import get_settings

USAGE = {
    "account": {
        "current_plan": "Researcher",
        "plan_limit": 1000,
        "plan_usage": 10,
        "paygo_limit": 0,
        "paygo_usage": 0,
    },
    "key": {"limit": 1000, "usage": 10},
}
RESULTS = {
    "results": [
        {
            "title": "PARC 2026",
            "url": "https://www.parcrobotics.org/",
            "content": "Competition in Dakar.",
            "score": 0.99,
        },
        {"title": "Unsafe", "url": "javascript:alert(1)", "content": "never opened"},
    ]
}


@pytest.fixture
def api(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "web_search_provider", "auto")
    monkeypatch.setattr(settings, "tavily_api_key", "tvly-test-not-real")
    monkeypatch.setattr(settings, "google_factcheck_api_key", "")
    seen = []
    state = {"usage": USAGE, "results": RESULTS, "status": 200}

    def handle(request):
        assert request.url.host == "api.tavily.com"
        assert request.headers["authorization"] == "Bearer tvly-test-not-real"
        seen.append(request)
        if request.url.path == "/usage":
            return httpx.Response(200, json=state["usage"])
        assert request.url.path == "/search"
        return httpx.Response(state["status"], json=state["results"])

    monkeypatch.setattr(websearch, "_transport", httpx.MockTransport(handle))
    return state, seen


def test_configured_api_replaces_html_scraping_with_basic_search_and_verified_free_usage(api):
    _, seen = api
    found = asyncio.run(websearch.web("MAZAVALOHA PARC 2026"))
    assert found == [
        {
            "title": "PARC 2026",
            "url": "https://www.parcrobotics.org/",
            "snippet": "Competition in Dakar.",
        }
    ]
    assert [request.url.path for request in seen] == ["/usage", "/search"]
    body = json.loads(seen[1].content)
    assert body["search_depth"] == "basic" and body["auto_parameters"] is False
    assert body["include_answer"] is False and body["include_raw_content"] is False
    assert "api_key" not in body and "score" not in found[0]
    assert asyncio.run(websearch.web("MAZAVALOHA PARC 2026")) == found
    assert len(seen) == 2  # repeat lookup is served from the result cache


@pytest.mark.parametrize(
    "account",
    [
        {**USAGE["account"], "current_plan": "Project", "plan_limit": 4000},
        {**USAGE["account"], "paygo_limit": 100},
        {**USAGE["account"], "plan_usage": 1000},
        {"current_plan": "Researcher", "plan_limit": 1000, "plan_usage": 0},
    ],
)
def test_paid_overage_exhausted_or_unverifiable_accounts_do_not_issue_a_search(api, account):
    state, seen = api
    state["usage"] = {**USAGE, "account": account}
    with pytest.raises(websearch.SearchUnavailable):
        asyncio.run(websearch.web("MAZAVALOHA PARC 2026"))
    assert [request.url.path for request in seen] == ["/usage"]


@pytest.mark.parametrize("status", [401, 403, 429, 432, 500])
def test_api_errors_never_retry_a_credit_consuming_post_or_leak_a_key(api, status):
    state, seen = api
    state["status"] = status
    with pytest.raises(websearch.SearchUnavailable) as error:
        asyncio.run(websearch.web("MAZAVALOHA PARC 2026"))
    assert "tvly-test-not-real" not in str(error.value)
    assert [request.url.path for request in seen] == ["/usage", "/search"]
    assert not websearch._cache


def test_fact_checker_search_uses_api_domain_filters_instead_of_a_fragile_html_query(api):
    state, seen = api
    state["results"] = {
        "results": [
            {"title": "Checked", "url": "https://factuel.afp.com/article", "content": "Evidence."}
        ]
    }
    found = asyncio.run(websearch.fact_checks("Madagascar OMS"))
    body = json.loads(seen[-1].content)
    assert "factuel.afp.com" in body["include_domains"]
    assert "site:" not in body["query"] and found[0]["url"].startswith("https://factuel.afp.com/")


def test_explicit_api_selection_without_a_key_does_not_make_a_network_request(monkeypatch):
    monkeypatch.setattr(get_settings(), "web_search_provider", "tavily")
    monkeypatch.setattr(get_settings(), "tavily_api_key", "")
    monkeypatch.setattr(
        websearch,
        "_transport",
        httpx.MockTransport(lambda _: pytest.fail("No request without a key")),
    )
    with pytest.raises(websearch.SearchUnavailable, match="not configured"):
        asyncio.run(websearch.web("MAZAVALOHA PARC 2026"))


@pytest.mark.parametrize(
    "payload", [{}, {"results": "bad"}, {"results": [{"url": "javascript:alert(1)"}]}]
)
def test_invalid_results_are_not_cached_as_a_successful_empty_search(api, payload):
    state, _ = api
    state["results"] = payload
    with pytest.raises(websearch.SearchUnavailable):
        asyncio.run(websearch.web("MAZAVALOHA PARC 2026"))
    assert not websearch._cache


def test_an_explicit_empty_results_array_is_a_valid_cached_empty_search(api):
    state, seen = api
    state["results"] = {"results": []}
    assert asyncio.run(websearch.web("a subject without indexed results")) == []
    assert asyncio.run(websearch.web("a subject without indexed results")) == []
    assert len(seen) == 2


def test_api_redirects_are_not_followed_with_the_server_credential(api, monkeypatch):
    _, seen = api

    def redirect(request):
        seen.append(request)
        return httpx.Response(302, headers={"location": "https://untrusted.example/collect"})

    monkeypatch.setattr(websearch, "_transport", httpx.MockTransport(redirect))
    with pytest.raises(websearch.SearchUnavailable):
        asyncio.run(websearch.web("MAZAVALOHA PARC 2026"))
    assert len(seen) == 1 and seen[0].url.host == "api.tavily.com"


def test_fact_checker_labels_reject_lookalike_hosts_and_unrelated_sections():
    assert websearch._fact_checker_url("https://factuel.afp.com/article")
    assert websearch._fact_checker_url("https://www.lemonde.fr/les-decodeurs/article")
    assert not websearch._fact_checker_url("https://factuel.afp.com.attacker.example/article")
    assert not websearch._fact_checker_url("https://news.example/?url=//factuel.afp.com/article")
    assert not websearch._fact_checker_url("https://www.lemonde.fr/sport/article")
