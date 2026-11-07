"""Domain-specific exceptions.

Every business failure has its own type so callers can react precisely and the
API layer can map them to safe, consistent HTTP responses without leaking
internals.
"""
from __future__ import annotations

from typing import Any


class DomainError(Exception):
    code = "DOMAIN_ERROR"
    http_status = 400

    def __init__(self, message: str | None = None, *, details: dict[str, Any] | None = None):
        super().__init__(message or self.__class__.__name__)
        self.message = message or self.__class__.__name__
        self.details = details or {}


class ValidationFailed(DomainError):
    code = "VALIDATION_FAILED"
    http_status = 422


class NotFound(DomainError):
    code = "NOT_FOUND"
    http_status = 404


class Conflict(DomainError):
    code = "CONFLICT"
    http_status = 409


class AuthenticationFailed(DomainError):
    code = "AUTHENTICATION_FAILED"
    http_status = 401


class PermissionDenied(DomainError):
    code = "PERMISSION_DENIED"
    http_status = 403


class UnauthorizedResourceAccess(DomainError):
    """The caller has the permission in general but not over *this* resource."""

    code = "RESOURCE_ACCESS_DENIED"
    http_status = 403


class InvalidStateTransition(Conflict):
    code = "INVALID_STATE_TRANSITION"


class ConcurrentModification(Conflict):
    code = "CONCURRENT_MODIFICATION"


class DuplicateIdempotencyKey(DomainError):
    """Same Idempotency-Key reused with a different request."""

    code = "IDEMPOTENCY_KEY_REUSED"
    http_status = 422


class IdempotencyRequestInProgress(Conflict):
    code = "IDEMPOTENCY_REQUEST_IN_PROGRESS"


class InsufficientEscrowFunds(DomainError):
    code = "INSUFFICIENT_ESCROW_FUNDS"
    http_status = 422


class InsufficientFunds(DomainError):
    code = "INSUFFICIENT_FUNDS"
    http_status = 422


class UnbalancedJournal(DomainError):
    code = "UNBALANCED_JOURNAL"
    http_status = 500


class PaymentVerificationFailed(DomainError):
    code = "PAYMENT_VERIFICATION_FAILED"
    http_status = 422


class WebhookSignatureInvalid(DomainError):
    code = "WEBHOOK_SIGNATURE_INVALID"
    http_status = 401


class LoanNotEligible(DomainError):
    code = "LOAN_NOT_ELIGIBLE"
    http_status = 422


class RateLimited(DomainError):
    code = "RATE_LIMITED"
    http_status = 429


class ProviderError(DomainError):
    """An external provider failed (timeout, 5xx, bad response)."""

    code = "PROVIDER_ERROR"
    http_status = 502
