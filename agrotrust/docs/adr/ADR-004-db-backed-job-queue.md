# ADR-004: DB-backed job queue instead of ARQ/Redis

**Status:** Accepted (sandbox constraint, but defensible as a lightweight default)

## Context
The spec calls for ARQ + Redis for background jobs (notification dispatch, outbox relay,
overdue-loan scanning, insurance-window evaluation). No Redis server is available here.

## Decision
`workers/queue.py` implements `DbJobQueue`: jobs live in a `jobs` table, `run_due()` claims one
atomically via `UPDATE ... WHERE status='PENDING'` (so two worker processes racing on the same
row only one wins - proven by a real `threading.Thread` race test), runs the handler inside a
transaction (so a failing handler's partial writes roll back), and applies exponential backoff
before moving to a dead-letter `FAILED` state after `max_attempts`.

## Consequences
- No pub/sub, no priority queues, no distributed workers across machines - a single process
  (or a few processes racing safely on the same table) polls `run_due()`. This is a real
  limitation at high job volume.
- The *handler contract* (idempotent, runs in a transaction, retried with backoff) is identical
  to what ARQ + Redis would provide, so swapping the queue implementation later does not change
  any job handler's code - only `workers/queue.py`'s internals and how jobs get enqueued/polled.
