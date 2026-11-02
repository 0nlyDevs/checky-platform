import asyncio
import time
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text

from app.core import ai, storage
from app.core.db import engine

router = APIRouter()

# Public endpoint that pings external providers: answer from a short cache so it can't be
# used to burn rate limits.
CACHE_SECONDS = 15.0
_cache: tuple[float, "HealthOut"] | None = None


class Check(BaseModel):
    status: Literal["up", "down", "not_configured"]
    latency_ms: int | None = None
    detail: str | None = None
    model: str | None = None


class HealthOut(BaseModel):
    ok: bool
    checks: dict[str, Check]
    ai: dict[str, Check]


async def _check_db() -> dict:
    started = time.monotonic()
    try:
        async with engine.connect() as conn:
            await asyncio.wait_for(conn.execute(text("select 1")), 5)
        status, detail = "up", None
    except Exception as e:  # noqa: BLE001 - any failure means the dependency is down
        status, detail = "down", type(e).__name__
    return {
        "status": status,
        "latency_ms": int((time.monotonic() - started) * 1000),
        "detail": detail,
    }


@router.get("/health")
async def health() -> HealthOut:
    """Database, storage and each AI provider: up, down or not configured.

    `ok` means the database is up, nothing configured is down, and at least one AI provider
    answers (when any is configured).
    """
    global _cache
    if _cache and time.monotonic() - _cache[0] < CACHE_SECONDS:
        return _cache[1]
    db, store, providers = await asyncio.gather(_check_db(), storage.check(), ai.check_providers())
    checks = {"database": Check(**db), "storage": Check(**store)}
    ai_checks = {name: Check(**c) for name, c in providers.items()}
    configured_ai = [c for c in ai_checks.values() if c.status != "not_configured"]
    ok = (
        checks["database"].status == "up"
        and checks["storage"].status != "down"
        and (not configured_ai or any(c.status == "up" for c in configured_ai))
    )
    out = HealthOut(ok=ok, checks=checks, ai=ai_checks)
    _cache = (time.monotonic(), out)
    return out
