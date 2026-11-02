import asyncio
from contextlib import asynccontextmanager, suppress

import socketio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.errors import install_error_handlers
from app.modules import (
    agent,
    ai,
    card,
    checker,
    copilot,
    demo,
    guide,
    health,
    items,
    jobs,
    linkcheck,
    me,
    public,
    quotes,
    rag,
    sources,
    workspaces,
)
from app.realtime.server import sio
from app.workers import queue


@asynccontextmanager
async def lifespan(_: FastAPI):
    n = get_settings().job_workers
    if n:
        await queue.requeue_interrupted()
    tasks = [asyncio.create_task(queue.worker_loop()) for _ in range(n)]
    yield
    for t in tasks:
        t.cancel()
    for t in tasks:
        with suppress(asyncio.CancelledError):
            await t


api = FastAPI(title="FANILO API", version="0.1.0", lifespan=lifespan)
api.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
install_error_handlers(api)
api.include_router(health.router, prefix="/api/v1", tags=["health"])
api.include_router(me.router, prefix="/api/v1")
api.include_router(workspaces.router, prefix="/api/v1")
api.include_router(items.router, prefix="/api/v1")
api.include_router(jobs.router, prefix="/api/v1")
api.include_router(demo.router, prefix="/api/v1")
api.include_router(ai.router, prefix="/api/v1")
api.include_router(sources.router, prefix="/api/v1")
api.include_router(checker.router, prefix="/api/v1")
api.include_router(rag.router, prefix="/api/v1")
api.include_router(agent.router, prefix="/api/v1")
api.include_router(quotes.router, prefix="/api/v1")
api.include_router(card.router, prefix="/api/v1")
api.include_router(public.router, prefix="/api/v1")
api.include_router(guide.router, prefix="/api/v1")
api.include_router(copilot.router, prefix="/api/v1")
api.include_router(linkcheck.router, prefix="/api/v1")

# Socket.IO shares the process and port with the API; uvicorn serves `app.main:app`.
app = socketio.ASGIApp(sio, other_asgi_app=api)
