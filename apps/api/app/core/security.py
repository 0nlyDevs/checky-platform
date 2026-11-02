"""Verify Better Auth JWTs against the web app's JWKS endpoint."""

from dataclasses import dataclass
from typing import Annotated

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import get_settings
from app.core.errors import ApiError

_bearer = HTTPBearer(auto_error=False)
_jwks_client: jwt.PyJWKClient | None = None


def _jwks() -> jwt.PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        # Keys are cached in-process; a new `kid` triggers a refetch.
        _jwks_client = jwt.PyJWKClient(get_settings().auth_jwks_url, cache_keys=True, lifespan=3600)
    return _jwks_client


@dataclass(frozen=True)
class CurrentUser:
    id: str
    email: str | None
    name: str | None


def decode_token(token: str) -> CurrentUser:
    s = get_settings()
    try:
        key = _jwks().get_signing_key_from_jwt(token).key
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
    return CurrentUser(id=claims["sub"], email=claims.get("email"), name=claims.get("name"))


async def current_user(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> CurrentUser:
    if creds is None:
        raise ApiError(401, "unauthorized", "Missing bearer token")
    return decode_token(creds.credentials)


User = Annotated[CurrentUser, Depends(current_user)]
