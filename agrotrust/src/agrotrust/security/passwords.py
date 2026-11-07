"""Password hashing with scrypt (stdlib). Production may swap in Argon2id
(``argon2-cffi``) behind the same two functions."""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

from ..shared.errors import ValidationFailed

_N, _R, _P = 2**14, 8, 1
_COMMON = {"password", "password123", "1234567890", "qwerty12345", "agrotrust123", "0123456789"}


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    return "scrypt${}${}${}${}${}".format(_N, _R, _P, base64.b64encode(salt).decode(), base64.b64encode(dk).decode())


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt_b64, dk_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        salt, expected = base64.b64decode(salt_b64), base64.b64decode(dk_b64)
        dk = hashlib.scrypt(password.encode(), salt=salt, n=int(n), r=int(r), p=int(p), dklen=len(expected))
    except Exception:
        return False
    return hmac.compare_digest(dk, expected)


def validate_password_strength(password: str) -> None:
    problems = []
    if len(password) < 10:
        problems.append("at least 10 characters")
    if not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
        problems.append("letters and digits")
    if password.lower() in _COMMON:
        problems.append("not a commonly used password")
    if problems:
        raise ValidationFailed("weak password: " + ", ".join(problems), details={"requirements": problems})
