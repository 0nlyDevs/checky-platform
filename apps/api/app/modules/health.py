from fastapi import APIRouter
from sqlalchemy import text

from app.core.db import engine

router = APIRouter()


async def _check_db() -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("select 1"))
        return True
    except Exception:  # noqa: BLE001 - any failure means the dependency is down
        return False


@router.get("/health")
async def health() -> dict:
    # Storage and AI provider checks are added with their modules (M4, M7).
    checks = {"database": await _check_db()}
    return {"ok": all(checks.values()), "checks": checks}
