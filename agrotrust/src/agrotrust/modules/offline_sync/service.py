"""Offline sync (spec section 26): a generic idempotent-replay envelope around any command.

Each client operation is uniquely identified by (device_id, operation_id) - the PRIMARY KEY on
``sync_operations`` makes replay-safety a DB guarantee, not something every handler has to get
right on its own. Conflict resolution rule: a handler that hits a stale optimistic-lock version
(ConcurrentModification) is reported back as CONFLICT so the client re-fetches and retries with
fresh data - the server never blindly overwrites newer state, and never guesses which side wins.
"""
from __future__ import annotations

import json
from typing import Callable

from ...security.permissions import Principal
from ...shared.context import Context
from ...shared.errors import ConcurrentModification, DomainError, ValidationFailed

Handler = Callable[[Principal, dict], dict]


class OfflineSyncService:
    def __init__(self, ctx: Context):
        self.ctx, self.db = ctx, ctx.db
        self._handlers: dict[str, Handler] = {}

    def register(self, op_type: str, handler: Handler) -> None:
        self._handlers[op_type] = handler

    def apply(self, principal: Principal, *, device_id: str, operation_id: str, op_type: str, payload: dict,
             client_created_at: str) -> dict:
        if not device_id or not operation_id:
            raise ValidationFailed("device_id and operation_id are required")
        if op_type not in self._handlers:
            raise ValidationFailed(f"unknown op_type: {op_type}")
        existing = self.db.one("SELECT * FROM sync_operations WHERE device_id=? AND operation_id=?",
                               (device_id, operation_id))
        if existing:
            return {"status": existing["status"], "result": json.loads(existing["result"]), "replayed": True}
        handler = self._handlers[op_type]
        try:
            with self.db.transaction():
                result = handler(principal, payload)
                self.db.execute(
                    "INSERT INTO sync_operations(device_id,operation_id,user_id,op_type,status,result,"
                    "client_created_at,received_at) VALUES (?,?,?,?,'APPLIED',?,?,?)",
                    (device_id, operation_id, principal.user_id, op_type, json.dumps(result, default=str),
                     client_created_at, self.ctx.now_iso()))
                return {"status": "APPLIED", "result": result, "replayed": False}
        except ConcurrentModification as e:
            return self._record_terminal(device_id, operation_id, principal.user_id, op_type, "CONFLICT",
                                         str(e), client_created_at)
        except DomainError as e:
            # a well-understood business rejection (validation, permission, not-found, ...) - recorded so the
            # client sees a definitive answer instead of retrying the same bad operation forever.
            return self._record_terminal(device_id, operation_id, principal.user_id, op_type, "REJECTED",
                                         str(e), client_created_at)
        # unexpected exceptions propagate WITHOUT being recorded, so a retry (e.g. after a transient DB error)
        # can run cleanly - identical to the idempotency-key pattern used elsewhere in the platform.

    def _record_terminal(self, device_id, operation_id, user_id, op_type, status, message, client_created_at) -> dict:
        with self.db.transaction():
            self.db.execute(
                "INSERT INTO sync_operations(device_id,operation_id,user_id,op_type,status,result,client_created_at,"
                "received_at) VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(device_id,operation_id) DO NOTHING",
                (device_id, operation_id, user_id, op_type, status, json.dumps({"error": message}),
                 client_created_at, self.ctx.now_iso()))
        return {"status": status, "result": {"error": message}, "replayed": False}

    def apply_batch(self, principal: Principal, device_id: str, operations: list[dict]) -> list[dict]:
        """Each operation is applied independently; one failure never blocks the rest of the batch."""
        out = []
        for op in operations:
            try:
                res = self.apply(principal, device_id=device_id, operation_id=op["operation_id"],
                                 op_type=op["op_type"], payload=op.get("payload", {}),
                                 client_created_at=op["client_created_at"])
                out.append({"operation_id": op["operation_id"], **res})
            except Exception as e:
                out.append({"operation_id": op.get("operation_id"), "status": "ERROR", "error": str(e)})
        return out

    def pending_status(self, device_id: str, operation_ids: list[str]) -> dict[str, str]:
        """Lets a client ask 'what happened to these ops' after being offline for a while."""
        if not operation_ids:
            return {}
        placeholders = ",".join("?" for _ in operation_ids)
        rows = self.db.all(f"SELECT operation_id, status FROM sync_operations WHERE device_id=?"
                           f" AND operation_id IN ({placeholders})", [device_id, *operation_ids])
        return {r["operation_id"]: r["status"] for r in rows}
