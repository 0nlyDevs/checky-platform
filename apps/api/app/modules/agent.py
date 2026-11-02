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

from app.core import ai, embed
from app.core.access import AnyMember
from app.core.db import SessionLocal
from app.core.models import Item
from app.modules.rag import search
from app.workers import ingest

router = APIRouter(tags=["agent"])

MAX_STEPS = 6
RESULT_CHARS = 4000


@dataclass
class AgentContext:
    workspace_id: uuid.UUID
    # Passages and pages the agent has read, numbered for citations in the final answer.
    cited: list[dict[str, Any]] = field(default_factory=list)

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
        lines.append(f"[{n}] {p.title}\n{p.text[:900]}")
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
    return (
        f"« {page['title'] or final} » lue",
        f"[{n}] {page['title']}\n{page['text'][:RESULT_CHARS]}",
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


Tool = Callable[..., Awaitable[tuple[str, str]]]
TOOLS: dict[str, tuple[Tool, str, dict[str, Any]]] = {
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
}

SYSTEM = """Tu es l'agent de vérification d'une rédaction à Madagascar. Tu utilises les outils pour \
trouver des éléments, puis tu réponds.
- Cherche d'abord dans les sources de l'espace (search_sources). Lis un lien (fetch_url) s'il est fourni \
ou s'il apparaît dans les passages.
- Ta réponse finale ne s'appuie que sur ce que les outils ont renvoyé et cite les passages [n].
- Si rien ne permet de conclure, dis-le et indique quoi chercher.
- Réponds dans la langue de la question, en 3 à 6 phrases."""


def _tool_specs() -> list[dict[str, Any]]:
    return [
        {"type": "function", "function": {"name": n, "description": d, "parameters": p}}
        for n, (_, d, p) in TOOLS.items()
    ]


class AgentIn(BaseModel):
    question: str = Field(min_length=2, max_length=2000)


@router.post("/workspaces/{ws}/agent", response_class=EventSourceResponse)
async def run_agent(body: AgentIn, member: AnyMember) -> AsyncIterable[ServerSentEvent]:
    ctx = AgentContext(member.workspace_id)
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": body.question},
    ]
    step = 0
    try:
        for turn in range(MAX_STEPS):
            last = turn == MAX_STEPS - 1
            reply = await ai.complete(
                messages,
                None if last else _tool_specs(),
                workspace_id=member.workspace_id,
                temperature=0.1,
            )
            if not reply.tool_calls:
                yield ServerSentEvent(
                    data={"text": reply.content, "citations": ctx.cited}, event="answer"
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
                if name in TOOLS:
                    try:
                        summary, result = await TOOLS[name][0](ctx, **args)
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
