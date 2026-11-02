"""The visitor's address for rate limits and budgets, which a client must not be able to choose.

Render serves the API behind Cloudflare. uvicorn's `--forwarded-allow-ips=*` keeps the scheme
right but takes the *first* X-Forwarded-For entry as the client, and that entry is whatever the
caller sent: one fake header per request reset every per-address limit (seen live on 2 Nov).
Cloudflare sets CF-Connecting-IP itself, so on Render (`RENDER` is set by the platform) the client
address comes from that header; elsewhere, from `CLIENT_IP_HEADER` if configured. Without the
header, the last X-Forwarded-For entry (added by the nearest proxy) is used, never the first.
"""

import ipaddress
import os

from app.core.config import get_settings


def trusted_header() -> bytes | None:
    name = get_settings().client_ip_header.strip().lower()
    if not name and os.environ.get("RENDER"):
        name = "cf-connecting-ip"
    return name.encode("latin-1") if name else None


def _address(raw: bytes | None) -> str | None:
    if not raw:
        return None
    value = raw.decode("latin-1").strip()
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        return None


class ClientAddress:
    """Pure ASGI middleware: rewrites scope["client"] before any route or limiter reads it."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        header = trusted_header() if scope["type"] in ("http", "websocket") else None
        if header:
            headers = dict(scope.get("headers") or [])
            forwarded = headers.get(b"x-forwarded-for", b"").split(b",")
            address = _address(headers.get(header)) or _address(forwarded[-1])
            if address:
                port = scope["client"][1] if scope.get("client") else 0
                scope = {**scope, "client": (address, port)}
        await self.app(scope, receive, send)
