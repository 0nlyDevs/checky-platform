"""FAN references (FAN-0142) and alert references (ALR-0007), allocated atomically per newsroom.

The counter lives in `workspace.settings.ref_counter` (no migration). One `UPDATE … RETURNING`
takes the workspace row's lock, so two tips arriving together wait for each other instead of both
reading the same « max + 1 ». The new value is the larger of the counter and the highest FAN
number already on an item, plus one: the first allocation seeds itself from the existing refs, and
refs written another way (the demo seeds FAN-0137…) never collide. Under READ COMMITTED a waiting
update re-reads the counter its predecessor committed, so even a stale « highest item » cannot
hand out the same number twice. The lock is held until the caller commits. Each prefix has its own
counter key (`ref_counter` for FAN, `alert_counter` for ALR).
"""

import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_COUNTERS = {"FAN": "ref_counter", "ALR": "alert_counter"}

_SQL = r"""
    UPDATE app.workspace
    SET settings = jsonb_set(
        COALESCE(settings, '{{}}'::jsonb),
        '{{{key}}}',
        to_jsonb(GREATEST(
            COALESCE(CASE WHEN settings->>'{key}' ~ '^[0-9]{{1,18}}$'
                          THEN (settings->>'{key}')::bigint END, 0),
            (SELECT COALESCE(MAX(substring(i.data->>'ref' FROM '^{prefix}-([0-9]{{1,18}})$')::bigint), 0)
             FROM app.item i WHERE i.workspace_id = :ws)
        ) + 1)
    )
    WHERE id = :ws
    RETURNING (settings->>'{key}')::bigint
    """

# Built once from the fixed table above: no caller value reaches the SQL text.
_NEXT = {prefix: text(_SQL.format(key=key, prefix=prefix)) for prefix, key in _COUNTERS.items()}


async def next_ref(db: AsyncSession, ws: uuid.UUID, prefix: str = "FAN") -> str:
    n = await db.scalar(_NEXT[prefix], {"ws": ws})
    return f"{prefix}-{(n or 1):04d}"
