"""SatyaCheck — authentication (upgrade plan, Phase 1).

Every request names an owner: the Supabase account it acts for. The owner scopes every
read and write (server/database.py sets it on each transaction, and Postgres row-level
security enforces it again).

  * "jwt" mode: an access token signed by the project's asymmetric key (JWKS, cached),
    with the expected issuer and audience. Only RS256/ES256 — an HS256 token is refused,
    so a guessed shared secret can never mint one.
  * "dev" mode (never in production): a request without a token acts as DEV_OWNER_ID,
    so the apps keep working before they have sign-in. A token that IS sent is still
    verified; a bad one is an error, not a silent fall back.

A WebSocket authenticates with its first message, {"type": "auth", "token": ...}, never
in the URL (URLs end up in proxy and access logs).

C owns this file.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Optional

import jwt
from fastapi import HTTPException, Request

import config

log = logging.getLogger("satyacheck.auth")


class AuthError(Exception):
    """The request could not be tied to an owner. The message is safe to log."""


@dataclass(frozen=True)
class Principal:
    owner_id: str
    via: str  # "jwt" | "dev"


_jwks_client: Optional[jwt.PyJWKClient] = None
_jwks_url: str = ""


def _signing_key(token: str):
    """The project's public key for this token's `kid` (JWKS fetched once, then cached)."""
    global _jwks_client, _jwks_url
    if _jwks_client is None or _jwks_url != config.AUTH_JWKS_URL:
        _jwks_client = jwt.PyJWKClient(config.AUTH_JWKS_URL, cache_keys=True, lifespan=600, timeout=5)
        _jwks_url = config.AUTH_JWKS_URL
    return _jwks_client.get_signing_key_from_jwt(token).key


def verify_token(token: str) -> Principal:
    """The owner named by a valid access token. Raises AuthError otherwise."""
    if not config.AUTH_JWKS_URL or not config.AUTH_ISSUER:
        raise AuthError("authentication is not configured (SUPABASE_URL / AUTH_JWKS_URL)")
    try:
        claims = jwt.decode(
            token,
            _signing_key(token),
            algorithms=config.AUTH_ALGORITHMS,
            audience=config.AUTH_AUDIENCE,
            issuer=config.AUTH_ISSUER,
            options={"require": ["exp", "sub", "iss", "aud"]},
        )
    except jwt.PyJWKClientError as e:
        raise AuthError(f"signing key unavailable: {e}") from None
    except jwt.InvalidTokenError as e:
        raise AuthError(f"invalid token: {type(e).__name__}") from None
    except Exception as e:  # noqa: BLE001 — a malformed token must be a 401, never a 500
        raise AuthError(f"invalid token: {type(e).__name__}") from None
    owner = str(claims.get("sub") or "")
    if not owner:
        raise AuthError("token names no account")
    return Principal(owner_id=owner, via="jwt")


def principal_from_header(authorization: Optional[str]) -> Principal:
    if authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            raise AuthError("expected 'Authorization: Bearer <token>'")
        return verify_token(token.strip())
    if config.AUTH_MODE == "dev":
        return Principal(owner_id=config.DEV_OWNER_ID, via="dev")
    raise AuthError("missing access token")


async def current_principal(request: Request) -> Principal:
    """FastAPI dependency: the authenticated principal, or 401."""
    try:
        return principal_from_header(request.headers.get("authorization"))
    except AuthError as e:
        log.info(f"auth refused {request.method} {request.url.path}: {e}")
        raise HTTPException(status_code=401, detail="Sign in required.",
                            headers={"WWW-Authenticate": "Bearer"}) from None


async def verified_principal(request: Request) -> Principal:
    """FastAPI dependency: a principal from a *verified* token only, in every AUTH_MODE.

    `current_principal` lets a tokenless request act as the dev account in dev mode. Some
    features must never do that: an app-to-app call needs two distinct real accounts, or
    both phones become the same identity and a verdict could reach the wrong person."""
    principal = await current_principal(request)
    if principal.via != "jwt":
        log.info(f"auth refused {request.method} {request.url.path}: a verified sign-in is required")
        raise HTTPException(status_code=401, detail="Sign in required.",
                            headers={"WWW-Authenticate": "Bearer"})
    return principal


async def current_owner(request: Request) -> str:
    """FastAPI dependency: the owner id every repository call is scoped to."""
    return (await current_principal(request)).owner_id


async def authenticate_ws(ws, silent_dev_after: Optional[float] = None) -> tuple[Principal, Optional[str]]:
    """Authenticate a WebSocket from its first message.

    Returns (principal, pending): `pending` is the first message when it was not an auth
    message (dev mode only) and must still be processed. Raises AuthError; the caller
    closes with 1008.

    `silent_dev_after`: for receive-only sockets (live feed, guardian), whose dev-mode
    clients never send anything — in dev mode only, silence for this long means the dev
    owner. In jwt mode silence is always a refusal.
    """
    dev_silence = config.AUTH_MODE == "dev" and silent_dev_after is not None
    timeout = silent_dev_after if dev_silence else config.WS_AUTH_TIMEOUT_S
    try:
        raw = await asyncio.wait_for(ws.receive_text(), timeout=timeout)
    except asyncio.TimeoutError:
        if dev_silence:
            return Principal(owner_id=config.DEV_OWNER_ID, via="dev"), None
        raise AuthError(f"no auth message within {timeout}s") from None
    try:
        msg = json.loads(raw)
    except (TypeError, ValueError):
        msg = None
    if isinstance(msg, dict) and msg.get("type") == "auth":
        return verify_token(str(msg.get("token") or "")), None
    if config.AUTH_MODE == "dev":
        return Principal(owner_id=config.DEV_OWNER_ID, via="dev"), raw
    raise AuthError("first message must be {\"type\": \"auth\", \"token\": ...}")


def log_mode() -> None:
    """One startup line saying how requests are authenticated."""
    if config.AUTH_MODE == "dev":
        log.warning(f"  AUTH_MODE=dev: requests without a token act as '{config.DEV_OWNER_ID}'. "
                    f"Never expose this server publicly in dev mode.")
    else:
        log.info(f"  AUTH_MODE=jwt: issuer {config.AUTH_ISSUER or '(NOT CONFIGURED — every request will be refused)'}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    log_mode()
    try:
        print(principal_from_header(None))
    except AuthError as e:
        print(f"[OK] refused without a token: {e}")
