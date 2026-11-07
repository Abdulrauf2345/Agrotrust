"""Shared application context passed to every module service (dependency injection)."""
from __future__ import annotations

from dataclasses import dataclass

from ..config.settings import Settings
from ..db.database import Database
from ..events.outbox import Outbox
from ..modules.audit.service import AuditService
from .clock import Clock, to_iso


@dataclass
class Context:
    db: Database
    clock: Clock
    settings: Settings
    audit: AuditService
    outbox: Outbox

    def now_iso(self) -> str:
        return to_iso(self.clock.now())

    def log_transition(self, entity_type: str, entity_id: str, from_state: str | None, to_state: str,
                       actor_id: str | None, reason: str | None = None) -> None:
        """Immutable state history + audit record. Must run in the caller's transaction."""
        self.db.execute(
            "INSERT INTO state_transitions(entity_type, entity_id, from_state, to_state, actor_id, reason, at)"
            " VALUES (?,?,?,?,?,?,?)", (entity_type, entity_id, from_state, to_state, actor_id, reason, self.now_iso()))
        self.audit.record(actor_id=actor_id, action=f"{entity_type.upper()}_{to_state}", resource_type=entity_type,
                          resource_id=entity_id, old={"state": from_state}, new={"state": to_state},
                          context={"reason": reason} if reason else None)

    def publish(self, event_type: str, aggregate_type: str, aggregate_id: str, payload: dict | None = None) -> None:
        self.outbox.publish(event_type, aggregate_type, aggregate_id, payload)
