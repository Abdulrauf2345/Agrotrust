"""Payment provider abstraction (spec sections 17, 60).

Real adapters (Paystack / Flutterwave) implement the same Protocol; they are intentionally not
shipped with credentials. ``MockPaymentProvider`` is refused in production by Settings.validate().
"""
from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Protocol

from ..shared.errors import ProviderError


@dataclass(frozen=True)
class ChargeInit:
    provider_reference: str
    checkout_url: str


@dataclass(frozen=True)
class ProviderCharge:
    status: str            # PENDING | SUCCEEDED | FAILED
    amount_minor: int
    currency: str


@dataclass(frozen=True)
class PayoutResult:
    status: str            # SUCCEEDED | FAILED | PENDING
    provider_reference: str | None = None
    failure_reason: str | None = None


class PaymentProvider(Protocol):
    name: str

    def initialize_charge(self, *, reference: str, amount_minor: int, currency: str, customer: str) -> ChargeInit: ...
    def verify_charge(self, reference: str) -> ProviderCharge: ...
    def send_payout(self, *, reference: str, amount_minor: int, currency: str, destination: dict) -> PayoutResult: ...
    def verify_webhook_signature(self, raw_body: bytes, signature: str) -> bool: ...


class MockPaymentProvider:
    name = "mock"

    def __init__(self, webhook_secret: str):
        self._secret = webhook_secret.encode()
        self.charges: dict[str, dict] = {}
        self.payouts: dict[str, dict] = {}
        self._fail_payouts = 0
        self._outage = 0

    # -- test controls
    def simulate_success(self, reference: str, amount_minor: int | None = None) -> None:
        c = self.charges[reference]
        c["status"] = "SUCCEEDED"
        if amount_minor is not None:
            c["amount_minor"] = amount_minor

    def simulate_failure(self, reference: str) -> None:
        self.charges[reference]["status"] = "FAILED"

    def fail_next_payouts(self, n: int = 1) -> None:
        self._fail_payouts = n

    def outage(self, n: int = 1) -> None:
        self._outage = n

    def sign(self, raw_body: bytes) -> str:
        return hmac.new(self._secret, raw_body, hashlib.sha512).hexdigest()

    def webhook(self, event: str, event_id: str, reference: str) -> tuple[bytes, str]:
        body = json.dumps({"event": event, "id": event_id, "data": {"reference": reference}}).encode()
        return body, self.sign(body)

    # -- Protocol
    def _check_outage(self):
        if self._outage > 0:
            self._outage -= 1
            raise ProviderError("provider unavailable")

    def initialize_charge(self, *, reference, amount_minor, currency, customer) -> ChargeInit:
        self._check_outage()
        self.charges.setdefault(reference, {"status": "PENDING", "amount_minor": amount_minor, "currency": currency})
        return ChargeInit(provider_reference=f"mock_{reference}", checkout_url=f"https://mock.pay/checkout/{reference}")

    def verify_charge(self, reference: str) -> ProviderCharge:
        self._check_outage()
        c = self.charges.get(reference)
        if not c:
            raise ProviderError("unknown reference")
        return ProviderCharge(c["status"], c["amount_minor"], c["currency"])

    def send_payout(self, *, reference, amount_minor, currency, destination) -> PayoutResult:
        self._check_outage()
        if reference in self.payouts:  # provider-side idempotency on our reference
            return self.payouts[reference]["result"]
        if self._fail_payouts > 0:
            self._fail_payouts -= 1
            res = PayoutResult("FAILED", None, "bank rejected")
        else:
            res = PayoutResult("SUCCEEDED", f"mockpo_{reference}")
        self.payouts[reference] = {"amount_minor": amount_minor, "result": res}
        return res

    def verify_webhook_signature(self, raw_body: bytes, signature: str) -> bool:
        return hmac.compare_digest(self.sign(raw_body), signature or "")
