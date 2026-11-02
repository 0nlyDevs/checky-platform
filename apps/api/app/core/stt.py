"""Speech-to-text through Groq Whisper (OpenAI-compatible `/audio/transcriptions`).

result = await transcribe(raw_bytes, "interview.m4a", "audio/mp4", language="fr")
result["text"], result["segments"]  # segments: [{start, end, text}]
"""

import asyncio
import time
from typing import Any

import httpx

from app.core import ai
from app.core.config import get_settings

URL = "https://api.groq.com/openai/v1/audio/transcriptions"

# Tests swap these for an httpx.MockTransport and a no-op sleep.
_transport: httpx.AsyncBaseTransport | None = None
_sleep = asyncio.sleep


class SttUnavailable(Exception):
    pass


async def transcribe(
    raw: bytes, filename: str, mime: str, language: str | None = None
) -> dict[str, Any]:
    s = get_settings()
    if not s.groq_api_key:
        raise SttUnavailable("GROQ_API_KEY is not set")
    data = {"model": s.stt_model, "response_format": "verbose_json", "temperature": "0"}
    if language:
        data["language"] = language
    errors = []
    for attempt in range(max(1, s.ai_attempts)):
        started = time.monotonic()
        try:
            async with httpx.AsyncClient(transport=_transport, timeout=s.stt_timeout) as http:
                resp = await http.post(
                    URL,
                    headers={"Authorization": f"Bearer {s.groq_api_key}"},
                    data=data,
                    files={"file": (filename, raw, mime)},
                )
            if resp.status_code == 429 or resp.status_code >= 500:
                raise httpx.HTTPStatusError(
                    f"HTTP {resp.status_code}", request=resp.request, response=resp
                )
            if resp.status_code >= 400:
                raise SttUnavailable(f"HTTP {resp.status_code}: {resp.text[:200]}")
            body = resp.json()
            await _log(s.stt_model, started, None)
            return {
                "text": (body.get("text") or "").strip(),
                "language": body.get("language"),
                "duration_s": body.get("duration"),
                "segments": [
                    {
                        "start": round(g["start"], 2),
                        "end": round(g["end"], 2),
                        "text": g["text"].strip(),
                    }
                    for g in body.get("segments") or []
                ],
            }
        except (httpx.HTTPStatusError, httpx.TimeoutException, httpx.TransportError) as e:
            errors.append(f"{type(e).__name__}: {e}")
            await _log(s.stt_model, started, errors[-1])
            if attempt + 1 < max(1, s.ai_attempts):
                await _sleep(min(2.0 * 2**attempt, 8.0))
    raise SttUnavailable("; ".join(errors))


async def _log(model: str, started: float, error: str | None) -> None:
    # Same call log as the chat gateway, so Paramètres-style checks see transcription too.
    await ai._log(ai.Provider("groq-stt", URL, "", model), started, error, None)
