"""Seed fixed FAN references in tests without using the public item write API."""

import asyncio
import uuid

from app.core.db import SessionLocal
from app.core.models import Item


def set_ref(item_id: str, ref: str) -> None:
    async def save() -> None:
        async with SessionLocal() as db:
            item = await db.get(Item, uuid.UUID(item_id))
            assert item is not None
            item.data = {**(item.data or {}), "ref": ref}
            await db.commit()

    asyncio.run(save())
