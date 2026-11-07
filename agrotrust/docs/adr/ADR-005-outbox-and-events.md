# ADR-005: Transactional outbox + in-process event bus

**Status:** Accepted

## Context
Business actions (order funded, escrow released, loan disbursed) need to trigger side effects
(notifications, analytics, eventually a real message broker) without either (a) losing the
event if the process crashes between the DB write and the publish, or (b) publishing an event
for a transaction that later rolled back.

## Decision
`events/outbox.py` implements the transactional outbox pattern: `Outbox.publish()` inserts into
an `outbox` table **inside the same transaction** as the business write (enforced: it raises if
called outside a transaction). A separate relay (`OutboxPublisher.publish_pending()`) reads
un-published rows and hands them to an `EventTransport`. `InProcessBus` is the transport used in
this sandbox (no Kafka/SQS available); it dedupes consumers via a `processed_events` table so
redelivery is a safe no-op.

## Consequences
- Proven properties (see `tests/integration/test_core_infra.py`): a rolled-back business
  transaction never produces an event; a committed transaction's event survives even if the
  broker is briefly down (message sits in `outbox` until published); a handler that fails after
  partial writes rolls back entirely and is *not* marked processed, so retry is clean; two
  deliveries of the same event to the same handler run the handler exactly once.
- Moving to a real broker (Kafka, SQS, Redis Streams) means replacing `InProcessBus` with a
  transport that pushes to that broker - the outbox table and the "publish only after commit"
  guarantee do not change, because that guarantee is what makes at-least-once delivery safe
  regardless of which broker is on the other end.
