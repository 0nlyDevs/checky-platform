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
