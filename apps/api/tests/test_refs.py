import asyncio
import uuid

from app.core.db import SessionLocal
from app.core.models import Item
from app.core.refs import next_ref
from tests.test_workspaces import _workspace


def _allocate(ws: uuid.UUID, n: int) -> list[str]:
    """`n` allocations at once, each in its own session that creates its item, then commits."""

    async def one(i: int) -> str:
        async with SessionLocal() as db:
            ref = await next_ref(db, ws)
            await asyncio.sleep(0.01 * (i % 3))  # hold the lock a little, as a real route does
            db.add(
                Item(
                    workspace_id=ws,
                    author_id="alice",
                    type="claim",
                    title=f"t{i}",
                    data={"ref": ref},
                )
            )
            await db.commit()
            return ref

    async def go():
        return await asyncio.gather(*(one(i) for i in range(n)))

    return asyncio.run(go())


def test_concurrent_allocations_never_share_a_number(as_user):
    ws = uuid.UUID(_workspace(as_user("alice")))
    refs = _allocate(ws, 12)
    assert len(set(refs)) == 12
    assert sorted(refs) == [f"FAN-{n:04d}" for n in range(1, 13)]


def test_the_counter_seeds_itself_from_the_existing_refs(as_user):
    ws = uuid.UUID(_workspace(as_user("alice")))

    async def go():
        async with SessionLocal() as db:
            db.add(
                Item(
                    workspace_id=ws,
                    author_id="alice",
                    type="claim",
                    title="old",
                    data={"ref": "FAN-0144"},
                )
            )
            await db.commit()
            first = await next_ref(db, ws)
            await db.commit()
            # A ref written another way ahead of the counter (the demo seeds its own) is skipped.
            db.add(
                Item(
                    workspace_id=ws,
                    author_id="alice",
                    type="claim",
                    title="seed",
                    data={"ref": "FAN-0200"},
                )
            )
            await db.commit()
            second = await next_ref(db, ws)
            await db.commit()
            return first, second

    assert asyncio.run(go()) == ("FAN-0145", "FAN-0201")
