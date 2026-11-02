import asyncio
import uuid

from app.core.access import require_member
from app.core.db import SessionLocal
from app.core.security import CurrentUser
from tests.test_workspaces import _workspace


def test_the_membership_check_closes_its_transaction_before_the_route_runs(as_user):
    """An SSE route keeps its session for minutes: the membership read must not hold it open."""
    ws = uuid.UUID(_workspace(as_user("alice")))
    alice = CurrentUser(id="alice", email=None, name=None)

    async def go():
        async with SessionLocal() as db:
            member = await require_member(ws, alice, db)
            assert member.workspace_id == ws
            assert not db.in_transaction()

    asyncio.run(go())
