"""FAN references (FAN-0142), allocated atomically per newsroom.

The counter lives in `workspace.settings.ref_counter` (no migration). One `UPDATE … RETURNING`
takes the workspace row's lock, so two tips arriving together wait for each other instead of both
reading the same « max + 1 ». The new value is the larger of the counter and the highest FAN
number already on an item, plus one: the first allocation seeds itself from the existing refs, and
refs written another way (the demo seeds FAN-0137…) never collide. Under READ COMMITTED a waiting
update re-reads the counter its predecessor committed, so even a stale « highest item » cannot
hand out the same number twice. The lock is held until the caller commits.
"""

import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_NEXT = text(
    r"""
    UPDATE app.workspace
    SET settings = jsonb_set(
        COALESCE(settings, '{}'::jsonb),
        '{ref_counter}',
        to_jsonb(GREATEST(
            COALESCE(CASE WHEN settings->>'ref_counter' ~ '^[0-9]{1,18}$'
                          THEN (settings->>'ref_counter')::bigint END, 0),
            (SELECT COALESCE(MAX(substring(i.data->>'ref' FROM '^FAN-([0-9]{1,18})$')::bigint), 0)
             FROM app.item i WHERE i.workspace_id = :ws)
        ) + 1)
    )
    WHERE id = :ws
    RETURNING (settings->>'ref_counter')::bigint
    """
)


async def next_ref(db: AsyncSession, ws: uuid.UUID) -> str:
    n = await db.scalar(_NEXT, {"ws": ws})
    return f"FAN-{(n or 1):04d}"
