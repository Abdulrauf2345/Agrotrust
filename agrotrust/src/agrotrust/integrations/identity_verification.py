"""Identity-verification port and adapters (NIN/BVN etc.).

Business logic depends only on ``IdentityVerificationProvider``. A real adapter
(e.g. an NDPC-compliant licensed KYC vendor) implements ``verify`` and reads its
API key from the environment / secret manager - never from source code.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class VerificationResult:
    verified: bool
    reference: str
    reason: str | None = None


class IdentityVerificationProvider(Protocol):
    name: str

    def verify(self, id_type: str, id_number: str, full_name: str | None) -> VerificationResult: ...


class MockIdentityProvider:
    """Deterministic: fails any number ending in 0000. Never contacts a network."""

    name = "mock"

    def verify(self, id_type: str, id_number: str, full_name: str | None) -> VerificationResult:
        ref = "mock_" + hashlib.sha256(f"{id_type}:{id_number}".encode()).hexdigest()[:16]
        if id_number.endswith("0000"):
            return VerificationResult(False, ref, "no match")
        return VerificationResult(True, ref)
