# ADR-001: Modular monolith, not microservices

**Status:** Accepted

## Context
The spec describes ~20 business domains (identity, marketplace, escrow, ledger, lending,
insurance, traceability, logistics, ...). A microservices split was considered.

## Decision
Ship as a single deployable modular monolith: one process, one database, with strict module
boundaries enforced by convention (`modules/<domain>/service.py`, each constructed with an
explicit `Context` and its own collaborators - no module reaches into another's private state).

## Rationale
- Escrow release, ledger posting, and order-state transitions must be atomic *together*. Across
  microservices that requires distributed sagas/2PC; in one process it's one SQL transaction.
- Team size and operational maturity for this project don't justify the complexity of service
  discovery, network retries, and distributed tracing that microservices demand.
- Module boundaries are kept clean enough that any module could be extracted into its own
  service later if its load profile genuinely diverges from the rest (e.g. ML scoring under
  heavy batch load).

## Consequences
- Single point of deployment/scaling for now; horizontal scaling means running more copies of
  the whole monolith behind a load balancer, not scaling hot modules independently.
- A future split would replace in-process method calls between modules with either synchronous
  HTTP/gRPC calls or, preferably, continue to route cross-module side effects through the
  existing outbox/event bus (ADR-005), which already models "this can be async and idempotent."
