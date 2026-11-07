"""Idempotency for payment-related commands (Idempotency-Key header).

Two execution modes:
* atomic=True (default): claim key + run the command + store the response in ONE
  transaction. Any failure rolls the claim back, so a retry re-executes cleanly, and
  a crash can never leave a financial effect without a stored response (or vice versa).
  Use for DB-only commands (release, refund, payout reservation, repayment).
* atomic=False: claim (committed) -> run outside a transaction -> store response.
  Use when the command calls an external provider, so no DB lock is held during the
  network call. A concurrent duplicate gets 409 IN_PROGRESS; a crashed request is
  retryable after ``in_progress_timeout_s``. The command itself must then be naturally
  idempotent (we send our own unique merchant ``reference`` to the provider).
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Callable

from ...db.database import Database
from ...shared.clock import Clock, from_iso, to_iso
from ...shared.errors import DuplicateIdempotencyKey, IdempotencyRequestInProgress, ValidationFailed

_KEY_RE = re.compile(r"^[A-Za-z0-9_\-:.]{8,128}$")


@dataclass
class IdempotentResult:
    status_code: int
    body: Any
    replayed: bool


def fingerprint(endpoint: str, payload: Any) -> str:
    canonical = json.dumps({"e": endpoint, "p": payload}, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


class IdempotencyService:
    def __init__(self, db: Database, clock: Clock, in_progress_timeout_s: int = 300):
        self.db, self.clock, self.timeout = db, clock, in_progress_timeout_s

    def run(self, *, scope: str, key: str | None, endpoint: str, payload: Any,
            fn: Callable[[], Any], atomic: bool = True, status_code: int = 200) -> IdempotentResult:
        if not key or not _KEY_RE.match(key):
            raise ValidationFailed("Idempotency-Key header is required (8-128 chars: A-Z a-z 0-9 _ - : .)")
        fp = fingerprint(endpoint, payload)
        return self._atomic(scope, key, endpoint, fp, fn, status_code) if atomic else \
            self._two_phase(scope, key, endpoint, fp, fn, status_code)

    # -- helpers ---------------------------------------------------------------
    def _claim(self, scope: str, key: str, endpoint: str, fp: str) -> IdempotentResult | None:
        """Insert IN_PROGRESS. Returns a replay result, or None if we own the key."""
        now = to_iso(self.clock.now())
        res = self.db.execute(
            "INSERT INTO idempotency_keys(scope, key, endpoint, request_hash, state, created_at, updated_at)"
            " VALUES (?,?,?,?,'IN_PROGRESS',?,?) ON CONFLICT DO NOTHING", (scope, key, endpoint, fp, now, now))
        if res.rowcount == 1:
            return None
        row = self.db.one("SELECT * FROM idempotency_keys WHERE scope=? AND key=?", (scope, key))
        if row["request_hash"] != fp:
            raise DuplicateIdempotencyKey("Idempotency-Key was already used with a different request",
                                          details={"key": key})
        if row["state"] == "COMPLETED":
            return IdempotentResult(row["status_code"], json.loads(row["response"]), True)
        age = self.clock.now() - from_iso(row["updated_at"])
        if age < timedelta(seconds=self.timeout):
            raise IdempotencyRequestInProgress("a request with this key is still being processed")
        self.db.execute("UPDATE idempotency_keys SET updated_at=? WHERE scope=? AND key=?", (now, scope, key))
        return None  # stale claim from a crashed request: take over

    def _complete(self, scope: str, key: str, status_code: int, body: Any) -> None:
        self.db.execute(
            "UPDATE idempotency_keys SET state='COMPLETED', status_code=?, response=?, updated_at=? WHERE scope=? AND key=?",
            (status_code, json.dumps(body, default=str), to_iso(self.clock.now()), scope, key))

    def _atomic(self, scope, key, endpoint, fp, fn, status_code) -> IdempotentResult:
        with self.db.transaction():
            replay = self._claim(scope, key, endpoint, fp)
            if replay:
                return replay
            body = fn()
            self._complete(scope, key, status_code, body)
            return IdempotentResult(status_code, body, False)

    def _two_phase(self, scope, key, endpoint, fp, fn, status_code) -> IdempotentResult:
        with self.db.transaction():
            replay = self._claim(scope, key, endpoint, fp)
        if replay:
            return replay
        try:
            body = fn()
        except BaseException:
            with self.db.transaction():  # release the key so the client can retry
                self.db.execute("DELETE FROM idempotency_keys WHERE scope=? AND key=? AND state='IN_PROGRESS'",
                                (scope, key))
            raise
        with self.db.transaction():
            self._complete(scope, key, status_code, body)
        return IdempotentResult(status_code, body, False)
