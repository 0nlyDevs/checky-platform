"""Rebuild every passage's embedding, e.g. after changing EMBED_MODEL or EMBED_DIM.

    cd apps/api && uv run python scripts/reembed_all.py            # local database
    DATABASE_URL="$PROD_DATABASE_URL" uv run python scripts/reembed_all.py

Queues one `embed_source` job per ready source with text; the API's workers run them.
A different EMBED_DIM also needs a migration of the `chunk.embedding` column first.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.core.db import SessionLocal
from app.core.models import Source
from app.modules import rag
from app.workers.queue import enqueue


async def main() -> None:
    async with SessionLocal() as db:
        sources = list(
            await db.scalars(select(Source).where(Source.status == "ready", Source.text != ""))
        )
        for s in sources:
            await enqueue(
                db, s.workspace_id, s.created_by, "embed_source", {"source_id": str(s.id)}
            )
    print(f"queued {len(sources)} sources for re-embedding ({rag.get_settings().embed_model})")


if __name__ == "__main__":
    asyncio.run(main())
