import socketio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.errors import install_error_handlers
from app.modules import health, me
from app.realtime.server import sio

api = FastAPI(title="FANILO API", version="0.1.0")
api.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
install_error_handlers(api)
api.include_router(health.router, prefix="/api/v1", tags=["health"])
api.include_router(me.router, prefix="/api/v1", tags=["me"])

# Socket.IO shares the process and port with the API; uvicorn serves `app.main:app`.
app = socketio.ASGIApp(sio, other_asgi_app=api)
