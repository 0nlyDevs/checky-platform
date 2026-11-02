import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Activity
from app.realtime.server import emit


async def record(
    db: AsyncSession,
    ws: uuid.UUID,
    actor_id: str,
    entity: str,
    entity_id: uuid.UUID,
    action: str,
    diff: dict[str, Any] | None = None,
) -> None:
    """Log the change (flushed with the caller's commit)."""
    db.add(
        Activity(
            workspace_id=ws,
            actor_id=actor_id,
            entity=entity,
            entity_id=entity_id,
            action=action,
            diff=diff or {},
        )
    )


async def broadcast(ws: uuid.UUID, event: str, payload: dict[str, Any]) -> None:
    await emit(ws, event, payload)
