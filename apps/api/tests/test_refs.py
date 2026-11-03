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


def test_clients_cannot_poison_a_newsrooms_reference_counter(as_user):
    alice = as_user("alice")
    ws = uuid.UUID(_workspace(alice))
    base = f"/api/v1/workspaces/{ws}/items"
    huge = "FAN-" + "9" * 1000
    assert alice.post(base, json={"title": "forged", "data": {"ref": huge}}).status_code == 422
    made = alice.post(base, json={"title": "ordinary"})
    assert made.status_code == 201
    item_id = made.json()["id"]
    # A dossier created from the desk takes the first reference itself; the forged one took none.
    assert made.json()["data"]["ref"] == "FAN-0001"
    assert alice.patch(f"{base}/{item_id}", json={"data": {"ref": huge}}).status_code == 422
    assert _allocate(ws, 1) == ["FAN-0002"]


def test_existing_oversized_reference_does_not_break_allocation(as_user):
    ws = uuid.UUID(_workspace(as_user("alice")))

    async def seed():
        async with SessionLocal() as db:
            db.add(
                Item(
                    workspace_id=ws,
                    author_id="alice",
                    type="claim",
                    title="old bad ref",
                    data={"ref": "FAN-" + "9" * 1000},
                )
            )
            await db.commit()

    asyncio.run(seed())
    assert _allocate(ws, 1) == ["FAN-0001"]


def test_alert_refs_have_their_own_counter_seeded_from_existing_alerts(as_user):
    ws = uuid.UUID(_workspace(as_user("alice")))

    async def go():
        async with SessionLocal() as db:
            db.add(
                Item(
                    workspace_id=ws,
                    author_id="checky",
                    type="alert",
                    title="old alert",
                    data={"ref": "ALR-0003"},
                )
            )
            await db.commit()
            alert = await next_ref(db, ws, "ALR")
            claim = await next_ref(db, ws)
            await db.commit()
            return alert, claim

    assert asyncio.run(go()) == ("ALR-0004", "FAN-0001")
