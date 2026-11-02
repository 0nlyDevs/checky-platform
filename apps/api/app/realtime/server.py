import socketio

from app.core.config import get_settings
from app.core.errors import ApiError
from app.core.security import decode_token

sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins=get_settings().cors_origin_list)


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
