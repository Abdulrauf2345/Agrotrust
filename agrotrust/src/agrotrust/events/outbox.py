"""Transactional outbox + in-process event bus.

Write side  : ``Outbox.publish`` inserts the event in the SAME transaction as the
              business change. Rollback => no event; commit => event guaranteed.
Publish side: ``OutboxPublisher.publish_pending`` (background worker) relays rows to a
              transport (in-process bus now; RabbitMQ/Kafka later) and marks them
              published only after a successful send => at-least-once delivery.
Consumer    : ``InProcessBus`` de-duplicates via ``processed_events`` inside the
              handler's own transaction => effectively-once *effects*.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Callable, Protocol

from ..db.database import Database
from ..shared.clock import Clock, to_iso
from ..shared.ids import new_id

log = logging.getLogger("agrotrust.events")


@dataclass(frozen=True)
class DomainEvent:
    event_id: str
    type: str
    aggregate_type: str
    aggregate_id: str
    payload: dict
    occurred_at: str


class Outbox:
    def __init__(self, db: Database, clock: Clock):
        self.db, self.clock = db, clock

    def publish(self, event_type: str, aggregate_type: str, aggregate_id: str, payload: dict | None = None) -> str:
        if not self.db.in_transaction:
            raise RuntimeError("outbox.publish must run inside the business transaction")
        event_id = new_id()
        self.db.execute(
            "INSERT INTO outbox(event_id, event_type, aggregate_type, aggregate_id, payload, created_at) VALUES (?,?,?,?,?,?)",
            (event_id, event_type, aggregate_type, aggregate_id, json.dumps(payload or {}, default=str),
             to_iso(self.clock.now())),
        )
        return event_id


class EventTransport(Protocol):
    def send(self, event: DomainEvent) -> None: ...


Handler = Callable[[DomainEvent], None]


class InProcessBus:
    def __init__(self, db: Database, clock: Clock):
        self.db, self.clock = db, clock
        self._handlers: dict[str, list[tuple[str, Handler]]] = {}

    def subscribe(self, event_type: str, handler_name: str, fn: Handler) -> None:
        self._handlers.setdefault(event_type, []).append((handler_name, fn))

    def send(self, event: DomainEvent) -> None:
        for name, fn in self._handlers.get(event.type, []) + self._handlers.get("*", []):
            with self.db.transaction():
                claimed = self.db.execute(
                    "INSERT INTO processed_events(handler, event_id, processed_at) VALUES (?,?,?) ON CONFLICT DO NOTHING",
                    (name, event.event_id, to_iso(self.clock.now())),
                )
                if claimed.rowcount == 0:
                    continue  # duplicate delivery: effect already applied
                fn(event)  # exception => rollback of claim + effects, publisher will retry


class OutboxPublisher:
    def __init__(self, db: Database, clock: Clock, transport: EventTransport, batch_size: int = 100,
                 max_attempts: int = 10):
        self.db, self.clock, self.transport = db, clock, transport
        self.batch_size, self.max_attempts = batch_size, max_attempts

    def publish_pending(self) -> dict[str, int]:
        rows = self.db.all(
            "SELECT * FROM outbox WHERE published_at IS NULL AND attempts < ? ORDER BY id LIMIT ?",
            (self.max_attempts, self.batch_size),
        )
        stats = {"published": 0, "failed": 0}
        blocked: set[tuple[str, str]] = set()  # keep per-aggregate ordering after a failure
        for r in rows:
            key = (r["aggregate_type"], r["aggregate_id"])
            if key in blocked:
                continue
            event = DomainEvent(r["event_id"], r["event_type"], r["aggregate_type"], r["aggregate_id"],
                                json.loads(r["payload"]), r["created_at"])
            try:
                self.transport.send(event)
            except Exception as exc:  # noqa: BLE001 - relay must survive any handler failure
                log.warning("outbox publish failed", extra={"event_id": r["event_id"], "error": str(exc)})
                with self.db.transaction():
                    self.db.execute("UPDATE outbox SET attempts = attempts + 1, last_error = ? WHERE id = ?",
                                    (str(exc)[:500], r["id"]))
                blocked.add(key)
                stats["failed"] += 1
                continue
            with self.db.transaction():
                self.db.execute("UPDATE outbox SET published_at = ?, attempts = attempts + 1 WHERE id = ?",
                                (to_iso(self.clock.now()), r["id"]))
            stats["published"] += 1
        return stats

    def pending_count(self) -> int:
        return self.db.scalar("SELECT COUNT(*) FROM outbox WHERE published_at IS NULL") or 0
