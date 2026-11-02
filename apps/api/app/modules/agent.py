"""M10 agent: a small tool loop over the gateway, streamed so the reasoning shows in the demo.

`POST …/agent` SSE: `step` ({n, tool, input, summary}) for each tool call, then `answer`
({text, citations}), then `done`, or `error`. At most MAX_STEPS model turns.

Add a tool: write an async function `(ctx, **args) -> (summary, result_text)` and register it
in TOOLS with its JSON schema. The model sees the schema; the user sees the summary.
"""

import json
import uuid
from collections.abc import AsyncIterable, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from fastapi import APIRouter
from fastapi.sse import EventSourceResponse, ServerSentEvent
from pydantic import BaseModel, Field
from sqlalchemy import or_, select

from app.core import ai, dates, embed, websearch
from app.core.access import AnyMember
from app.core.db import SessionLocal
from app.core.models import Item
from app.modules import guard
from app.modules.guard import Guard
from app.modules.rag import search
from app.workers import ingest

router = APIRouter(tags=["agent"])

MAX_STEPS = 6
RESULT_CHARS = 4000


@dataclass
class AgentContext:
    workspace_id: uuid.UUID | None
    # Passages and pages the agent has read, numbered for citations in the final answer.
    cited: list[dict[str, Any]] = field(default_factory=list)
    # Changes the agent proposes; nothing is written until the person confirms one in the UI.
    actions: list[dict[str, Any]] = field(default_factory=list)

    def propose(self, kind: str, **payload: Any) -> dict[str, Any]:
        action = {"id": len(self.actions) + 1, "kind": kind, **payload}
        self.actions.append(action)
        return action

    def cite(self, title: str, url: str | None, text: str, source_id: str | None = None) -> int:
        self.cited.append(
            {
                "n": len(self.cited) + 1,
                "title": title,
                "url": url,
                "text": text[:600],
                "source_id": source_id,
            }
        )
        return len(self.cited)


async def search_sources(ctx: AgentContext, query: str) -> tuple[str, str]:
    if not embed.configured():
        return "recherche indisponible", "Search is not configured."
    async with SessionLocal() as db:
        passages = await search(db, ctx.workspace_id, query, 5)
    lines = []
    for p in passages:
        n = ctx.cite(p.title, p.url, p.text, str(p.source_id))
        lines.append(f"[{n}] {p.title} ({dates.published_line(p.published_at)})\n{p.text[:900]}")
    summary = f"{len(passages)} passages" + (f", dont « {passages[0].title} »" if passages else "")
    return summary, "\n\n".join(lines) or "No passage found."


async def fetch_url(ctx: AgentContext, url: str) -> tuple[str, str]:
    try:
        final, html = await ingest.fetch_page(url)
        page = ingest.extract_page(html, final)
    except Exception as e:  # noqa: BLE001 - the model gets the failure and can try something else
        return f"page illisible ({e})"[:120], f"Could not read the page: {e}"
    if not page["text"]:
        return "aucun texte principal", "The page has no main text."
    n = ctx.cite(page["title"] or final, final, page["text"])
    when = dates.published_line(page["published_at"])
    return (
        f"« {page['title'] or final} » lue",
        f"[{n}] {page['title']} ({when})\n{page['text'][:RESULT_CHARS]}",
    )


async def find_claims(ctx: AgentContext, query: str) -> tuple[str, str]:
    like = f"%{query}%"
    async with SessionLocal() as db:
        items = list(
            await db.scalars(
                select(Item)
                .where(
                    Item.workspace_id == ctx.workspace_id,
                    or_(Item.title.ilike(like), Item.body.ilike(like)),
                )
                .order_by(Item.created_at.desc())
                .limit(8)
            )
        )
    rows = [
        {
            "id": str(i.id),
            "ref": i.data.get("ref"),
            "title": i.title,
            "status": i.status,
            "verdict": i.data.get("verdict"),
        }
        for i in items
    ]
    return f"{len(rows)} affirmations", json.dumps(rows, ensure_ascii=False)


async def _found(ctx: AgentContext, results: list[dict[str, Any]], what: str) -> tuple[str, str]:
    lines = []
    for r in results:
        n = ctx.cite(r["title"], r["url"], r["snippet"])
        lines.append(f"[{n}] {r['title']}\n{r['url']}\n{r['snippet'][:700]}")
    if not results:
        return f"aucun résultat ({what})", "No result. Try other words, or another language."
    summary = f"{len(results)} résultats ({what}), dont « {results[0]['title'][:60]} »"
    return summary, "\n\n".join(lines)


async def search_web(ctx: AgentContext, query: str) -> tuple[str, str]:
    try:
        return await _found(ctx, await websearch.web(query), "web")
    except websearch.SearchUnavailable as e:
        return "recherche web indisponible", f"Web search is unavailable right now ({e})."


async def search_wikipedia(
    ctx: AgentContext, query: str, lang: str | None = None
) -> tuple[str, str]:
    try:
        return await _found(ctx, await websearch.wikipedia(query, lang or "fr"), "Wikipedia")
    except websearch.SearchUnavailable as e:
        return "Wikipedia indisponible", f"Wikipedia is unavailable right now ({e})."


async def search_fact_checks(ctx: AgentContext, query: str) -> tuple[str, str]:
    try:
        return await _found(ctx, await websearch.fact_checks(query), "fact-checkeurs")
    except websearch.SearchUnavailable as e:
        return "recherche indisponible", f"Search is unavailable right now ({e})."


QUERY = {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}
WEB_TOOLS = {
    "search_web": (
        search_web,
        (
            "Search the web (news, posts, official pages). Returns numbered results with links; read "
            "one with fetch_url before relying on it."
        ),
        QUERY,
    ),
    "search_wikipedia": (
        search_wikipedia,
        "Search Wikipedia and return the opening summary of the best articles.",
        {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "lang": {"type": "string", "enum": ["fr", "mg", "en"]},
            },
            "required": ["query"],
        },
    ),
    "search_fact_checks": (
        search_fact_checks,
        (
            "Search articles already published by fact-checkers (AFP Factuel, Africa Check, France 24 "
            "Observers, Les Décodeurs…) about the claim."
        ),
        QUERY,
    ),
}


Tool = Callable[..., Awaitable[tuple[str, str]]]
Tools = dict[str, tuple[Tool, str, dict[str, Any]]]
TOOLS: Tools = {
    "search_sources": (
        search_sources,
        "Search the workspace's sources (articles, documents, transcripts) and return numbered passages.",
        {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
    ),
    "fetch_url": (
        fetch_url,
        "Read a public web page (article, post) and return its main text, numbered for citation.",
        {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]},
    ),
    "find_claims": (
        find_claims,
        "Find claims already tracked by the newsroom whose title or context contains the words.",
        {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
    ),
    **WEB_TOOLS,
}

SYSTEM = (
    """Tu es l'agent de vérification d'une rédaction à Madagascar. Tu utilises les outils pour \
trouver des éléments, puis tu réponds.
- Cherche d'abord dans les sources de l'espace (search_sources). Si elles ne suffisent pas, cherche \
dehors : search_fact_checks (déjà vérifié ailleurs ?), search_wikipedia (faits établis), search_web \
(presse, pages officielles, publications). Lis la page (fetch_url) avant de t'appuyer sur un résultat.
- Un résultat web n'est pas une preuve en soi : dis d'où vient l'information et préfère les sources \
primaires (institutions, presse reconnue) aux réseaux sociaux.
- Ta réponse finale ne s'appuie que sur ce que les outils ont renvoyé et cite les passages [n].
- Si rien ne permet de conclure, dis-le et indique quoi chercher.
- Réponds dans la langue de la question, en 3 à 6 phrases.

"""
    + guard.SCOPE
)


def _nullable(schema: dict[str, Any]) -> dict[str, Any]:
    # Models often send null for an argument they skip, and Groq rejects that against a plain
    # "string": every optional argument also accepts null (the tools default it).
    required = set(schema.get("required", []))
    props = {}
    for name, prop in schema.get("properties", {}).items():
        if name not in required and isinstance(prop.get("type"), str):
            prop = {**prop, "type": [prop["type"], "null"]}
            if "enum" in prop:
                prop["enum"] = [*prop["enum"], None]
        props[name] = prop
    return {**schema, "properties": props}


DESK_REFUSAL = (
    "Ce n'est pas mon rôle : je vérifie des affirmations à partir des sources de votre espace, "
    "des fact-checkeurs, de Wikipedia et du web, et j'aide à faire avancer le travail du desk. "
    "Posez-moi une question de vérification."
)


def desk_guard() -> Guard:
    return Guard(refusal=DESK_REFUSAL)


def tool_specs(tools: Tools) -> list[dict[str, Any]]:
    return [
        {"type": "function", "function": {"name": n, "description": d, "parameters": _nullable(p)}}
        for n, (_, d, p) in tools.items()
    ]


async def tool_loop(
    ctx: AgentContext,
    messages: list[dict[str, Any]],
    tools: Tools,
    max_steps: int = MAX_STEPS,
    guard: Guard | None = None,
    **params: Any,
) -> AsyncIterable[ServerSentEvent]:
    """Runs the model with tools until it answers. SSE: `step`…, `answer` ({text, citations,
    actions}), `done`, or `error`. The last turn has no tools, so the model must answer.
    With a `guard`, the answer is checked against what the tools returned (see guard.py)."""
    step = 0
    # what the answer may rest on: the instructions, the question, every tool result
    context = [str(m.get("content") or "") for m in messages if m.get("role") in ("system", "user")]
    try:
        for turn in range(max_steps):
            last = turn == max_steps - 1
            reply = await ai.complete(
                messages,
                None if last else tool_specs(tools),
                workspace_id=ctx.workspace_id,
                temperature=0.1,
                **params,
            )
            if not reply.tool_calls:
                text = reply.content or ""
                if guard:
                    text, reply = await _checked(ctx, messages, reply, step, guard, context, params)
                yield ServerSentEvent(
                    data={"text": text, "citations": ctx.cited, "actions": ctx.actions},
                    event="answer",
                )
                yield ServerSentEvent(
                    data={"provider": reply.provider, "model": reply.model, "steps": step},
                    event="done",
                )
                return
            messages.append(reply.message)
            for call in reply.tool_calls:
                fn = call.get("function") or {}
                name = fn.get("name", "")
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                step += 1
                if name in tools:
                    try:
                        summary, result = await tools[name][0](ctx, **args)
                    except TypeError:
                        summary, result = "arguments invalides", "Invalid arguments for this tool."
                else:
                    summary, result = "outil inconnu", f"Unknown tool {name}."
                yield ServerSentEvent(
                    data={"n": step, "tool": name, "input": args, "summary": summary}, event="step"
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.get("id", ""),
                        "content": result[:RESULT_CHARS],
                    }
                )
                if guard:
                    guard.seen.append(result[:RESULT_CHARS])
        # The last turn was asked without tools, so it can only have answered above.
        yield ServerSentEvent(
            data={"code": "no_answer", "message": "The agent did not conclude"}, event="error"
        )
    except ai.AiUnavailable as e:
        yield ServerSentEvent(data={"code": "ai_unavailable", "message": str(e)}, event="error")
    except Exception as e:  # noqa: BLE001 - never end the stream without telling the client
        yield ServerSentEvent(
            data={"code": "agent_failed", "message": type(e).__name__}, event="error"
        )


async def _checked(ctx, messages, reply, steps, g: Guard, context, params):
    """The guard's verdict on an answer: refuse, clean, or ask for one rewrite."""
    text = reply.content or ""
    if guard.from_memory(text, steps, g):
        return g.refusal, reply
    if guard.verdict_without_files(text, len(ctx.cited), g):
        return g.no_verdict or g.refusal, reply
    text = guard.strip_bad_cites(text, len(ctx.cited))
    seen = [*context, *g.seen]
    missing = guard.unbacked(text, seen, "")
    if missing:
        messages.append(reply.message)
        messages.append({"role": "user", "content": guard.repair_prompt(missing)})
        reply = await ai.complete(messages, None, workspace_id=ctx.workspace_id, **params)
        text = guard.strip_bad_cites(reply.content or "", len(ctx.cited))
        if missing := guard.unbacked(text, seen, ""):
            text += guard.flag(missing)
    return text, reply


class AgentIn(BaseModel):
    question: str = Field(min_length=2, max_length=2000)


@router.post("/workspaces/{ws}/agent", response_class=EventSourceResponse)
async def run_agent(body: AgentIn, member: AnyMember) -> AsyncIterable[ServerSentEvent]:
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": f"{SYSTEM}\n\n{dates.today_line()}"},
        {"role": "user", "content": body.question},
    ]
    async for event in tool_loop(
        AgentContext(member.workspace_id), messages, TOOLS, guard=desk_guard()
    ):
        yield event
