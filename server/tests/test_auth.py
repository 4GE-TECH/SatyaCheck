"""Upgrade plan, Phase 1: every request is authenticated (server/auth.py).

A Supabase access token (JWT, asymmetric key from the project's JWKS) names the owner.
In dev mode a request without a token acts as DEV_OWNER_ID so the apps keep working
before they have sign-in; production refuses dev mode outright.

Keys are generated here and served through a stubbed JWKS client: no network, no project.
"""

from __future__ import annotations

import asyncio
import importlib
import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

import config

ISSUER = "https://example-ref.supabase.co/auth/v1"


@pytest.fixture(scope="module")
def keys():
    good = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return good, other


@pytest.fixture
def jwt_mode(keys, monkeypatch):
    from server import auth

    good, _ = keys
    monkeypatch.setattr(config, "AUTH_MODE", "jwt")
    monkeypatch.setattr(config, "AUTH_ISSUER", ISSUER)
    monkeypatch.setattr(config, "AUTH_JWKS_URL", "https://example-ref.supabase.co/auth/v1/.well-known/jwks.json")
    monkeypatch.setattr(config, "AUTH_AUDIENCE", "authenticated")

    class _Key:
        key = good.public_key()

    monkeypatch.setattr(auth, "_signing_key", lambda token: _Key.key)
    return good


def _token(private_key, sub="user-a", aud="authenticated", iss=ISSUER, exp_in=300, kid="k1", **extra):
    claims = {"sub": sub, "aud": aud, "iss": iss, "exp": int(time.time()) + exp_in,
              "iat": int(time.time()), "role": "authenticated", **extra}
    if sub is None:
        claims.pop("sub")
    return jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": kid})


# --- token verification --------------------------------------------------------------------

def test_a_valid_token_names_its_owner(jwt_mode):
    from server.auth import verify_token

    p = verify_token(_token(jwt_mode, sub="0b0e-uuid"))
    assert p.owner_id == "0b0e-uuid" and p.via == "jwt"


@pytest.mark.parametrize("change", [
    {"exp_in": -10},
    {"aud": "anon"},
    {"iss": "https://evil.example/auth/v1"},
    {"sub": None},
])
def test_bad_tokens_are_refused(jwt_mode, change):
    from server.auth import AuthError, verify_token

    with pytest.raises(AuthError):
        verify_token(_token(jwt_mode, **change))


def test_a_token_signed_by_another_key_is_refused(jwt_mode, keys):
    from server.auth import AuthError, verify_token

    with pytest.raises(AuthError):
        verify_token(_token(keys[1]))


def test_an_hs256_token_is_refused_even_with_the_right_claims(jwt_mode):
    """Algorithm confusion: only the asymmetric algorithms are accepted."""
    from server.auth import AuthError, verify_token

    forged = jwt.encode({"sub": "user-a", "aud": "authenticated", "iss": ISSUER,
                         "exp": int(time.time()) + 300}, "guessable-secret", algorithm="HS256")
    with pytest.raises(AuthError):
        verify_token(forged)


def test_unconfigured_auth_refuses_rather_than_accepting(monkeypatch):
    from server.auth import AuthError, verify_token

    monkeypatch.setattr(config, "AUTH_JWKS_URL", "")
    monkeypatch.setattr(config, "AUTH_ISSUER", "")
    with pytest.raises(AuthError):
        verify_token("anything")


# --- the request dependency -------------------------------------------------------------------

def _client():
    from server.main import app

    return TestClient(app)


def test_jwt_mode_refuses_a_request_without_a_token(jwt_mode):
    r = _client().get("/api/persons")
    assert r.status_code == 401
    assert r.headers.get("www-authenticate", "").lower().startswith("bearer")


def test_jwt_mode_refuses_a_malformed_header(jwt_mode):
    assert _client().get("/api/persons", headers={"Authorization": "Basic abc"}).status_code == 401


def test_dev_mode_acts_as_the_dev_owner(monkeypatch):
    from server.auth import principal_from_header

    monkeypatch.setattr(config, "AUTH_MODE", "dev")
    p = principal_from_header(None)
    assert p.owner_id == config.DEV_OWNER_ID and p.via == "dev"


def test_dev_mode_still_verifies_a_token_that_is_sent(jwt_mode, monkeypatch):
    """A bad token is an error in every mode, never a silent fall back to the dev owner."""
    from server.auth import AuthError, principal_from_header

    monkeypatch.setattr(config, "AUTH_MODE", "dev")
    assert principal_from_header(f"Bearer {_token(jwt_mode, sub='real')}").owner_id == "real"
    with pytest.raises(AuthError):
        principal_from_header("Bearer not-a-jwt")


def test_production_forces_jwt_mode(monkeypatch):
    monkeypatch.setenv("SATYACHECK_ENV", "production")
    monkeypatch.setenv("AUTH_MODE", "dev")
    try:
        assert importlib.reload(config).AUTH_MODE == "jwt"
    finally:
        monkeypatch.delenv("SATYACHECK_ENV")
        monkeypatch.delenv("AUTH_MODE")
        importlib.reload(config)


def test_health_stays_open(jwt_mode):
    assert _client().get("/api/health").status_code == 200


# --- WebSocket: first-message authentication ----------------------------------------------

class _FakeWS:
    def __init__(self, messages, delay=0.0):
        self.messages = list(messages)
        self.delay = delay

    async def receive_text(self):
        if self.delay:
            await asyncio.sleep(self.delay)
        return self.messages.pop(0)


def test_ws_first_message_auth(jwt_mode):
    from server.auth import authenticate_ws

    ws = _FakeWS([json.dumps({"type": "auth", "token": _token(jwt_mode, sub="user-b")})])
    principal, pending = asyncio.run(authenticate_ws(ws))
    assert principal.owner_id == "user-b" and pending is None


def test_ws_without_auth_in_jwt_mode_is_refused(jwt_mode):
    from server.auth import AuthError, authenticate_ws

    with pytest.raises(AuthError):
        asyncio.run(authenticate_ws(_FakeWS([json.dumps({"type": "audio_chunk"})])))


def test_ws_that_never_speaks_times_out(jwt_mode, monkeypatch):
    from server.auth import AuthError, authenticate_ws

    monkeypatch.setattr(config, "WS_AUTH_TIMEOUT_S", 0.05)
    with pytest.raises(AuthError):
        asyncio.run(authenticate_ws(_FakeWS(["{}"], delay=1.0)))


def test_ws_in_dev_mode_hands_back_the_first_message(monkeypatch):
    from server.auth import authenticate_ws

    monkeypatch.setattr(config, "AUTH_MODE", "dev")
    first = json.dumps({"type": "audio_chunk", "chunk_index": 0})
    principal, pending = asyncio.run(authenticate_ws(_FakeWS([first])))
    assert principal.owner_id == config.DEV_OWNER_ID and pending == first
