"""Shared HTTP clients, so calls to the AI providers reuse their open connections.

A fresh client pays DNS, TCP and TLS on every call: measured from the API to Groq, a small request
took 3.4 s (median) with a new client against 0.7 s on a kept-alive one, and a spoken turn makes five
or six such calls (transcription, model turns, embedding, voice). One client is kept per service,
event loop, transport and timeout: tests swap transports and run each job in a loop of its own.
"""

import asyncio

import httpx

# Idle connections stay open between the turns of a conversation (httpx's default is 5 s).
LIMITS = httpx.Limits(max_connections=50, max_keepalive_connections=20, keepalive_expiry=60)

_clients: dict[str, tuple[asyncio.AbstractEventLoop, object, float, httpx.AsyncClient]] = {}


def shared(
    name: str, transport: httpx.AsyncBaseTransport | None, timeout: float
) -> httpx.AsyncClient:
    """The kept-alive client for `name`. Never close it: close the responses you stream instead."""
    loop = asyncio.get_running_loop()
    hit = _clients.get(name)
    if (
        hit
        and hit[0] is loop
        and hit[1] is transport
        and hit[2] == timeout
        and not hit[3].is_closed
    ):
        return hit[3]
    client = httpx.AsyncClient(transport=transport, timeout=timeout, limits=LIMITS)
    _clients[name] = (loop, transport, timeout, client)
    return client
