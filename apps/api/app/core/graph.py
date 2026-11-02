"""A small agent graph, in the shape of LangGraph: a typed state, nodes, stages that run in
parallel, a bounded loop and a human node at the end.

The crew that verifies a claim (`app/modules/crew.py`) is built with it. Design rules, which are
the product's rules:

- A node either retrieves or compares evidence (`llm=False`) or interprets it with a
  model call (`llm=True`). Neither classification guarantees factual correctness. When the newsroom turned the AI off (« Mode sans IA »), or when a
  provider is down, the fact nodes still run and the card still shows what they found.
- A node that fails is reported as failed and the graph goes on: one check down never hides the
  others.
- Every node reports through `emit("agent", {...})` as it starts and ends, so the live log on
  Vérifier shows the checks racing side by side.
- A stage may send the graph back once (`loop_to`); on that second pass only the nodes marked
  `rerun=True` run again, so a loop costs one targeted search, not another round of model calls.
- `checkpoint(state)` is awaited after every stage, so a caller can store stage snapshots. Automatic resume is not implemented.
- The last node of a verification is the journalist (« Signer et publier »): the graph can end in a
  reading, never in a publication. That node is not run here; it is the person.

    graph = Graph()
    graph.stage("read", [Node("Lecteur", read, llm=True)])
    graph.stage("facts", [Node("Provenance", provenance), Node("Registre", registry), ...])
    graph.stage("judge", [Node("Synthèse", synthesise, llm=True)])
    graph.stage("critic", [Node("Contradicteur", criticise, llm=True)], loop_to="facts", max_loops=1)
    state = await graph.run(state, emit=send, ai_enabled=True)

A node is `async def fn(state: dict) -> dict | None`: it returns the keys it adds to the state
(merged, the node never mutates the shared state while others run) and may set a
`summary` string for the log through the returned `_summary` key.
"""

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger("checky.graph")

NodeFn = Callable[[dict[str, Any]], Awaitable[dict[str, Any] | None]]
Emit = Callable[[str, dict[str, Any]], Awaitable[None]]


class Skip(Exception):
    """Raised by a node that has nothing to do for this input (shown as `skipped`, not failed)."""


@dataclass
class Node:
    name: str
    fn: NodeFn
    llm: bool = False
    # seconds before the node is reported as failed (timed out) and the graph moves on
    timeout: float = 25.0
    # False: when a loop sends the graph back through this node's stage, the node is not run
    # again (its first answer stands). The Contradicteur's loop re-runs the Web search only.
    rerun: bool = True


@dataclass
class Stage:
    name: str
    nodes: list[Node]
    # `loop_to` names an earlier stage to run again when `should_loop(state)` says so, at most
    # `max_loops` times (the Contradicteur sends the researchers back once with a targeted query).
    loop_to: str | None = None
    should_loop: Callable[[dict[str, Any]], bool] | None = None
    max_loops: int = 1


@dataclass
class Trace:
    """What one node did, kept in `state["trace"]` and shown on the dossier."""

    agent: str
    stage: str
    status: str  # done|failed|skipped|timeout|no_ai
    ms: int
    summary: str = ""
    llm: bool = False
    error: str | None = None

    def dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass
class Graph:
    stages: list[Stage] = field(default_factory=list)

    def stage(self, name: str, nodes: list[Node], **kw: Any) -> "Graph":
        self.stages.append(Stage(name, nodes, **kw))
        return self

    async def run(
        self,
        state: dict[str, Any],
        *,
        emit: Emit | None = None,
        checkpoint: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
        ai_enabled: bool = True,
    ) -> dict[str, Any]:
        state = {**state, "trace": list(state.get("trace") or []), "ai_enabled": ai_enabled}
        loops: dict[str, int] = {}
        seen: set[str] = set()
        i = 0
        while i < len(self.stages):
            stage = self.stages[i]
            again = stage.name in seen
            seen.add(stage.name)
            await self._run_stage(stage, state, emit, ai_enabled, again)
            if checkpoint:
                await checkpoint(state)
            if (
                stage.loop_to
                and stage.should_loop
                and loops.get(stage.name, 0) < stage.max_loops
                and stage.should_loop(state)
            ):
                loops[stage.name] = loops.get(stage.name, 0) + 1
                state["loops"] = loops
                i = next(n for n, s in enumerate(self.stages) if s.name == stage.loop_to)
                continue
            i += 1
        return state

    async def _run_stage(
        self,
        stage: Stage,
        state: dict[str, Any],
        emit: Emit | None,
        ai_enabled: bool,
        again: bool = False,
    ) -> None:
        nodes = [node for node in stage.nodes if node.rerun or not again]
        results = await asyncio.gather(
            *(self._run_node(stage, node, state, emit, ai_enabled) for node in nodes)
        )
        # Merge after the whole stage, so parallel nodes never read each other's half-written keys.
        for update in results:
            if update:
                state.update(update)

    async def _run_node(
        self, stage: Stage, node: Node, state: dict[str, Any], emit: Emit | None, ai_enabled: bool
    ) -> dict[str, Any] | None:
        async def send(status: str, **extra: Any) -> None:
            if emit:
                await emit(
                    "agent",
                    {
                        "agent": node.name,
                        "stage": stage.name,
                        "status": status,
                        "llm": node.llm,
                        **extra,
                    },
                )

        if node.llm and not ai_enabled:
            trace = Trace(node.name, stage.name, "no_ai", 0, "", True)
            state["trace"].append(trace.dict())
            await send("no_ai")
            return None
        await send("running")
        started = time.monotonic()
        try:
            update = await asyncio.wait_for(node.fn(deepcopy(state)), node.timeout)
        except Skip as skip:
            trace = Trace(node.name, stage.name, "skipped", _ms(started), str(skip), node.llm)
            state["trace"].append(trace.dict())
            await send("skipped", summary=str(skip), ms=trace.ms)
            return None
        except TimeoutError:
            summary = f"Délai dépassé ({node.timeout:.0f} s)"
            trace = Trace(
                node.name, stage.name, "timeout", _ms(started), summary, node.llm, "timeout"
            )
            state["trace"].append(trace.dict())
            await send("timeout", summary=summary, ms=trace.ms)
            return None
        except Exception as exc:  # noqa: BLE001 - one failed check must not hide the others
            log.warning("agent %s failed: %s", node.name, type(exc).__name__)
            summary = failure_summary(exc)
            trace = Trace(
                node.name, stage.name, "failed", _ms(started), summary, node.llm, type(exc).__name__
            )
            state["trace"].append(trace.dict())
            await send("failed", summary=summary, ms=trace.ms, error=type(exc).__name__)
            return None
        update = dict(update or {})
        summary = str(update.pop("_summary", "") or "")
        count = update.pop("_count", None)
        trace = Trace(node.name, stage.name, "done", _ms(started), summary, node.llm)
        state["trace"].append(trace.dict())
        await send(
            "done", summary=summary, ms=trace.ms, **({"count": count} if count is not None else {})
        )
        return update


# One line for the live log, from the kind of failure only: an exception's message may quote the
# checked content or a provider's answer, so it never reaches the screen.
FAILURES = {
    "AiUnavailable": "Modèles d'IA indisponibles",
    "SearchUnavailable": "Recherche indisponible",
    "ApiError": "Service indisponible",
    "HTTPError": "Service distant injoignable",
    "ConnectError": "Service distant injoignable",
    "ReadTimeout": "Service distant trop lent",
    "ValidationError": "Réponse illisible",
    "JSONDecodeError": "Réponse illisible",
    "ValueError": "Réponse inexploitable",
}


def failure_summary(exc: BaseException) -> str:
    for cls in type(exc).__mro__:
        if cls.__name__ in FAILURES:
            return FAILURES[cls.__name__]
    return f"Échec ({type(exc).__name__})"


def _ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)
