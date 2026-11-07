from __future__ import annotations

import secrets
import uuid

_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I confusion


def new_id() -> str:
    return str(uuid.uuid4())


def lot_code(year: int) -> str:
    return f"LOT-{year}-" + "".join(secrets.choice(_ALPHABET) for _ in range(6))
