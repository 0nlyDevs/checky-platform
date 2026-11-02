"""Embeddings through an OpenAI-compatible `/embeddings` endpoint (Gemini by default).

    vectors = await embed(["passage one", "passage two"])   # list of EMBED_DIM floats each

One provider for the whole event: vectors from different models cannot be compared, so the
model name is stored with every chunk and a switch means rebuilding them all.
"""

import asyncio
import time

import httpx

from app.core import ai
from app.core.config import get_settings

BATCH = 64

# Tests swap these for an httpx.MockTransport and a no-op sleep.
_transport: httpx.AsyncBaseTransport | None = None
_sleep = asyncio.sleep


class EmbedUnavailable(Exception):
    pass


def _provider() -> ai.Provider | None:
    s = get_settings()
    name = s.embed_provider
    key = getattr(s, f"{name}_api_key", "") if name in ai.PROVIDERS else ""
    if not key:
        return None
    return ai.Provider(name, ai.PROVIDERS[name][0], key, s.embed_model)


def configured() -> bool:
    return _provider() is not None


async def embed(texts: list[str]) -> list[list[float]]:
    p = _provider()
    if p is None:
        raise EmbedUnavailable(f"No API key for embedding provider {get_settings().embed_provider}")
    out: list[list[float]] = []
    for i in range(0, len(texts), BATCH):
        out.extend(await _batch(p, texts[i : i + BATCH]))
    return out


async def _batch(p: ai.Provider, texts: list[str]) -> list[list[float]]:
    s = get_settings()
    log_as = ai.Provider(f"{p.name}-embed", p.base_url, "", p.model)
    errors = []
    for attempt in range(max(1, s.ai_attempts) + 1):
        started = time.monotonic()
        try:
            async with httpx.AsyncClient(transport=_transport, timeout=s.ai_timeout) as http:
                resp = await http.post(
                    f"{p.base_url}/embeddings",
                    headers={"Authorization": f"Bearer {p.api_key}"},
                    json={"model": p.model, "input": texts, "dimensions": s.embed_dim},
                )
            if resp.status_code == 429 or resp.status_code >= 500:
                raise httpx.HTTPStatusError(
                    f"HTTP {resp.status_code}", request=resp.request, response=resp
                )
            if resp.status_code >= 400:
                await ai._log(log_as, started, f"HTTP {resp.status_code}", None)
                raise EmbedUnavailable(f"HTTP {resp.status_code}: {resp.text[:200]}")
            # Gemini's compatibility endpoint omits `index`; its results come back in order.
            data = resp.json()["data"]
            if all("index" in d for d in data):
                data = sorted(data, key=lambda d: d["index"])
            vectors = [d["embedding"] for d in data]
            if any(len(v) != s.embed_dim for v in vectors):
                raise EmbedUnavailable(f"Expected {s.embed_dim} dimensions from {p.model}")
            await ai._log(log_as, started, None, None)
            return vectors
        except (httpx.HTTPStatusError, httpx.TimeoutException, httpx.TransportError) as e:
            errors.append(f"{type(e).__name__}: {e}")
            await ai._log(log_as, started, errors[-1], None)
            await _sleep(min(2.0 * 2**attempt, 16.0))
    raise EmbedUnavailable("; ".join(errors))
