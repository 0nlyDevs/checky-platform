import redis.asyncio as redis
from fastapi import APIRouter
from sqlalchemy import text

from app.core.config import get_settings
from app.core.db import engine

router = APIRouter()


async def _check_db() -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("select 1"))
        return True
    except Exception:  # noqa: BLE001 - any failure means the dependency is down
        return False


async def _check_redis() -> bool:
    try:
        client = redis.from_url(get_settings().redis_url)
        try:
            return bool(await client.ping())
        finally:
            await client.aclose()
    except Exception:  # noqa: BLE001 - any failure means the dependency is down
        return False


@router.get("/health")
async def health() -> dict:
    # Storage and AI provider checks are added with their modules (M4, M7).
    checks = {"database": await _check_db(), "redis": await _check_redis()}
    return {"ok": all(checks.values()), "checks": checks}
