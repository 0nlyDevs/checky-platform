import asyncio
from contextlib import asynccontextmanager, suppress

import socketio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.client_ip import ClientAddress
from app.core.config import get_settings
from app.core.errors import install_error_handlers
from app.modules import (
    agent,
    ai,
    alert_kit,
    alerts,
    card,
    checker,
    copilot,
    crew,
    demo,
    directory,
    extension_public,
    figures,
    gestures,
    guide,
    health,
    imagecheck,
    items,
    jobs,
    linkcheck,
    live,
    me,
    media_api,
    official,
    onair,
    public,
    quotes,
    rag,
    registry,
    rubrique,
    signing,
    sms,
    sms_gateway,
    sources,
    studio,
    trajet,
    translate,
    veille,
    verification,
    verify_public,
    voicenote,
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


api = FastAPI(title="Checky API", version="0.1.0", lifespan=lifespan)
api.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # The PDFs' file names (carnet-FAN-0142.pdf) are read by the desk across origins.
    expose_headers=["Content-Disposition"],
)
# Added last so it runs first: every limiter reads the address it sets.
api.add_middleware(ClientAddress)
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
api.include_router(imagecheck.router, prefix="/api/v1")
api.include_router(media_api.router, prefix="/api/v1")
api.include_router(extension_public.router, prefix="/api/v1")
api.include_router(crew.router, prefix="/api/v1")
api.include_router(directory.router, prefix="/api/v1")
api.include_router(figures.router, prefix="/api/v1")
api.include_router(registry.router, prefix="/api/v1")
api.include_router(rubrique.router, prefix="/api/v1")
api.include_router(signing.router, prefix="/api/v1")
api.include_router(trajet.router, prefix="/api/v1")
api.include_router(translate.router, prefix="/api/v1")
api.include_router(veille.router, prefix="/api/v1")
api.include_router(verify_public.router, prefix="/api/v1")
api.include_router(sms.router, prefix="/api/v1")
api.include_router(sms_gateway.router, prefix="/api/v1")
api.include_router(studio.router, prefix="/api/v1")
api.include_router(onair.router, prefix="/api/v1")
api.include_router(verification.router, prefix="/api/v1")
api.include_router(official.router, prefix="/api/v1")
api.include_router(alerts.router, prefix="/api/v1")
api.include_router(alert_kit.router, prefix="/api/v1")
api.include_router(live.router, prefix="/api/v1")
api.include_router(gestures.router, prefix="/api/v1")
api.include_router(voicenote.router, prefix="/api/v1")

# Socket.IO shares the process and port with the API; uvicorn serves `app.main:app`.
app = socketio.ASGIApp(sio, other_asgi_app=api)
