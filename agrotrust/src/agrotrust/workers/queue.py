"""Background job queue with retries and exponential backoff.

``DbJobQueue`` persists jobs in the primary database (simple, transactional with
business writes, ideal for the modular monolith). Production runs the same
handlers under ARQ/Redis (workers/arq_settings.py, ADR-004) — handlers are plain
functions of a JSON payload and must be idempotent.
"""
from __future__ import annotations

import json
import logging
from datetime import timedelta
from typing import Any, Callable

from ..db.database import Database
from ..shared.clock import Clock, to_iso
from ..shared.ids import new_id

log = logging.getLogger("agrotrust.jobs")
JobHandler = Callable[[dict], None]


class DbJobQueue:
    def __init__(self, db: Database, clock: Clock):
        self.db, self.clock = db, clock
        self.handlers: dict[str, JobHandler] = {}

    def register(self, name: str, fn: JobHandler) -> None:
        self.handlers[name] = fn

    def enqueue(self, name: str, payload: dict[str, Any] | None = None, *, delay_s: int = 0,
                dedupe_key: str | None = None, max_attempts: int = 5) -> str | None:
        now = self.clock.now()
        job_id = new_id()
        res = self.db.execute(
            "INSERT INTO jobs(id, name, payload, status, attempts, max_attempts, run_at, dedupe_key, created_at, updated_at)"
            " VALUES (?,?,?,'PENDING',0,?,?,?,?,?) ON CONFLICT DO NOTHING",
            (job_id, name, json.dumps(payload or {}), max_attempts, to_iso(now + timedelta(seconds=delay_s)),
             dedupe_key, to_iso(now), to_iso(now)))
        return job_id if res.rowcount else None

    def run_due(self, limit: int = 50) -> dict[str, int]:
        stats = {"done": 0, "retried": 0, "failed": 0}
        now = to_iso(self.clock.now())
        due = self.db.all("SELECT id FROM jobs WHERE status='PENDING' AND run_at <= ? ORDER BY run_at LIMIT ?", (now, limit))
        for row in due:
            with self.db.transaction():  # claim atomically: only one worker wins
                claimed = self.db.execute(
                    "UPDATE jobs SET status='RUNNING', attempts=attempts+1, updated_at=? WHERE id=? AND status='PENDING'",
                    (now, row["id"]))
                if claimed.rowcount == 0:
                    continue
                job = self.db.one("SELECT * FROM jobs WHERE id=?", (row["id"],))
            try:
                handler = self.handlers[job["name"]]
                with self.db.transaction():
                    handler(json.loads(job["payload"]))
                    self.db.execute("UPDATE jobs SET status='DONE', updated_at=?, last_error=NULL WHERE id=?", (now, job["id"]))
                stats["done"] += 1
            except Exception as exc:  # noqa: BLE001
                log.warning("job failed", extra={"job": job["name"], "error": str(exc)})
                with self.db.transaction():
                    if job["attempts"] >= job["max_attempts"]:
                        self.db.execute("UPDATE jobs SET status='FAILED', last_error=?, updated_at=? WHERE id=?",
                                        (str(exc)[:500], now, job["id"]))
                        stats["failed"] += 1
                    else:
                        backoff = min(3600, 2 ** job["attempts"] * 10)
                        self.db.execute(
                            "UPDATE jobs SET status='PENDING', last_error=?, run_at=?, updated_at=? WHERE id=?",
                            (str(exc)[:500], to_iso(self.clock.now() + timedelta(seconds=backoff)), now, job["id"]))
                        stats["retried"] += 1
        return stats

    def depth(self) -> int:
        return self.db.scalar("SELECT COUNT(*) FROM jobs WHERE status='PENDING'") or 0
