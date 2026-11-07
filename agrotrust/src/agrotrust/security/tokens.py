"""Access tokens (JWT, HS256) and opaque refresh tokens.

Design:
* Access tokens are short-lived and carry only ``sub`` — roles/permissions are
  re-read from the database on every request, so role removal, suspension and
  deletion take effect immediately (no stale-claims privilege retention).
* Refresh tokens are random opaque strings; only their SHA-256 is stored.
* ``alg`` is pinned and ``exp`` is checked against the injected clock.
"""
from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import timedelta

import jwt

from ..shared.clock import Clock
from ..shared.errors import AuthenticationFailed


class TokenService:
    ALGORITHM = "HS256"

    def __init__(self, secret: str, issuer: str, access_ttl_s: int, clock: Clock):
        self._secret, self._issuer, self._ttl, self._clock = secret, issuer, access_ttl_s, clock

    def create_access_token(self, user_id: str) -> tuple[str, int]:
        now = self._clock.now()
        claims = {
            "sub": user_id, "iss": self._issuer, "typ": "access", "jti": str(uuid.uuid4()),
            "iat": int(now.timestamp()), "exp": int((now + timedelta(seconds=self._ttl)).timestamp()),
        }
        return jwt.encode(claims, self._secret, algorithm=self.ALGORITHM), self._ttl

    def decode_access_token(self, token: str) -> dict:
        try:
            claims = jwt.decode(
                token, self._secret, algorithms=[self.ALGORITHM], issuer=self._issuer,
                options={"verify_exp": False, "verify_iat": False, "require": ["sub", "exp", "iss", "typ", "jti"]},
            )
        except jwt.PyJWTError as exc:
            raise AuthenticationFailed("invalid token") from exc
        if claims.get("typ") != "access":
            raise AuthenticationFailed("invalid token type")
        if claims["exp"] <= int(self._clock.now().timestamp()):
            raise AuthenticationFailed("token expired")
        return claims


def new_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
