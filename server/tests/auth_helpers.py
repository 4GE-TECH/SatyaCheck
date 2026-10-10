"""Signed-in test accounts without a Supabase project.

`signed_in` switches the server to jwt mode with a locally generated RSA key standing in
for the project's JWKS, and returns `headers(owner)` -> {"Authorization": "Bearer ..."}
plus `token(owner)` for WebSocket first messages.

Import into a test module: `from server.tests.auth_helpers import signed_in`.
"""

from __future__ import annotations

import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

import config

ISSUER = "https://test-ref.supabase.co/auth/v1"
_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def make_token(owner: str, exp_in: int = 300) -> str:
    claims = {"sub": owner, "aud": "authenticated", "iss": ISSUER, "role": "authenticated",
              "iat": int(time.time()), "exp": int(time.time()) + exp_in}
    return jwt.encode(claims, _KEY, algorithm="RS256", headers={"kid": "test"})


@pytest.fixture
def signed_in(monkeypatch):
    from server import auth

    monkeypatch.setattr(config, "AUTH_MODE", "jwt")
    monkeypatch.setattr(config, "AUTH_ISSUER", ISSUER)
    monkeypatch.setattr(config, "AUTH_JWKS_URL", "https://test-ref.supabase.co/auth/v1/.well-known/jwks.json")
    monkeypatch.setattr(config, "AUTH_AUDIENCE", "authenticated")
    monkeypatch.setattr(auth, "_signing_key", lambda token: _KEY.public_key())

    class _Accounts:
        token = staticmethod(make_token)

        @staticmethod
        def headers(owner: str) -> dict:
            return {"Authorization": f"Bearer {make_token(owner)}"}

    return _Accounts
