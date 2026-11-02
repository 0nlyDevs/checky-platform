import uuid
from typing import Any

import socketio

from app.core.config import get_settings
from app.core.errors import ApiError
from app.core.security import decode_token

sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins=get_settings().cors_origin_list)


def room(ws: uuid.UUID | str) -> str:
    return f"ws:{ws}"


async def emit(ws: uuid.UUID, event: str, payload: dict[str, Any]) -> None:
    await sio.emit(event, payload, room=room(ws))


@sio.event
async def connect(sid, environ, auth):
    # Reject the handshake unless it carries a valid Better Auth JWT.
    token = (auth or {}).get("token")
    if not token:
        raise socketio.exceptions.ConnectionRefusedError("unauthorized")
    try:
        user = decode_token(token)
    except ApiError as e:
        raise socketio.exceptions.ConnectionRefusedError("invalid_token") from e
    await sio.save_session(sid, {"user_id": user.id})


@sio.event
async def join(sid, ws_id: str):
    from app.core.access import get_membership  # avoid an import cycle at module load
    from app.core.db import SessionLocal

    session = await sio.get_session(sid)
    try:
        ws = uuid.UUID(ws_id)
    except (ValueError, TypeError):
        return {"ok": False, "error": "bad_workspace"}
    async with SessionLocal() as db:
        membership = await get_membership(db, ws, session["user_id"])
        if membership is None or membership.role not in ("admin", "editor", "journalist"):
            return {"ok": False, "error": "not_found"}
    await sio.enter_room(sid, room(ws))
    return {"ok": True}
