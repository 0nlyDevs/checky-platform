"""AI gateway: one `complete()` over OpenAI-compatible providers, with retries and fallback.

    reply = await complete([{"role": "user", "content": "Bonjour"}])
    reply.content, reply.provider

    stream = complete(messages, stream=True)
    async for text in stream:
        ...
    stream.completion.provider   # set once the stream is finished

Providers are tried in LLM_PROVIDERS order; one without an API key is skipped, and a key list
(`GROQ_API_KEY=k1,k2`) is used in turn. A 429 sets that key aside for AI_COOLDOWN seconds and
moves on at once; 5xx and timeouts are retried with backoff first. A prompt larger than a
provider's LLM_MAX_PROMPT_TOKENS_* skips it. A stream can only fall back before its first
chunk. Every attempt is logged to app.ai_call (no prompt text). With AI_CACHE=true identical
requests are answered from app.ai_cache.
"""

import asyncio
import hashlib
import json
import logging
import time
import uuid
from collections.abc import AsyncIterator, Coroutine
from dataclasses import asdict, dataclass, field
from typing import Any, Literal, overload

import httpx

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.models import AiCacheEntry, AiCall

log = logging.getLogger("fanilo.ai")

# name -> (OpenAI-compatible base URL, default model)
PROVIDERS: dict[str, tuple[str, str]] = {
    "groq": ("https://api.groq.com/openai/v1", "openai/gpt-oss-120b"),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai", "gemini-3.5-flash-lite"),
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


# In-process state: which key of each provider goes first next time, and keys set aside until
# a monotonic time after a 429 or repeated failures.
_turn: dict[str, int] = {}
_cooldown: dict[tuple[str, str], float] = {}


def _keys(name: str) -> list[str]:
    raw = getattr(get_settings(), f"{name}_api_key", "") or ""
    return [k.strip() for k in raw.split(",") if k.strip()]


def providers(prompt_tokens: int | None = None) -> list[Provider]:
    """Configured provider keys in fallback order.

    Keys of one provider rotate between calls; keys cooling down after a 429 go last; a provider
    whose LLM_MAX_PROMPT_TOKENS_* is below `prompt_tokens` is left out (unless that leaves none).
    """
    s = get_settings()
    out: list[Provider] = []
    for name in s.llm_provider_list:
        if name not in PROVIDERS:
            log.warning("unknown LLM provider %r in LLM_PROVIDERS", name)
            continue
        keys = _keys(name)
        if not keys:
            continue
        start = _turn.get(name, 0) % len(keys)
        _turn[name] = start + 1
        base_url, default_model = PROVIDERS[name]
        model = getattr(s, f"llm_model_{name}", "") or default_model
        out.extend(Provider(name, base_url, k, model) for k in keys[start:] + keys[:start])
    if prompt_tokens:
        fits = [
            p
            for p in out
            if not (limit := getattr(s, f"llm_max_prompt_tokens_{p.name}", 0))
            or prompt_tokens <= limit
        ]
        out = fits or out
    now = time.monotonic()
    ready = [p for p in out if _cooldown.get((p.name, p.api_key), 0) <= now]
    cooling = sorted(
        (p for p in out if p not in ready), key=lambda p: _cooldown[(p.name, p.api_key)]
    )
    return ready + cooling


def estimate_tokens(messages: Any, tools: Any = None) -> int:
    """Rough prompt size: about 3 characters per token for French JSON, on the safe side."""
    return len(json.dumps([messages, tools], ensure_ascii=False)) // 3


def _set_aside(p: Provider, seconds: float) -> None:
    _cooldown[(p.name, p.api_key)] = time.monotonic() + seconds


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
    def __init__(self, message: str, retry_after: float | None = None, status: int = 0):
        super().__init__(message)
        self.retry_after = retry_after
        self.status = status


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
        raise _Retryable(msg, retry_after, resp.status_code)
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


async def _attempts(workspace_id: uuid.UUID | None, attempt, prompt_tokens: int | None = None):
    """Run `attempt(provider)` over provider keys with retries; return the first success."""
    s = get_settings()
    errors: list[str] = []
    tries = max(1, s.ai_attempts)
    for provider in providers(prompt_tokens):
        for i in range(tries):
            started = time.monotonic()
            try:
                return await attempt(provider, started)
            except (_Retryable, httpx.TimeoutException, httpx.TransportError) as e:
                error = f"{type(e).__name__}: {e}"
                await _log(provider, started, error, workspace_id)
                errors.append(f"{provider.name}: {error}")
                if getattr(e, "status", 0) == 429:
                    # Rate limited: waiting would only make the user wait; set the key aside.
                    wait = getattr(e, "retry_after", None) or s.ai_cooldown
                    _set_aside(provider, min(max(wait, 5.0), 120.0))
                    break
                if i + 1 < tries:
                    delay = getattr(e, "retry_after", None) or 0.5 * 2**i
                    await _sleep(min(delay, 8.0))
                else:
                    _set_aside(provider, s.ai_cooldown)
            except Exception as e:  # noqa: BLE001 - bad key, bad request: try the next provider
                error = f"{type(e).__name__}: {e}"
                await _log(provider, started, error, workspace_id)
                errors.append(f"{provider.name}: {error}")
                break
    raise AiUnavailable(errors)


async def check_providers() -> dict[str, dict[str, Any]]:
    """Up/down per provider in LLM_PROVIDERS order, via the free `/models` list (no tokens)."""
    configured = {p.name: p for p in providers()}

    async def check(name: str) -> tuple[str, dict[str, Any]]:
        p = configured.get(name)
        if p is None:
            return name, {"status": "not_configured"}
        started = time.monotonic()
        try:
            async with httpx.AsyncClient(transport=_transport, timeout=5) as http:
                resp = await http.get(
                    f"{p.base_url}/models", headers={"Authorization": f"Bearer {p.api_key}"}
                )
            status = "up" if resp.status_code < 400 else "down"
            detail = None if status == "up" else f"HTTP {resp.status_code}"
        except httpx.HTTPError as e:
            status, detail = "down", type(e).__name__
        latency = int((time.monotonic() - started) * 1000)
        return name, {"status": status, "model": p.model, "latency_ms": latency, "detail": detail}

    names = [n for n in get_settings().llm_provider_list if n in PROVIDERS]
    return dict(await asyncio.gather(*(check(n) for n in names)))


# --- cache ------------------------------------------------------------------------------


def _cache_key(messages, tools, params) -> str | None:
    if not get_settings().ai_cache:
        return None
    raw = json.dumps({"m": messages, "t": tools, "p": params}, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


async def _cache_get(key: str | None) -> Completion | None:
    if key is None:
        return None
    try:
        async with SessionLocal() as db:
            entry = await db.get(AiCacheEntry, key)
        return Completion(**{**entry.value, "cached": True}) if entry else None
    except Exception:
        log.exception("ai cache read failed")
        return None


async def _cache_put(key: str | None, completion: Completion) -> None:
    if key is None:
        return
    try:
        async with SessionLocal() as db:
            await db.merge(AiCacheEntry(key=key, value=asdict(completion)))
            await db.commit()
    except Exception:
        log.exception("ai cache write failed")


# --- non-streaming ----------------------------------------------------------------------


async def _complete(messages, tools, workspace_id, params) -> Completion:
    key = _cache_key(messages, tools, params)
    if hit := await _cache_get(key):
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

    result = await _attempts(workspace_id, attempt, estimate_tokens(messages, tools))
    await _cache_put(key, result)
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
        key = _cache_key(self.messages, self.tools, {**self.params, "stream": True})
        if hit := await _cache_get(key):
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

        provider, started, http, events, first = await _attempts(
            self.workspace_id, attempt, estimate_tokens(self.messages, self.tools)
        )
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
        await _cache_put(key, self.completion)


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
