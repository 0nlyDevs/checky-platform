"""AI gateway: one `complete()` over OpenAI-compatible providers, with retries and fallback.

    reply = await complete([{"role": "user", "content": "Bonjour"}])
    reply.content, reply.provider

    stream = complete(messages, stream=True)
    async for text in stream:
        ...
    stream.completion.provider   # set once the stream is finished

Providers are tried in LLM_PROVIDERS order; one without an API key is skipped. On 429, 5xx
or a timeout the call is retried with backoff, then the next provider takes over. A stream
can only fall back before its first chunk. Every attempt is logged to app.ai_call (no prompt
text). With AI_CACHE=true identical requests are answered from disk.
"""

import asyncio
import hashlib
import json
import logging
import time
import uuid
from collections.abc import AsyncIterator, Coroutine
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal, overload

import httpx

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.models import AiCall

log = logging.getLogger("fanilo.ai")

# name -> (OpenAI-compatible base URL, default model)
PROVIDERS: dict[str, tuple[str, str]] = {
    "groq": ("https://api.groq.com/openai/v1", "llama-3.3-70b-versatile"),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai", "gemini-2.5-flash"),
    "nvidia": ("https://integrate.api.nvidia.com/v1", "meta/llama-3.3-70b-instruct"),
}

# Tests swap these for an httpx.MockTransport and a no-op sleep.
_transport: httpx.AsyncBaseTransport | None = None
_sleep = asyncio.sleep


@dataclass(frozen=True)
class Provider:
    name: str
    base_url: str
    api_key: str
    model: str


def providers() -> list[Provider]:
    """Configured providers in fallback order, skipping unknown names and missing keys."""
    s = get_settings()
    out = []
    for name in s.llm_provider_list:
        if name not in PROVIDERS:
            log.warning("unknown LLM provider %r in LLM_PROVIDERS", name)
            continue
        key = getattr(s, f"{name}_api_key", "")
        if key:
            base_url, default_model = PROVIDERS[name]
            model = getattr(s, f"llm_model_{name}", "") or default_model
            out.append(Provider(name, base_url, key, model))
    return out


@dataclass
class Completion:
    content: str
    provider: str
    model: str
    tool_calls: list[dict[str, Any]] | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    cached: bool = False

    @property
    def message(self) -> dict[str, Any]:
        """The assistant message, ready to append to the conversation."""
        msg: dict[str, Any] = {"role": "assistant", "content": self.content}
        if self.tool_calls:
            msg["tool_calls"] = self.tool_calls
        return msg


class AiUnavailable(Exception):
    """Every provider failed (or none is configured)."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors) or "No AI provider configured")


class _Retryable(Exception):
    def __init__(self, message: str, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


def _body(provider: Provider, messages, tools, stream: bool, params) -> dict[str, Any]:
    body: dict[str, Any] = {"model": provider.model, "messages": messages, **params}
    if tools:
        body["tools"] = tools
    if stream:
        body["stream"] = True
        body["stream_options"] = {"include_usage": True}
    return body


def _check(resp: httpx.Response, text: str) -> None:
    if resp.status_code < 400:
        return
    msg = f"HTTP {resp.status_code}: {text[:200]}"
    if resp.status_code == 429 or resp.status_code >= 500:
        try:
            retry_after = float(resp.headers.get("retry-after", ""))
        except ValueError:
            retry_after = None
        raise _Retryable(msg, retry_after)
    raise RuntimeError(msg)


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=_transport, timeout=get_settings().ai_timeout)


async def _log(
    provider: Provider,
    started: float,
    error: str | None,
    workspace_id: uuid.UUID | None,
    tokens_in: int | None = None,
    tokens_out: int | None = None,
    cached: bool = False,
) -> None:
    # Logging must never break a call.
    try:
        async with SessionLocal() as db:
            db.add(
                AiCall(
                    workspace_id=workspace_id,
                    provider=provider.name,
                    model=provider.model,
                    latency_ms=int((time.monotonic() - started) * 1000),
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    ok=error is None,
                    error=error[:500] if error else None,
                    cached=cached,
                )
            )
            await db.commit()
    except Exception:
        log.exception("could not log ai call")


async def _attempts(workspace_id: uuid.UUID | None, attempt):
    """Run `attempt(provider)` over providers with retries; return the first success."""
    errors: list[str] = []
    tries = max(1, get_settings().ai_attempts)
    for provider in providers():
        for i in range(tries):
            started = time.monotonic()
            try:
                return await attempt(provider, started)
            except (_Retryable, httpx.TimeoutException, httpx.TransportError) as e:
                error = f"{type(e).__name__}: {e}"
                await _log(provider, started, error, workspace_id)
                errors.append(f"{provider.name}: {error}")
                if i + 1 < tries:
                    delay = getattr(e, "retry_after", None) or 0.5 * 2**i
                    await _sleep(min(delay, 8.0))
            except Exception as e:  # noqa: BLE001 - bad key, bad request: try the next provider
                error = f"{type(e).__name__}: {e}"
                await _log(provider, started, error, workspace_id)
                errors.append(f"{provider.name}: {error}")
                break
    raise AiUnavailable(errors)


# --- dev cache --------------------------------------------------------------------------


def _cache_path(messages, tools, params) -> Path | None:
    s = get_settings()
    if not s.ai_cache:
        return None
    raw = json.dumps({"m": messages, "t": tools, "p": params}, sort_keys=True, default=str)
    return Path(s.ai_cache_dir) / f"{hashlib.sha256(raw.encode()).hexdigest()}.json"


def _cache_get(path: Path | None) -> Completion | None:
    if path is None or not path.exists():
        return None
    try:
        return Completion(**{**json.loads(path.read_text()), "cached": True})
    except Exception:  # noqa: BLE001 - a corrupt entry is just a miss
        return None


def _cache_put(path: Path | None, completion: Completion) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(completion), ensure_ascii=False))


# --- non-streaming ----------------------------------------------------------------------


async def _complete(messages, tools, workspace_id, params) -> Completion:
    path = _cache_path(messages, tools, params)
    if hit := _cache_get(path):
        return hit

    async def attempt(provider: Provider, started: float) -> Completion:
        async with _client() as http:
            resp = await http.post(
                f"{provider.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {provider.api_key}"},
                json=_body(provider, messages, tools, False, params),
            )
        _check(resp, resp.text)
        data = resp.json()
        msg = data["choices"][0]["message"]
        usage = data.get("usage") or {}
        result = Completion(
            content=msg.get("content") or "",
            provider=provider.name,
            model=data.get("model") or provider.model,
            tool_calls=msg.get("tool_calls") or None,
            tokens_in=usage.get("prompt_tokens"),
            tokens_out=usage.get("completion_tokens"),
        )
        await _log(provider, started, None, workspace_id, result.tokens_in, result.tokens_out)
        return result

    result = await _attempts(workspace_id, attempt)
    _cache_put(path, result)
    return result


# --- streaming --------------------------------------------------------------------------


@dataclass
class Stream:
    """Async iterator of text deltas; `completion` is filled in when the stream ends."""

    messages: list[dict[str, Any]]
    tools: list[dict[str, Any]] | None
    workspace_id: uuid.UUID | None
    params: dict[str, Any]
    completion: Completion | None = field(default=None, init=False)

    def __aiter__(self) -> AsyncIterator[str]:
        return self._run()

    async def _run(self) -> AsyncIterator[str]:
        path = _cache_path(self.messages, self.tools, {**self.params, "stream": True})
        if hit := _cache_get(path):
            self.completion = hit
            if hit.content:
                yield hit.content
            return

        async def attempt(provider: Provider, started: float):
            # Open the stream and read up to the first event, so failures here can fall back.
            http = _client()
            try:
                req = http.build_request(
                    "POST",
                    f"{provider.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {provider.api_key}"},
                    json=_body(provider, self.messages, self.tools, True, self.params),
                )
                resp = await http.send(req, stream=True)
                if resp.status_code >= 400:
                    _check(resp, (await resp.aread()).decode(errors="replace"))
                events = _sse_events(resp)
                first = await anext(events, None)
            except BaseException:
                await http.aclose()
                raise
            return provider, started, http, events, first

        provider, started, http, events, first = await _attempts(self.workspace_id, attempt)
        content: list[str] = []
        calls: dict[int, dict[str, Any]] = {}
        model, usage = provider.model, {}
        error: str | None = None
        try:
            event = first
            while event is not None:
                model = event.get("model") or model
                usage = event.get("usage") or (event.get("x_groq") or {}).get("usage") or usage
                for choice in event.get("choices") or []:
                    delta = choice.get("delta") or {}
                    for tc in delta.get("tool_calls") or []:
                        _merge_tool_call(calls, tc)
                    if text := delta.get("content"):
                        content.append(text)
                        yield text
                event = await anext(events, None)
        except GeneratorExit:
            error = "cancelled by the caller"
            raise
        except BaseException as e:
            error = f"{type(e).__name__}: {e}"
            raise
        finally:
            await http.aclose()
            tokens = (usage.get("prompt_tokens"), usage.get("completion_tokens"))
            await _log(provider, started, error, self.workspace_id, *tokens)

        self.completion = Completion(
            content="".join(content),
            provider=provider.name,
            model=model,
            tool_calls=[calls[i] for i in sorted(calls)] or None,
            tokens_in=usage.get("prompt_tokens"),
            tokens_out=usage.get("completion_tokens"),
        )
        _cache_put(path, self.completion)


async def _sse_events(resp: httpx.Response) -> AsyncIterator[dict[str, Any]]:
    async for line in resp.aiter_lines():
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            return
        if data:
            yield json.loads(data)


def _merge_tool_call(calls: dict[int, dict[str, Any]], delta: dict[str, Any]) -> None:
    # Streamed tool calls arrive in pieces keyed by index; arguments are concatenated.
    call = calls.setdefault(
        delta.get("index", 0),
        {"id": "", "type": "function", "function": {"name": "", "arguments": ""}},
    )
    if delta.get("id"):
        call["id"] = delta["id"]
    fn = delta.get("function") or {}
    call["function"]["name"] += fn.get("name") or ""
    call["function"]["arguments"] += fn.get("arguments") or ""


# --- public entry point -----------------------------------------------------------------


@overload
def complete(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    *,
    stream: Literal[False] = False,
    workspace_id: uuid.UUID | None = None,
    **params: Any,
) -> Coroutine[Any, Any, Completion]: ...


@overload
def complete(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    *,
    stream: Literal[True],
    workspace_id: uuid.UUID | None = None,
    **params: Any,
) -> Stream: ...


def complete(messages, tools=None, *, stream=False, workspace_id=None, **params):
    """Chat completion. `await` it, or with stream=True iterate it with `async for`.

    Extra keyword arguments (temperature, max_tokens, response_format, ...) are passed through
    to the provider.
    """
    if stream:
        return Stream(messages, tools, workspace_id, params)
    return _complete(messages, tools, workspace_id, params)
