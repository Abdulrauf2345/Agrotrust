# ADR-007: Mocked payment/KYC/SMS providers, never fake production credentials

**Status:** Accepted

## Context
The spec (section 60) is explicit: never use fake production credentials, and payment/KYC/SMS
providers (Paystack, Flutterwave, NIN/BVN verification, SMS gateways) all require real
credentials and network access that this sandbox has neither of, and that would be
inappropriate to fabricate even if it did.

## Decision
Every external integration is a `Protocol` (`PaymentProvider`, `IdentityVerificationProvider`,
`NotificationProvider`) with a `Mock*` implementation used everywhere in this build:
`MockPaymentProvider` simulates charges/payouts/webhooks with real HMAC-signed webhook bodies
so the signature-verification code path is genuinely exercised; `MockIdentityProvider`
deterministically fails IDs ending in `0000` so both the success and failure paths are testable;
`MockProvider` (notifications) records sent messages in memory and can simulate outages.
`config/settings.py` **refuses to start with `payment_provider=="mock"` in staging/production**
- the mock is structurally prevented from reaching a real deployment.

## Consequences
- Every money-moving and identity-verification code path is tested against realistic
  success/failure/malformed-input behavior without ever touching a real provider.
- Adding a real adapter (e.g. `integrations/paystack_adapter.py`) is additive: implement the
  same `Protocol`, wire real credentials via environment variables (never in code), and flip
  `settings.payment_provider`. No module above the integration layer needs to change.
