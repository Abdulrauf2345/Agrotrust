"""PII masking and log/audit redaction (NDPA data-minimisation support)."""
from __future__ import annotations

import re
from enum import Enum
from typing import Any


class DataClassification(str, Enum):
    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    CONFIDENTIAL = "CONFIDENTIAL"
    HIGHLY_SENSITIVE = "HIGHLY_SENSITIVE"


_SENSITIVE_KEY = re.compile(r"(password|secret|token|otp|api[_-]?key|authorization|id_number|bvn|nin|hash|signature|card)", re.I)


def mask_phone(phone: str) -> str:
    return phone[:4] + "*" * max(len(phone) - 7, 0) + phone[-3:] if len(phone) > 7 else "***"


def mask_email(email: str) -> str:
    if "@" not in email:
        return "***"
    local, domain = email.split("@", 1)
    return local[:1] + "***@" + domain


def redact(value: Any) -> Any:
    """Recursively replace values of sensitive-looking keys."""
    if isinstance(value, dict):
        return {k: ("[REDACTED]" if _SENSITIVE_KEY.search(str(k)) else redact(v)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(v) for v in value]
    return value
