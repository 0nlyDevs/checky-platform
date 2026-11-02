"""The layered public check: a signed verdict first, then a fact-checker's review (relayed as
theirs), then the facts alone; never a model verdict, never a percentage."""

import json

import pytest
from fastapi.testclient import TestClient

from app.core import websearch
from app.core.config import get_settings
from app.main import app

RUMOUR = (
    "URGENT ⚠️ COMMUNIQUÉ N° 2026-118 de la JIRAMA : délestage de 72 heures à partir du 3 novembre "
    "sur tout Antananarivo, hausse de 40 % du tarif en décembre. Partagez à tous vos contacts !!!"
)
CLAIM = "72 heures de délestage dès demain sur tout Antananarivo, selon la JIRAMA"


@pytest.fixture(autouse=True)
def _fresh_limits():
    from app.modules import verify_public

    verify_public._NOTIFY.clear()  # conftest does not know this module's per-address limit


@pytest.fixture
def secret(monkeypatch):
    monkeypatch.setattr(get_settings(), "seal_secret", "test-seal-secret-for-contacts")


@pytest.fixture
def no_reviews(monkeypatch):
    async def none(query, k=6):
        return []

    monkeypatch.setattr(websearch, "fact_checks", none)


def _newsroom(c, public=True):
    ws = c.post("/api/v1/workspaces", json={"name": "Desk du matin"}).json()["id"]
    if public:
        c.patch(f"/api/v1/workspaces/{ws}", json={"is_public": True})
    return ws


def _claim(c, ws, title, status="published", verdict="false", **data):
    data = {"ref": "FAN-0145", **({"verdict": verdict} if verdict else {}), **data}
    r = c.post(
        f"/api/v1/workspaces/{ws}/items", json={"title": title, "status": status, "data": data}
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_signed_verdict_comes_first_with_its_confidence_in_words(as_user, monkeypatch):
    async def never(query, k=6):
        raise AssertionError("a signed verdict needs no outside search")

    monkeypatch.setattr(websearch, "fact_checks", never)
    alice = as_user("alice")
    ws = _newsroom(alice)
    item = _claim(
        alice,
        ws,
        CLAIM,
        reason="Le communiqué N° 2026-118 annonce 4 heures par jour, pas 72 heures.",
        verdict_suggested="false",
        analysis={"confidence": {"score": 84, "level": "eleve", "reasons": ["…"]}},
    )
    r = TestClient(app).post("/api/v1/public/verify", json={"text": RUMOUR})
    out = r.json()
    assert r.status_code == 200 and out["status"] == "signed"
    assert out["signed"]["id"] == item and out["signed"]["verdict"] == "false"
    assert out["signed"]["confidence"] == "eleve"
    # the percentage behind the level never leaves the newsroom
    raw = json.dumps(out)
    assert "score" not in raw and ": 84" not in raw and "84 %" not in raw and "%" not in raw


def test_no_confidence_when_the_journalist_signed_another_verdict(as_user, no_reviews):
    alice = as_user("alice")
    ws = _newsroom(alice)
    _claim(
        alice,
        ws,
        CLAIM,
        verdict="misleading",
        verdict_suggested="false",
        analysis={"confidence": {"score": 84, "level": "eleve"}},
    )
    out = TestClient(app).post("/api/v1/public/verify", json={"text": RUMOUR}).json()
    assert out["status"] == "signed" and out["signed"]["confidence"] is None


def test_a_fact_checkers_review_is_relayed_as_theirs(as_user, monkeypatch):
    async def reviews(query, k=6):
        assert "jirama" in query and "urgent" in query
        return [
            {
                "title": "Non, la JIRAMA n'annonce pas 72 heures de délestage à Antananarivo",
                "url": "https://factuel.afp.com/doc.afp.com.36XY",
                "snippet": "AFP Factuel : « Faux ». Affirmation : 72 heures de délestage",
                "date": "2026-10-30T10:00:00Z",
            },
            {
                "title": "Did the moon landing happen?",
                "url": "https://www.snopes.com/fact-check/moon/",
                "snippet": "",
            },
        ]

    monkeypatch.setattr(websearch, "fact_checks", reviews)
    out = TestClient(app).post("/api/v1/public/verify", json={"text": RUMOUR}).json()
    assert out["status"] == "external" and out["signed"] is None
    assert out["external"] == [
        {
            "publisher": "AFP Factuel",
            "url": "https://factuel.afp.com/doc.afp.com.36XY",
            "rating": "Faux",
            "date": "2026-10-30",
            "title": "Non, la JIRAMA n'annonce pas 72 heures de délestage à Antananarivo",
        }
    ]


def test_facts_alone_from_the_registry(as_user, no_reviews, monkeypatch):
    from app.modules import registry

    async def match_text(db, workspace_id, text):
        assert workspace_id is not None
        return {
            "status": "modified",
            "issuer": "JIRAMA",
            "number": "N° 2026-118",
            "communique": {"issued_on": "2026-11-01", "url": None},
            "diff": [{"op": "replace", "a": "4 heures", "b": "72 heures"}],
            "summary": "Le communiqué N° 2026-118 existe, mais il annonce 4 heures, pas 72.",
        }

    monkeypatch.setattr(registry, "match_text", match_text, raising=False)
    alice = as_user("alice")
    _newsroom(alice)
    out = TestClient(app).post("/api/v1/public/verify", json={"text": RUMOUR}).json()
    assert out["status"] == "facts" and out["signed"] is None
    fact = out["known"][0]
    assert fact["kind"] == "registry" and fact["date"] == "2026-11-01"
    assert fact["diff"][0]["b"] == "72 heures" and "4 heures" in fact["text"]
    assert out["search_status"] == "done" and out["followed_since"] is None


def test_a_followed_rumour_gives_the_hour_and_the_newsroom_only(as_user, no_reviews):
    alice = as_user("alice")
    ws = _newsroom(alice)
    item = _claim(alice, ws, CLAIM, status="to_check", verdict=None)
    anon = TestClient(app)
    out = anon.post("/api/v1/public/verify", json={"text": CLAIM}).json()
    assert out["status"] == "facts" and out["followed_by"] == "Desk du matin"
    assert out["followed_since"].endswith(("00:00Z", "00:00+00:00"))
    raw = json.dumps(out)
    assert item not in raw and "FAN-0145" not in raw and "selon la JIRAMA" not in raw
    # nobody probes a draft title word by word
    for probe in ("délestage Antananarivo", "délestage Antananarivo pomme banane rouge"):
        out = anon.post("/api/v1/public/verify", json={"text": probe}).json()
        assert out["status"] == "none" and out["followed_since"] is None
    # a public tip is not « followed » (anyone could have sent it)
    _claim(
        alice,
        ws,
        "Le pont de Mangasoavina serait fermé jusqu'à lundi",
        status="to_check",
        verdict=None,
        public_tip=True,
    )
    out = anon.post(
        "/api/v1/public/verify", json={"text": "Le pont de Mangasoavina serait fermé jusqu'à lundi"}
    ).json()
    assert out["followed_since"] is None


def test_the_crews_fact_agents_answer_when_they_are_there(monkeypatch):
    from app.modules import crew

    async def public_facts(db, text, url):
        return {
            "provenance": {"first_seen": "2023-03-14", "verdict_hint": "old_media_new_caption"},
            "tone": {"level": "sensationnaliste", "signals": [{"kind": "caps", "quote": "URGENT"}]},
            "fact_checks": [],
            "analysis": {"verdict": "false"},  # never relayed: a model's reading stays inside
        }

    monkeypatch.setattr(crew, "public_facts", public_facts, raising=False)
    out = TestClient(app).post("/api/v1/public/verify", json={"text": RUMOUR}).json()
    assert out["status"] == "facts"
    kinds = [f["kind"] for f in out["known"]]
    assert kinds == ["provenance", "tone"]
    assert "14 mars 2023" in out["known"][0]["text"] and "« URGENT »" in out["known"][1]["text"]
    assert "analysis" not in out["facts"] and out["followed_since"] is None


def test_nothing_known_says_so_and_reports_the_search_outage(monkeypatch):
    async def down(query, k=6):
        raise websearch.SearchUnavailable("ConnectError")

    monkeypatch.setattr(websearch, "fact_checks", down)
    out = TestClient(app).post("/api/v1/public/verify", json={"text": "le pont est fermé"}).json()
    assert out["status"] == "none" and out["search_status"] == "unavailable"
    assert TestClient(app).post("/api/v1/public/verify", json={"text": "a"}).status_code == 422


def test_a_link_alone_is_read_first(as_user, no_reviews, monkeypatch):
    from app.modules import linkcheck

    async def read_link(url):
        return {"text": RUMOUR, "title": "Post"}

    monkeypatch.setattr(linkcheck, "read_link", read_link)
    alice = as_user("alice")
    _claim(alice, _newsroom(alice), CLAIM)
    out = (
        TestClient(app)
        .post("/api/v1/public/verify", json={"url": "https://example.org/post/1"})
        .json()
    )
    assert out["status"] == "signed"


def test_notify_needs_the_secret_and_keeps_contacts_masked(as_user, monkeypatch):
    monkeypatch.setattr(get_settings(), "seal_secret", "")
    anon = TestClient(app)
    body = {"text": CLAIM + " ?", "contact": "034 00 000 12"}
    assert anon.post("/api/v1/public/notify", json=body).status_code == 503
    monkeypatch.setattr(get_settings(), "seal_secret", "test-seal-secret-for-contacts")
    # no newsroom answers the public yet: nothing is stored anywhere
    assert anon.post("/api/v1/public/notify", json=body).status_code == 409
    alice = as_user("alice")
    ws = _newsroom(alice)
    item = _claim(alice, ws, CLAIM, status="to_check", verdict=None)
    r = anon.post("/api/v1/public/notify", json=body)
    assert r.status_code == 201
    assert r.json() == {"masked": "+261 34 •• ••• 12", "channel": "sms", "followed": True}
    assert anon.post("/api/v1/public/notify", json=body).status_code == 201  # not stored twice
    email = {
        "text": "Appelez le 034 00 000 99 ou c.rabe@example.org : 72 heures à Antananarivo ?",
        "contact": "C.Rabe@example.org",
        "item_id": item,
    }
    assert anon.post("/api/v1/public/notify", json=email).json()["masked"] == "c•••@example.org"
    assert anon.post("/api/v1/public/notify", json=body).status_code == 429  # 5 per 10 minutes
    from app.modules import verify_public

    verify_public._NOTIFY.clear()
    bad = {"text": RUMOUR, "contact": "pas un numéro"}
    assert anon.post("/api/v1/public/notify", json=bad).status_code == 422
    groups = alice.get(f"/api/v1/workspaces/{ws}/questions").json()
    assert len(groups) == 1
    g = groups[0]
    assert g["count"] == 2 and g["waiting"] == 2 and g["item_ref"] == "FAN-0145"
    assert g["regions"] == {"Analamanga": 2} and g["channels"] == {"web": 2}
    # nothing in clear for the desk, not even inside the question's own words
    raw = json.dumps(groups)
    assert "000 12" not in raw and "000 99" not in raw and "rabe" not in raw.lower()


def test_questions_are_grouped_and_stay_with_their_newsroom(as_user, secret):
    alice, bob = as_user("alice"), as_user("bob")
    ws = _newsroom(alice)
    other = _newsroom(bob)  # a second public newsroom, created later
    anon = TestClient(app)
    for text, phone in [
        ("Est-ce vrai, 72 heures de délestage à Antananarivo ?", "0340000001"),
        ("délestage de 72 heures à Antananarivo selon la JIRAMA ??", "0340000002"),
        ("Le bac est reporté à Toliara ?", "0340000003"),
    ]:
        r = anon.post("/api/v1/public/notify", json={"text": text, "contact": phone})
        assert r.status_code == 201
    groups = alice.get(f"/api/v1/workspaces/{ws}/questions").json()
    assert sorted(g["count"] for g in groups) == [1, 2]
    toliara = alice.get(f"/api/v1/workspaces/{ws}/questions?region=atsimo-andrefana").json()
    assert [g["count"] for g in toliara] == [1]
    # every question went to one newsroom: the other public newsroom sees none of them
    assert bob.get(f"/api/v1/workspaces/{other}/questions").json() == []
    # until it declares Toliara's region as its home: questions from there now reach it
    bob.patch(f"/api/v1/workspaces/{other}", json={"settings": {"region": "Atsimo-Andrefana"}})
    r = anon.post(
        "/api/v1/public/notify",
        json={"text": "Le bac est reporté à Toliara ?", "contact": "0340000004"},
    )
    assert r.status_code == 201
    assert [g["count"] for g in bob.get(f"/api/v1/workspaces/{other}/questions").json()] == [1]
    private = _newsroom(alice, public=False)
    assert alice.get(f"/api/v1/workspaces/{private}/questions").json() == []
