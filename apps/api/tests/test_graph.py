"""The agent graph: stages run in parallel, a failed or skipped node never hides the others, LLM
nodes are skipped when the AI is off, and a stage can send the graph back once."""

import asyncio

import pytest

from app.core.graph import Graph, Node, Skip


async def _ok(state):
    return {"a": 1, "_summary": "found one", "_count": 1}


async def _boom(state):
    raise RuntimeError("down")


async def _skip(state):
    raise Skip("nothing to read")


async def _slow(state):
    await asyncio.sleep(5)
    return {"slow": True}


async def _reads(state):
    return {"read": state.get("a")}


@pytest.mark.asyncio
async def test_parallel_stage_merges_and_survives_failures():
    events = []

    async def emit(event, data):
        events.append((event, data))

    g = Graph().stage(
        "facts",
        [
            Node("Ok", _ok),
            Node("Boom", _boom),
            Node("Skip", _skip),
            Node("Slow", _slow, timeout=0.05),
        ],
    )
    state = await g.run({}, emit=emit)
    assert state["a"] == 1
    assert "slow" not in state
    statuses = {t["agent"]: t["status"] for t in state["trace"]}
    assert statuses == {"Ok": "done", "Boom": "failed", "Skip": "skipped", "Slow": "timeout"}
    done = next(d for e, d in events if d["agent"] == "Ok" and d["status"] == "done")
    assert done["summary"] == "found one" and done["count"] == 1
    assert all(e == "agent" for e, _ in events)


@pytest.mark.asyncio
async def test_llm_nodes_skipped_without_ai_and_stages_chain():
    g = (
        Graph()
        .stage("facts", [Node("Ok", _ok)])
        .stage("judge", [Node("Synthèse", _reads, llm=True)])
    )
    with_ai = await g.run({}, ai_enabled=True)
    assert with_ai["read"] == 1
    without = await g.run({}, ai_enabled=False)
    assert "read" not in without
    assert [t["status"] for t in without["trace"]] == ["done", "no_ai"]


@pytest.mark.asyncio
async def test_loop_runs_once():
    runs = {"facts": 0}

    async def facts(state):
        runs["facts"] += 1
        return {"n": runs["facts"]}

    g = (
        Graph()
        .stage("facts", [Node("Web", facts)])
        .stage(
            "critic",
            [Node("Contradicteur", _ok, llm=True)],
            loop_to="facts",
            should_loop=lambda s: True,
            max_loops=1,
        )
    )
    checkpoints = []

    async def checkpoint(state):
        checkpoints.append(state["n"])

    state = await g.run({}, checkpoint=checkpoint)
    assert runs["facts"] == 2 and state["loops"] == {"critic": 1}
    assert len(checkpoints) == 4  # facts, critic, facts again, critic again


async def test_parallel_nodes_cannot_modify_sibling_or_callers_nested_state():
    async def mutate(state):
        state["nested"]["value"] = "changed"
        return {}

    async def observe(state):
        await asyncio.sleep(0)
        return {"observed": state["nested"]["value"]}

    original = {"nested": {"value": "original"}}
    result = (
        await Graph()
        .stage("parallel", [Node("mutate", mutate), Node("observe", observe)])
        .run(original)
    )
    assert result["observed"] == original["nested"]["value"] == "original"
