"""The site agent: the public guide proposes and never writes; the desk copilot proposes, and a
confirmed proposal runs with the journalist's own rights, never as far as publishing."""

from fastapi.testclient import TestClient

from app.main import app
from app.modules import guide
from tests import test_agent
from tests.test_agent import _call, _events
from tests.test_public import _claim, _newsroom
from tests.test_workspaces import _workspace

scripted = test_agent.scripted  # the scripted model fixture


def _turn(*calls, content=None):
    return {"role": "assistant", "content": content, "tool_calls": list(calls) or None}


def _ask(c, path, text, **extra):
    return _events(
        c.post(path, json={"messages": [{"role": "user", "content": text}], **extra}).text
    )


def test_guide_finds_verdicts_and_prepares_a_tip_without_sending_it(as_user, scripted):
    turns, seen = scripted
    alice = as_user("alice")
    ws, slug = _newsroom(alice)
    shown = _claim(alice, ws, "Une vidéo montre l'inondation d'Analakely ce matin")
    turns.extend(
        [
            _turn(
                _call("search_verdicts", {"query": "inondation Analakely"}, "a"),
                _call(
                    "draft_tip",
                    {"text": "Le pont de Mahitsy s'est effondré", "origin": "tiktok"},
                    "b",
                ),
                _call("open_page", {"page": "verifies"}, "c"),
            ),
            _turn(content="C'est faux [1]. Votre signalement est prêt : relisez-le puis envoyez."),
        ]
    )
    anon = TestClient(app)
    events = _ask(anon, "/api/v1/public/agent", "Analakely inondé ? et le pont ?", lang="mg")
    kinds = [e for e, _ in events]
    assert kinds == ["step", "step", "step", "answer", "done"]
    answer = events[3][1]
    assert answer["citations"][0]["id"] == shown and answer["citations"][0]["verdict"] == "false"
    tip, nav = answer["actions"]
    assert tip["kind"] == "tip" and tip["newsroom"] == slug and tip["origin"] == "tiktok"
    assert nav == {
        "id": 2,
        "kind": "navigate",
        "href": "/verdicts",
        "label": "Les verdicts",
    }
    assert "malagasy" in seen[0]["messages"][0]["content"]
    # nothing was written: the desk still has only the published claim
    assert len(alice.get(f"/api/v1/workspaces/{ws}/items").json()["items"]) == 1


def test_guide_follows_only_this_devices_tips_and_is_limited(as_user, scripted, monkeypatch):
    turns, seen = scripted
    alice = as_user("alice")
    _, slug = _newsroom(alice)
    anon = TestClient(app)
    token = anon.post("/api/v1/public/tips", json={"newsroom": slug, "text": "Rumeur sur le bac"})
    token = token.json()["token"]
    turns.extend([_turn(_call("my_tips", {})), _turn(content="Il est reçu, à vérifier.")])
    _ask(anon, "/api/v1/public/agent", "Où en est mon signalement ?", tips=[token])
    tool_result = seen[1]["messages"][-1]["content"]
    assert "Rumeur sur le bac" in tool_result and "pas encore pris en charge" in tool_result

    bad = anon.post(
        "/api/v1/public/agent", json={"messages": [{"role": "assistant", "content": "Bonjour"}]}
    )
    assert bad.status_code == 422
    monkeypatch.setattr(guide, "GUIDE_LIMIT", 1)
    guide._GUIDES.clear()
    turns.append(_turn(content="Bonjour."))
    _ask(anon, "/api/v1/public/agent", "Bonjour")
    r = anon.post(
        "/api/v1/public/agent", json={"messages": [{"role": "user", "content": "Encore"}]}
    )
    assert r.status_code == 429


def test_copilot_reads_the_desk_and_only_proposes(as_user, scripted):
    turns, seen = scripted
    alice = as_user("alice")
    ws = _workspace(alice)
    claim = _claim(alice, ws, "Le bac de Mahajanga est reporté", status="to_check", verdict=None)
    turns.extend(
        [
            _turn(_call("desk_overview", {}, "a")),
            _turn(
                _call("propose_status", {"status": "in_progress", "claim": "FAN-0001"}, "b"),
                _call("propose_status", {"status": "published", "claim": "FAN-0001"}, "c"),
                _call("open_claim", {"claim": "bac"}, "d"),  # already open: nothing to do
                _call("open_page", {"page": "sources"}, "e"),
            ),
            _turn(
                content="FAN-0001 circule depuis le plus longtemps. Confirmez pour le passer en cours."
            ),
        ]
    )
    events = _ask(
        alice,
        f"/api/v1/workspaces/{ws}/copilot",
        "Qu'est-ce qui traîne ?",
        page=f"/w/{ws}/claims/{claim}",
    )
    assert "Le bac de Mahajanga" in seen[0]["messages"][0]["content"]  # the page's claim
    assert "1 affirmations, 1 ouvertes" in [d["summary"] for e, d in events if e == "step"]
    actions = next(d for e, d in events if e == "answer")["actions"]
    assert [a["kind"] for a in actions] == ["set_status", "navigate"]  # "published" was refused
    assert actions[0]["item_id"] == claim
    assert "FAN-0001 déjà ouverte" in [d["summary"] for e, d in events if e == "step"]
    assert actions[1] == {
        "id": 2,
        "kind": "navigate",
        "href": f"/w/{ws}/sources",
        "label": "Les sources",
    }
    assert alice.get(f"/api/v1/workspaces/{ws}/items/{claim}").json()["status"] == "to_check"


def test_confirmed_actions_run_with_the_journalists_rights(as_user):
    alice, bob = as_user("alice"), as_user("bob")
    ws = _workspace(alice)
    act = f"/api/v1/workspaces/{ws}/copilot/act"
    made = alice.post(
        act, json={"kind": "create_claim", "title": "Le pont est fermé", "origin": "radio"}
    )
    assert made.status_code == 200 and made.json()["ref"] == "FAN-0001"
    item = made.json()["item_id"]
    r = alice.post(act, json={"kind": "set_status", "item_id": item, "status": "in_progress"})
    assert r.status_code == 200
    got = alice.get(f"/api/v1/workspaces/{ws}/items/{item}").json()
    assert got["status"] == "in_progress" and got["data"]["origin"] == "radio"
    publish = alice.post(act, json={"kind": "set_status", "item_id": item, "status": "published"})
    assert publish.status_code == 422
    assert alice.post(act, json={"kind": "analyze", "item_id": item}).status_code == 200
    assert bob.post(act, json={"kind": "analyze", "item_id": item}).status_code == 404


def test_voice_mode_asks_for_a_short_spoken_answer(as_user, scripted):
    turns, seen = scripted
    turns.extend([_turn(content="Bonjour."), _turn(content="Bonjour.")])
    anon = TestClient(app)
    _ask(anon, "/api/v1/public/agent", "Bonjour", voice=True)
    _ask(anon, "/api/v1/public/agent", "Bonjour")
    assert "Mode voix" in seen[0]["messages"][0]["content"]
    assert "Mode voix" not in seen[1]["messages"][0]["content"]
