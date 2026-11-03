import httpx
import pytest

from app.core import evidence_search, query_plan
from app.core.config import get_settings
from app.core.public_checks import budget
from app.modules import linkcheck
from app.workers import ingest
from tests.test_agent import _events
from tests.test_imagecheck import png
from tests.test_public import _claim, _newsroom


@pytest.fixture
def evidence(monkeypatch):
    seen = []

    async def prepare(text):
        return query_plan.Preparation(method="fallback", summary=text[:500], queries=[text[:160]])

    async def search(plan, skip):
        seen.append((plan.queries[0], skip))
        return evidence_search.SearchReport(
            status="ok",
            attempts=[],
            sources=[
                evidence_search.ResearchSource(
                    n=1,
                    kind="fact-check",
                    title="Public evidence",
                    url="https://factuel.example/checked",
                    snippet="A passage to read.",
                )
            ],
        )

    async def read(*args):
        return None

    monkeypatch.setattr(query_plan, "prepare", prepare)
    monkeypatch.setattr(evidence_search, "search", search)
    monkeypatch.setattr(evidence_search, "read_sources", read)
    return seen


def test_anonymous_check_only_exposes_published_confirmed_public_verdicts(
    client, as_user, evidence
):
    alice, bob = as_user("alice"), as_user("bob")
    ws, _ = _newsroom(alice)
    private, _ = _newsroom(bob, public=False)
    title = "Une vidéo montre une inondation à Analakely"
    shown = _claim(alice, ws, title, reason="La vidéo est ancienne.")
    _claim(alice, ws, title + " brouillon secret", status="in_progress")
    assert (
        alice.post(
            f"/api/v1/workspaces/{ws}/items",
            json={
                "title": title + " suggestion secrète",
                "status": "published",
                "data": {"verdict_suggested": "true"},
            },
        ).status_code
        == 409
    )
    _claim(bob, private, title + " rédaction privée")
    response = client.post("/api/v1/public/check", json={"text": title})
    assert response.status_code == 200
    result = response.json()
    assert [item["id"] for item in result["published"]] == [shown]
    assert result["published"][0]["reason"] == "La vidéo est ancienne."
    assert result["results"][0]["url"] == "https://factuel.example/checked"
    assert "analysis" not in result and "tracked" not in result and "verdict" not in result
    assert not any(
        word in response.text
        for word in ("brouillon secret", "suggestion secrète", "rédaction privée")
    )
    assert evidence == [(title, None)]
    assert len(alice.get(f"/api/v1/workspaces/{ws}/items").json()["items"]) == 2


def test_a_new_claim_has_sources_but_no_invented_verdict(client, evidence):
    result = client.post("/api/v1/public/check", json={"text": "Le pont d’Anosy est fermé"}).json()
    assert result["published"] == [] and len(result["results"]) == 1
    assert "verdict" not in result and "claims" not in result
    assert budget.active == 0


def test_public_stream_reports_real_stages_and_requires_no_account(client, evidence):
    response = client.post("/api/v1/public/check/stream", json={"text": "Le pont est fermé"})
    assert response.status_code == 200
    events = _events(response.text)
    assert [
        data["key"] for event, data in events if event == "step" and data["status"] == "running"
    ] == ["read", "claims", "search", "verdict"]
    prepared = next(data for event, data in events if event == "preparation")
    assert prepared["queries"] == ["Le pont est fermé"]
    result = next(data for event, data in events if event == "result")
    assert result["search_status"] == "ok" and result["preparation"] == prepared
    assert events[-1][0] == "done" and "analysis" not in result and budget.active == 0


def test_search_failures_stay_visible_in_the_response(client, evidence, monkeypatch):
    async def unavailable(*args):
        return evidence_search.SearchReport(
            status="unavailable",
            attempts=[evidence_search.SearchAttempt(kind="web", query="Le pont", status="blocked")],
            sources=[],
        )

    monkeypatch.setattr(evidence_search, "search", unavailable)
    result = client.post("/api/v1/public/check", json={"text": "Le pont est fermé"}).json()
    assert result["search_status"] == "unavailable" and result["results"] == []
    assert result["searches"][0]["status"] == "blocked"


def test_selected_text_does_not_fetch_the_whole_page(client, evidence, monkeypatch):
    async def unexpected(_):
        pytest.fail("A pasted passage must not trigger fetching its surrounding page")

    monkeypatch.setattr(linkcheck, "read_link", unexpected)
    response = client.post(
        "/api/v1/public/check",
        json={
            "text": "Le pont est fermé",
            "url": "https://page.example/unrelated",
        },
    )
    assert response.status_code == 200


def test_public_link_can_be_read_and_private_payloads_are_rejected(client, evidence, monkeypatch):
    async def page(url):
        return {
            "kind": "page",
            "title": "Le pont d’Anosy",
            "text": "Le pont est fermé",
            "final_url": url,
            "published_at": "2019-01-14",
        }

    monkeypatch.setattr(linkcheck, "read_link", page)
    result = client.post("/api/v1/public/check", json={"url": "https://page.example/a"}).json()
    assert result["published_at"] == "2019-01-14" and result["days_old"] > 1000
    assert evidence[0] == ("Le pont est fermé", "https://page.example/a")
    for body in (
        {},
        {"text": "x"},
        {"text": "a" * 6001},
        {"url": "file:///etc/passwd"},
        {"text": "hello", "source_id": "private"},
        {"text": "hello", "workspace_id": "private"},
    ):
        assert client.post("/api/v1/public/check", json=body).status_code == 422
    assert budget.active == 0


def test_unreadable_link_is_a_bounded_error_and_releases_its_slot(client, evidence, monkeypatch):
    async def failed(_):
        raise ValueError("Private or inaccessible address")

    monkeypatch.setattr(linkcheck, "read_link", failed)
    assert (
        client.post("/api/v1/public/check", json={"url": "http://localhost/secret"}).status_code
        == 422
    )
    assert budget.active == 0


def test_public_image_works_without_auth_or_a_pixel_detector(client, monkeypatch):
    monkeypatch.setattr(ingest, "_resolve", lambda _: ["93.184.216.34"])
    monkeypatch.setattr(
        ingest,
        "_transport",
        httpx.MockTransport(
            lambda _: httpx.Response(
                200, content=png("Stable Diffusion"), headers={"Content-Type": "image/png"}
            )
        ),
    )
    result = client.post("/api/v1/public/image-check", json={"url": "https://images.example/a.png"})
    assert result.status_code == 200
    assert result.json()["assessment"] == "detected"
    assert "detector" not in result.json()
    assert budget.active == 0


def test_public_image_file_works_without_auth_or_storage(client, monkeypatch):
    endpoint = "/api/v1/public/image-check/file"
    result = client.post(
        endpoint, content=png("Stable Diffusion"), headers={"Content-Type": "image/png"}
    )
    assert result.status_code == 200
    assert result.json()["source"] == "file" and result.json()["url"] is None
    assert result.json()["assessment"] == "detected"
    assert "detector" not in result.json()
    assert (
        client.post(
            endpoint, content=b"<svg/>", headers={"Content-Type": "image/svg+xml"}
        ).status_code
        == 415
    )
    assert (
        client.post(
            endpoint,
            content=png(),
            headers={"Content-Type": "image/png", "Content-Length": str(6 * 1024 * 1024)},
        ).status_code
        == 413
    )
    assert budget.active == 0


def test_public_text_and_images_share_ip_daily_and_concurrency_budgets(
    client, evidence, monkeypatch
):
    settings = get_settings()
    monkeypatch.setattr(settings, "public_checks_per_window", 1)
    assert (
        client.post("/api/v1/public/check", json={"text": "Le pont est fermé"}).status_code == 200
    )
    assert (
        client.post(
            "/api/v1/public/image-check", json={"url": "https://image.example/a.png"}
        ).status_code
        == 429
    )
    budget.reset()
    monkeypatch.setattr(settings, "public_checks_per_day", 0)
    assert (
        client.post("/api/v1/public/check", json={"text": "Une autre affirmation"}).status_code
        == 429
    )
    assert budget.active == 0
    monkeypatch.setattr(settings, "public_checks_per_day", 1000)
    budget.active = settings.public_checks_concurrency
    assert (
        client.post("/api/v1/public/check", json={"text": "Une autre affirmation"}).status_code
        == 429
    )
    budget.reset()


def test_anonymous_access_cannot_write_or_call_private_analysis(client, as_user, evidence):
    ws, _ = _newsroom(as_user("alice"))
    assert (
        client.post(
            f"/api/v1/workspaces/{ws}/copilot/act", json={"kind": "create_claim", "title": "x"}
        ).status_code
        == 401
    )
    assert (
        client.post(f"/api/v1/workspaces/{ws}/link-check", json={"text": "hello"}).status_code
        == 401
    )
