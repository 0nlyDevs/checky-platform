"""Claude as one more provider of the gateway, through the official `anthropic` SDK.

The rest of the app speaks the OpenAI chat format; this module translates both ways:
system messages become `system`, assistant tool calls become `tool_use` blocks, `tool` messages
become `tool_result` blocks, and the reply comes back as plain text + OpenAI-style tool calls.
Claude's own content blocks (its thinking included) are kept on the assistant message as
`anthropic_content` and sent back unchanged on the next turn; other providers never see them.

Set `CLAUDE_API_KEY` (a comma list works, like the others) and add `claude` to LLM_PROVIDERS.
"""

import json
import re
from collections.abc import AsyncIterator
from typing import Any

import anthropic
import httpx2

from app.core.config import get_settings

DEFAULT_MODEL = "claude-opus-5-5"
KEEP_BLOCKS = {"text", "thinking", "redacted_thinking", "tool_use"}
JSON_ONLY = "Réponds uniquement avec un objet JSON valide, sans aucun texte autour."
# Refused requests are re-run server-side on the model Anthropic recommends for that refusal.
FALLBACK_BETA = "server-side-fallback-2026-07-01"

# Tests swap this for an httpx2.MockTransport.
_transport: httpx2.AsyncBaseTransport | None = None


class Refused(Exception):
    """Claude declined (stop_reason "refusal"); the gateway moves on to the next provider."""


def client(api_key: str) -> anthropic.AsyncAnthropic:
    s = get_settings()
    http = anthropic.DefaultAsyncHttpxClient(transport=_transport) if _transport else None
    # No SDK retries: the gateway owns retries, cooldowns and the fallback to other providers.
    return anthropic.AsyncAnthropic(
        api_key=api_key, max_retries=0, timeout=s.ai_timeout, http_client=http
    )


def classify(e: BaseException) -> tuple[int, float | None] | None:
    """(status, retry_after) when the error is worth retrying or cooling down on, else None."""
    if isinstance(e, anthropic.APIStatusError):
        if e.status_code == 429 or e.status_code >= 500:
            try:
                wait = float(e.response.headers.get("retry-after", ""))
            except ValueError:
                wait = None
            return e.status_code, wait
        return None
    if isinstance(e, anthropic.APIConnectionError):  # timeouts included
        return 0, None
    return None


def _id(raw: str | None, blanks: list[int], side: int) -> str:
    """Claude only accepts [A-Za-z0-9_-] ids: other providers' ids are cleaned the same way on
    both sides; blank ones pair up in order (call, then its result)."""
    if raw:
        return re.sub(r"[^A-Za-z0-9_-]", "_", raw)[:64]
    blanks[side] += 1
    return f"call_{blanks[side]}"


def request(
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
    params: dict[str, Any],
) -> dict[str, Any]:
    """The Messages API arguments for an OpenAI-style conversation."""
    system: list[str] = []
    out: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    blanks = [0, 0]  # blank ids seen on calls, on results

    def flush():
        if results:
            out.append({"role": "user", "content": list(results)})
            results.clear()

    for m in messages:
        role = m.get("role")
        if role == "system":
            system.append(str(m.get("content") or ""))
        elif role == "tool":
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": _id(m.get("tool_call_id"), blanks, 1),
                    "content": str(m.get("content") or "") or "(empty)",
                }
            )
        elif role == "assistant":
            flush()
            blocks = m.get("anthropic_content")
            if not blocks:
                blocks = [{"type": "text", "text": m["content"]}] if m.get("content") else []
                for call in m.get("tool_calls") or []:
                    fn = call.get("function") or {}
                    try:
                        args = json.loads(fn.get("arguments") or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    blocks.append(
                        {
                            "type": "tool_use",
                            "id": _id(call.get("id"), blanks, 0),
                            "name": fn.get("name", ""),
                            "input": args if isinstance(args, dict) else {},
                        }
                    )
            if blocks:
                out.append({"role": "assistant", "content": blocks})
        else:
            flush()
            out.append({"role": "user", "content": str(m.get("content") or "")})
    flush()

    if (params.get("response_format") or {}).get("type") == "json_object":
        system.append(JSON_ONLY)
    s = get_settings()
    # Thinking is always on for the current models and counts towards max_tokens: leave room.
    args: dict[str, Any] = {
        "model": model,
        "max_tokens": max(int(params.get("max_tokens") or 0), 4096),
        "messages": out,
        "output_config": {"effort": s.claude_effort},
    }
    if system:
        args["system"] = "\n\n".join(system)
    if tools:
        args["tools"] = [
            {
                "name": t["function"]["name"],
                "description": t["function"].get("description", ""),
                "input_schema": t["function"].get("parameters") or {"type": "object"},
            }
            for t in tools
        ]
    if re.match(r"claude-(opus|fable|sonnet)", model):
        args["betas"] = [FALLBACK_BETA]
        args["fallbacks"] = "default"
    return args


def reply(message: Any) -> dict[str, Any]:
    """Text, OpenAI-style tool calls and the blocks to replay, from a Claude message."""
    if message.stop_reason == "refusal":
        raise Refused(getattr(message.stop_details, "category", None) or "refusal")
    text, calls, raw = [], [], []
    for block in message.content:
        if block.type not in KEEP_BLOCKS:
            continue
        raw.append(block.model_dump(mode="json", exclude_none=True))
        if block.type == "text":
            text.append(block.text)
        elif block.type == "tool_use":
            calls.append(
                {
                    "id": block.id,
                    "type": "function",
                    "function": {
                        "name": block.name,
                        "arguments": json.dumps(block.input, ensure_ascii=False),
                    },
                }
            )
    usage = message.usage
    return {
        "content": "".join(text),
        "model": message.model,
        "tool_calls": calls or None,
        "tokens_in": getattr(usage, "input_tokens", None),
        "tokens_out": getattr(usage, "output_tokens", None),
        "raw": raw,
    }


async def complete(api_key, model, messages, tools, params) -> dict[str, Any]:
    async with client(api_key) as c:
        message = await c.beta.messages.create(**request(model, messages, tools, params))
    return reply(message)


class OpenStream:
    """A Claude stream presented as OpenAI chat chunks, so the gateway's stream code is shared."""

    def __init__(self, api_key, model, messages, tools, params):
        self._client = client(api_key)
        self._manager = self._client.beta.messages.stream(**request(model, messages, tools, params))
        self._stream = None
        self.raw: list[dict[str, Any]] | None = None  # the blocks to replay, once finished

    async def open(self) -> None:
        self._stream = await self._manager.__aenter__()

    async def events(self) -> AsyncIterator[dict[str, Any]]:
        async for event in self._stream:
            if event.type == "content_block_delta" and event.delta.type == "text_delta":
                yield {"choices": [{"delta": {"content": event.delta.text}}]}
        final = reply(await self._stream.get_final_message())
        self.raw = final["raw"]
        tool_calls = [{**c, "index": i} for i, c in enumerate(final["tool_calls"] or [])]
        yield {
            "model": final["model"],
            "usage": {
                "prompt_tokens": final["tokens_in"],
                "completion_tokens": final["tokens_out"],
            },
            "choices": [{"delta": {"tool_calls": tool_calls}}],
        }

    async def aclose(self) -> None:
        try:
            await self._manager.__aexit__(None, None, None)
        finally:
            await self._client.close()


async def check(api_key: str) -> None:
    """Raises when the key cannot list models (free, no tokens)."""
    async with client(api_key) as c:
        await c.models.list(limit=1)
