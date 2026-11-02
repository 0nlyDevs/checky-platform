"""Guardrails: answers from memory are refused, phantom citations go, figures must come from the
tools (one rewrite, then a visible flag), and the public guide never states a verdict it did not
find."""

from fastapi.testclient import TestClient

from app.main import app
from app.modules import guard
from tests import test_agent
from tests.test_agent import _call, _events
from tests.test_workspaces import _workspace

scripted = test_agent.scripted  # the scripted model fixture
POEM = "L'amour est un rayon qui caresse la terre, un souffle partagé. " * 10


def _answer(events):
    return next(d for e, d in events if e == "answer")["text"]


def test_figures_and_citations_are_checked_against_what_was_read():
    assert guard.figures("19 620 habitants [3], soit 12,5 % ; 3 cas") == ["19620", "12.5"]
    assert (
        guard.unbacked(
            "Le PIB est de 19,62 milliards [1].", ["PIB : 19.62 milliards de dollars"], ""
        )
        == []
    )
    assert guard.unbacked("Le PIB est de 21,4 milliards.", ["PIB : 19.62 milliards"], "") == [
        "21.4"
    ]
    assert guard.strip_bad_cites("Stable [1, 7]. Faux [9].", 2) == "Stable [1]. Faux."


def test_an_answer_from_memory_is_refused(as_user, scripted):
    turns, _ = scripted
    turns.append({"role": "assistant", "content": POEM})
    alice = as_user("alice")
    ws = _workspace(alice)
    events = _events(
        alice.post(f"/api/v1/workspaces/{ws}/agent", json={"question": "Un poème ?"}).text
    )
    assert _answer(events).startswith("Ce n'est pas mon rôle")


def test_an_unbacked_figure_gets_one_rewrite_then_a_flag(as_user, scripted):
    turns, seen = scripted
    turns.extend(
        [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [_call("find_claims", {"query": "riz"})],
            },
            {"role": "assistant", "content": "Le riz a augmenté de 48 % en un mois."},
            {
                "role": "assistant",
                "content": "Je n'ai pas trouvé ce chiffre. Il aurait augmenté de 48 %.",
            },
        ]
    )
    alice = as_user("alice")
    ws = _workspace(alice)
    events = _events(
        alice.post(
            f"/api/v1/workspaces/{ws}/agent", json={"question": "Le riz a-t-il augmenté ?"}
        ).text
    )
    assert "48" in seen[-1]["messages"][-1]["content"]  # the rewrite request names the figure
    assert "(À vérifier : 48 ne figure pas" in _answer(events)


def test_the_public_guide_never_states_a_verdict_it_did_not_find(scripted):
    turns, _ = scripted
    turns.append({"role": "assistant", "content": "C'est faux, le pont n'est pas fermé."})
    events = _events(
        TestClient(app)
        .post(
            "/api/v1/public/agent",
            json={"messages": [{"role": "user", "content": "Le pont est fermé ?"}]},
        )
        .text
    )
    assert _answer(events).startswith("Aucune rédaction n'a encore publié de verdict")


def test_an_answer_that_only_announces_a_search_is_nudged_once(as_user, scripted):
    turns, seen = scripted
    turns.extend(
        [
            {
                "role": "assistant",
                "content": "Je cherche des sources et je vous proposerai les liens.",
            },
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [_call("find_claims", {"query": "pont"})],
            },
            {"role": "assistant", "content": "Rien ne traite de ce pont."},
        ]
    )
    alice = as_user("alice")
    ws = _workspace(alice)
    r = alice.post(
        f"/api/v1/workspaces/{ws}/agent", json={"question": "Trouve des sources sur le pont"}
    )
    events = _events(r.text)
    assert [e for e, _ in events] == ["step", "answer", "done"]
    assert events[1][1]["text"] == "Rien ne traite de ce pont."
    assert guard.DO_IT in seen[1]["messages"][-1]["content"]
    assert guard.promises("Je vais chercher des articles.", 0)
    assert not guard.promises("Je vais chercher des articles.", 1)  # it did search
    assert not guard.promises("Le pont est fermé.", 0)


def test_a_proposal_said_but_not_made_is_nudged_once(as_user, scripted):
    turns, seen = scripted
    alice = as_user("alice")
    ws = _workspace(alice)
    claim = alice.post(f"/api/v1/workspaces/{ws}/items", json={"title": "Pont fermé"}).json()["id"]
    attach = {"url": "https://www.journal.mg/pont", "claim": ""}
    turns.extend(
        [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [_call("find_claims", {"query": "pont"})],
            },
            {"role": "assistant", "content": "Je vous propose d'attacher l'article du Journal."},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [_call("propose_attach_link", attach)],
            },
            {"role": "assistant", "content": "Confirmez pour joindre l'article."},
        ]
    )
    r = alice.post(
        f"/api/v1/workspaces/{ws}/copilot",
        json={
            "messages": [{"role": "user", "content": "Joins des sources"}],
            "page": f"/w/{ws}/affirmations/{claim}",
        },
    )
    answer = next(d for e, d in _events(r.text) if e == "answer")
    assert guard.PROPOSE_IT in seen[2]["messages"][-1]["content"]
    assert [a["kind"] for a in answer["actions"]] == ["attach_link"]
    assert answer["text"] == "Confirmez pour joindre l'article."


def test_an_empty_answer_is_asked_again_then_said_plainly(as_user, scripted):
    turns, seen = scripted
    alice = as_user("alice")
    ws = _workspace(alice)
    turns.extend([{"role": "assistant", "content": ""}, {"role": "assistant", "content": "Voilà."}])
    r = alice.post(f"/api/v1/workspaces/{ws}/agent", json={"question": "Et le pont ?"})
    assert next(d for e, d in _events(r.text) if e == "answer")["text"] == "Voilà."
    assert guard.ANSWER_NOW in seen[1]["messages"][-1]["content"]
    turns.extend([{"role": "assistant", "content": ""}, {"role": "assistant", "content": " "}])
    r = alice.post(f"/api/v1/workspaces/{ws}/agent", json={"question": "Et le pont ?"})
    assert next(d for e, d in _events(r.text) if e == "answer")["text"] == guard.EMPTY
