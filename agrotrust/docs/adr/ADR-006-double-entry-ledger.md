# ADR-006: A real double-entry ledger, not a balance column

**Status:** Accepted

## Context
Money moves between many parties (buyer wallets, escrow, platform fees, loan receivables,
insurance pool) and must never be created, destroyed, or double-counted - errors here are the
single most damaging bug class a platform like this can ship.

## Decision
`modules/ledger/service.py` implements real double-entry bookkeeping: every movement is a
balanced `journal_entries` + `journal_lines` pair (enforced by a DB `CHECK (debit=credit)` and
re-checked in application code before insert), accounts are typed (ASSET/LIABILITY/
REVENUE/EQUITY) with natural-balance-sign queries, `reference` is a unique idempotency key so
re-running the same business event (a webhook redelivery, a retried payout) never double-posts,
and `journal_entries`/`journal_lines` are immutable at the DB level (triggers) - corrections are
always compensating reversal entries (`reverses_entry_id`, unique - an entry can be reversed at
most once), never edits to history.

## Consequences
- Every other module (escrow, payments, lending, insurance) that moves money does so by calling
  `LedgerService.post()` with balanced lines - none of them touch a "balance" column directly,
  so there is exactly one place double-entry correctness is enforced.
- `trial_balance()` gives a standing invariant check (`total debits == total credits`) that can
  run as a scheduled health check in production; the test suite calls it after nearly every
  money-moving test as a cheap "did anything break" assertion.
- The overdraft guard (accounts with `allow_negative=0`) runs inside the same write-locked
  transaction as the posting, so a concurrency race can never overdraw an account - proven with
  a real multi-threaded test firing 8 concurrent withdrawals against a wallet that can only
  afford 3.
