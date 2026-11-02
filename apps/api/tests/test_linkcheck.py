"""« Analyser un lien »: read, claims and warning signs, search, suggested verdict — every quote
must be found in what it cites, and nothing is written to the desk."""

import io
import json

import httpx
import pytest

from app.core import websearch
from app.workers import ingest
from tests import test_agent
from tests.test_agent import _events
from tests.test_websearch import DDG
from tests.test_workspaces import _workspace

scripted = test_agent.scripted  # the scripted model fixture

ARTICLE = """<html><head><title>Choc</title>
<meta property="og:site_name" content="Info Tana Buzz">
<meta property="og:image" content="https://cdn.example.mg/photo.jpg"></head>
<body><article><h1>Madagascar quitte l'OMS</h1>
<p>Le président a annoncé hier que Madagascar quitte l'OMS. Partagez avant que ce soit supprimé !
Selon nos informations, 80 % des médecins approuvent cette décision historique pour le pays.</p>
<p>La décision prendra effet immédiatement, a-t-on appris de sources proches du dossier.</p>
</article></body></html>"""


def _say(obj):
    return {"role": "assistant", "content": json.dumps(obj, ensure_ascii=False)}


@pytest.fixture
def web(monkeypatch):
    websearch._cache.clear()
    pages = {}

    def page(request):
        body, kind = pages.get(str(request.url), ("", "text/html"))
        if body is None:
            return httpx.Response(403)
        return httpx.Response(
            200,
            content=body if isinstance(body, bytes) else body.encode(),
            headers={"content-type": kind},
        )

    def search(request):
        if request.url.host == "html.duckduckgo.com":
            return httpx.Response(200, text=DDG)
        return httpx.Response(200, json={"query": {"search": []}})

    monkeypatch.setattr(ingest, "_resolve", lambda host: ["93.184.216.34"])
    monkeypatch.setattr(ingest, "_transport", httpx.MockTransport(page))
    monkeypatch.setattr(websearch, "_transport", httpx.MockTransport(search))
    return pages


def test_a_link_is_read_searched_and_judged_without_writing(as_user, scripted, web):
    turns, seen = scripted
    web["https://buzz.mg/oms"] = (ARTICLE, "text/html; charset=utf-8")
    turns.extend(
        [
            _say(
                {
                    "summary": "Le texte affirme que Madagascar quitte l'OMS.",
                    "claims": ["Madagascar quitte l'OMS"],
                    "signals": [
                        {
                            "type": "urgence",
                            "quote": "Partagez avant que ce soit supprimé",
                            "why": "Pousse à partager vite.",
                        },
                        {
                            "type": "chiffre_invérifiable",
                            "quote": "95 % des médecins",
                            "why": "invented",
                        },
                    ],
                    "search": "Madagascar OMS retrait",
                }
            ),
            _say(
                {
                    "verdict": "false",
                    "reason": "L'AFP a démenti.",
                    "evidence": [
                        {
                            "result": 1,
                            "stance": "contradicts",
                            "quote": "Rien ne permet d'affirmer",
                        },
                        {"result": 2, "stance": "supports", "quote": "une phrase inventée"},
                    ],
                    "missing": "Le communiqué officiel.",
                }
            ),
        ]
    )
    alice = as_user("alice")
    ws = _workspace(alice)
    r = alice.post(f"/api/v1/workspaces/{ws}/link-check", json={"url": "https://buzz.mg/oms"})
    events = _events(r.text)
    steps = [(d["key"], d["status"]) for e, d in events if e == "step"]
    assert steps == [
        ("read", "running"),
        ("read", "done"),
        ("claims", "running"),
        ("claims", "done"),
        ("search", "running"),
        ("search", "done"),
        ("verdict", "running"),
        ("verdict", "done"),
    ]
    out = next(d for e, d in events if e == "result")
    assert out["site"] == "Info Tana Buzz" and out["claims"] == ["Madagascar quitte l'OMS"]
    assert [s["type"] for s in out["signals"]] == ["urgence"]  # the invented quote is dropped
    assert out["results"][0]["url"] == "https://factuel.afp.com/non-oms"
    assert out["analysis"]["verdict"] == "false" and out["analysis"]["dropped"] == 1
    assert out["reverse_search"][0]["name"] == "Google Lens"
    assert "Partagez avant" in seen[0]["messages"][1]["content"]
    assert alice.get(f"/api/v1/workspaces/{ws}/items").json()["items"] == []


def test_without_backed_evidence_the_verdict_is_unverifiable(as_user, scripted, web):
    turns, _ = scripted
    turns.extend(
        [
            _say(
                {
                    "summary": "s",
                    "claims": ["Le pont est fermé"],
                    "signals": [],
                    "search": "pont fermé",
                }
            ),
            _say(
                {
                    "verdict": "false",
                    "reason": "r",
                    "evidence": [{"result": 1, "stance": "contradicts", "quote": "absent"}],
                }
            ),
        ]
    )
    alice = as_user("alice")
    ws = _workspace(alice)
    events = _events(
        alice.post(
            f"/api/v1/workspaces/{ws}/link-check", json={"text": "Le pont est fermé jusqu'à lundi"}
        ).text
    )
    out = next(d for e, d in events if e == "result")
    assert out["analysis"]["verdict"] == "unverifiable"


def test_a_closed_social_link_asks_for_the_text_and_an_image_shows_its_traces(
    as_user, scripted, web
):
    from PIL import Image, PngImagePlugin

    alice = as_user("alice")
    ws = _workspace(alice)
    web["https://www.facebook.com/p/1"] = (None, "")
    events = _events(
        alice.post(
            f"/api/v1/workspaces/{ws}/link-check", json={"url": "https://www.facebook.com/p/1"}
        ).text
    )
    out = next(d for e, d in events if e == "result")
    assert out["needs_text"] and out["platform"] == "facebook" and "403" in out["read_error"]

    info = PngImagePlugin.PngInfo()
    info.add_text("parameters", "Model: Stable Diffusion XL")
    buf = io.BytesIO()
    Image.new("RGB", (4, 4)).save(buf, "PNG", pnginfo=info)
    web["https://cdn.example.mg/fake.png"] = (buf.getvalue(), "image/png")
    events = _events(
        alice.post(
            f"/api/v1/workspaces/{ws}/link-check", json={"url": "https://cdn.example.mg/fake.png"}
        ).text
    )
    out = next(d for e, d in events if e == "result")
    assert out["kind"] == "image" and out["image"]["ai_markers"] == ["Stable Diffusion"]
    assert "analysis" not in out  # no text, no claim: no verdict


def test_outsiders_cannot_analyse(as_user, web):
    alice, bob = as_user("alice"), as_user("bob")
    ws = _workspace(alice)
    assert bob.post(f"/api/v1/workspaces/{ws}/link-check", json={"text": "x"}).status_code == 404
    assert alice.post(f"/api/v1/workspaces/{ws}/link-check", json={}).status_code == 422


def test_an_old_post_is_dated_for_the_model_and_the_journalist(as_user, scripted, web):
    turns, seen = scripted
    dated = ARTICLE.replace(
        "<title>Choc</title>",
        '<title>Choc</title><meta property="article:published_time" '
        'content="2019-01-14T08:00:00+03:00">',
    )
    web["https://buzz.mg/oms"] = (dated, "text/html; charset=utf-8")
    turns.extend(
        [
            _say({"summary": "s", "claims": ["Madagascar quitte l'OMS"], "search": "OMS"}),
            _say({"verdict": "unverifiable", "reason": "r", "evidence": []}),
        ]
    )
    alice = as_user("alice")
    ws = _workspace(alice)
    r = alice.post(f"/api/v1/workspaces/{ws}/link-check", json={"url": "https://buzz.mg/oms"})
    out = next(d for e, d in _events(r.text) if e == "result")
    assert out["published_at"] == "2019-01-14" and out["days_old"] > 2000
    for call in seen:  # in the instructions, apart from the content
        assert "Aujourd'hui : " in call["messages"][0]["content"]
        assert "Contenu publié le 14 janvier 2019, il y a " in call["messages"][0]["content"]
        assert "Aujourd'hui" not in call["messages"][1]["content"]


def test_a_shared_file_is_checked_on_its_transcript(as_user, scripted, web):
    turns, seen = scripted
    turns.extend(
        [
            _say(
                {
                    "summary": "La vidéo affirme que le pont d'Anosy est fermé.",
                    "claims": ["Le pont d'Anosy est fermé"],
                    "signals": [],
                    "search": "pont Anosy fermé",
                }
            ),
            _say({"verdict": "unverifiable", "reason": "r", "evidence": [], "missing": "m"}),
        ]
    )
    alice, bob = as_user("alice"), as_user("bob")
    ws = _workspace(alice)
    item = alice.post(f"/api/v1/workspaces/{ws}/items", json={"title": "Pont"}).json()
    said = "Attention, le pont d'Anosy est fermé depuis ce matin."
    src = alice.post(
        f"/api/v1/workspaces/{ws}/sources", json={"text": said, "item_id": item["id"]}
    ).json()
    url = f"/api/v1/workspaces/{ws}/link-check"
    events = _events(alice.post(url, json={"source_id": src["id"]}).text)
    out = next(d for e, d in events if e == "result")
    assert out["kind"] == "text" and out["source_id"] == src["id"]
    assert out["claims"] == ["Le pont d'Anosy est fermé"]
    assert out["tracked"]["item_id"] == item["id"]
    assert said in seen[0]["messages"][1]["content"]

    pending = alice.post(f"/api/v1/workspaces/{ws}/sources", json={"url": "https://a.mg/x"}).json()
    errors = [
        d["code"]
        for e, d in _events(alice.post(url, json={"source_id": pending["id"]}).text)
        if e == "error"
    ]
    assert errors == ["source_not_ready"]
    other = _workspace(bob)
    errors = [
        d["code"]
        for e, d in _events(
            bob.post(f"/api/v1/workspaces/{other}/link-check", json={"source_id": src["id"]}).text
        )
        if e == "error"
    ]
    assert errors == ["not_found"]
