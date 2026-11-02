"""Verify Better Auth JWTs against the web app's JWKS endpoint."""

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Annotated, Any

import httpx
import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core import http
from app.core.config import get_settings
from app.core.errors import ApiError

log = logging.getLogger("fanilo.auth")
_bearer = HTTPBearer(auto_error=False)


class Jwks:
    """The web app's signing keys, fetched without blocking the event loop and kept an hour.

    A token signed with a key we do not know triggers one refetch (Better Auth rotated its key),
    at most every `min_refetch` seconds, so a stream of forged `kid`s cannot hammer the web app.
    Concurrent requests share one fetch.
    """

    transport: httpx.AsyncBaseTransport | None = None  # tests swap in a MockTransport

    def __init__(self, url: str, lifespan: float = 3600, min_refetch: float = 30):
        self.url, self.lifespan, self.min_refetch = url, lifespan, min_refetch
        self._keys: dict[str | None, Any] = {}
        self._fetched = 0.0
        self._lock = asyncio.Lock()

    async def _fetch(self) -> None:
        client = http.shared("jwks", self.transport, 10.0)
        r = await client.get(self.url)
        r.raise_for_status()
        keys: dict[str | None, Any] = {}
        for data in r.json().get("keys", []):
            try:
                keys[data.get("kid")] = jwt.PyJWK(data).key
            except jwt.PyJWTError:
                continue  # an algorithm we do not use
        self._keys, self._fetched = keys, time.monotonic()

    async def key_for(self, token: str) -> Any:
        kid = jwt.get_unverified_header(token).get("kid")
        age = time.monotonic() - self._fetched
        if kid in self._keys and age < self.lifespan:
            return self._keys[kid]
        async with self._lock:
            age = time.monotonic() - self._fetched
            stale = age >= self.lifespan or not self._keys
            if stale or (kid not in self._keys and age >= self.min_refetch):
                try:
                    await self._fetch()
                except (httpx.HTTPError, ValueError) as e:
                    log.warning("JWKS fetch failed: %s", e)
                    if not self._keys:
                        raise jwt.PyJWKClientConnectionError(f"JWKS unreachable: {e}") from e
        if kid not in self._keys:
            if kid is None and len(self._keys) == 1:
                return next(iter(self._keys.values()))
            raise jwt.PyJWKClientError(f"Unknown signing key {kid!r}")
        return self._keys[kid]


_jwks_client: Jwks | None = None


def _jwks() -> Jwks:
    global _jwks_client
    if _jwks_client is None:
        _jwks_client = Jwks(get_settings().auth_jwks_url)
    return _jwks_client


@dataclass(frozen=True)
class CurrentUser:
    id: str
    email: str | None
    name: str | None
    # Better Auth puts the user object in the token; emailVerified is false until a mail is confirmed.
    email_verified: bool = False


async def decode_token(token: str) -> CurrentUser:
    s = get_settings()
    try:
        key = await _jwks().key_for(token)
        claims = jwt.decode(
            token,
            key,
            algorithms=["EdDSA", "ES256", "RS256"],
            issuer=s.auth_issuer,
            audience=s.auth_audience,
            options={"require": ["sub", "exp"]},
        )
    except jwt.PyJWTError as e:
        raise ApiError(401, "invalid_token", f"Invalid token: {e}") from e
    return CurrentUser(
        id=claims["sub"],
        email=claims.get("email"),
        name=claims.get("name"),
        email_verified=claims.get("emailVerified") is True,
    )


async def current_user(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> CurrentUser:
    if creds is None:
        raise ApiError(401, "unauthorized", "Missing bearer token")
    return await decode_token(creds.credentials)


User = Annotated[CurrentUser, Depends(current_user)]
