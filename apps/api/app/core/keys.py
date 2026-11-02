"""API key lists shared by every outside service (chat, embeddings, transcription, voice,
web search, fact-checks, image detection).

Any `*_API_KEY` may hold several keys separated by commas (one per teammate, or several free
accounts). Calls take them in turn, and a key that hits its quota is set aside for a while so the
next call goes straight to another one. The state is per process, like the rate limits.
"""

import time

# service -> index of the key that goes first next time; (service, key) -> monotonic time it is back
_turn: dict[str, int] = {}
_cooldown: dict[tuple[str, str], float] = {}


def split(raw: str | None) -> list[str]:
    return [k.strip() for k in (raw or "").split(",") if k.strip()]


def rotation(service: str, keys: list[str]) -> list[str]:
    """The keys in the order to try them: the next in turn first, keys cooling down last."""
    if not keys:
        return []
    start = _turn.get(service, 0) % len(keys)
    _turn[service] = start + 1
    ordered = keys[start:] + keys[:start]
    now = time.monotonic()
    ready = [k for k in ordered if _cooldown.get((service, k), 0) <= now]
    cooling = sorted((k for k in ordered if k not in ready), key=lambda k: _cooldown[(service, k)])
    return ready + cooling


def set_aside(service: str, key: str, seconds: float) -> None:
    _cooldown[(service, key)] = time.monotonic() + seconds


def retry_after(headers, default: float) -> float:
    try:
        return max(1.0, float(headers.get("retry-after", "")))
    except ValueError:
        return default
