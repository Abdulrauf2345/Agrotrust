"""Tamper-evident audit log: WHO / WHAT / WHEN / CONTEXT / RESOURCE / OLD / NEW.

Rows are append-only (DB triggers reject UPDATE/DELETE) and hash-chained:
hash_n = SHA256(hash_{n-1} || canonical(row_n)). ``verify_chain`` detects any
out-of-band modification, insertion, or deletion of history.
Records are written inside the caller's transaction so an audit row exists iff
the audited change committed.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from ...db.database import Database
from ...security.pii import redact
from ...shared.clock import Clock, to_iso


def _canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


class AuditService:
    def __init__(self, db: Database, clock: Clock):
        self.db, self.clock = db, clock

    def record(self, *, actor_id: str | None, action: str, resource_type: str, resource_id: str | None = None,
               old: Any = None, new: Any = None, context: dict | None = None) -> int:
        if not self.db.in_transaction:
            raise RuntimeError("audit.record must run inside a transaction")
        prev = self.db.scalar("SELECT hash FROM audit_log ORDER BY id DESC LIMIT 1")
        row = {
            "at": to_iso(self.clock.now()), "actor_id": actor_id, "action": action,
            "resource_type": resource_type, "resource_id": resource_id,
            "old_state": _canonical(redact(old)) if old is not None else None,
            "new_state": _canonical(redact(new)) if new is not None else None,
            "context": _canonical(redact(context)) if context else None,
        }
        digest = hashlib.sha256(((prev or "") + _canonical(row)).encode()).hexdigest()
        res = self.db.execute(
            "INSERT INTO audit_log(at, actor_id, action, resource_type, resource_id, old_state, new_state, context, prev_hash, hash)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (row["at"], actor_id, action, resource_type, resource_id, row["old_state"], row["new_state"],
             row["context"], prev, digest),
        )
        return res.lastrowid or 0

    def verify_chain(self) -> tuple[bool, int | None]:
        prev = None
        for r in self.db.all("SELECT * FROM audit_log ORDER BY id"):
            body = {k: r[k] for k in ("at", "actor_id", "action", "resource_type", "resource_id",
                                      "old_state", "new_state", "context")}
            expected = hashlib.sha256(((prev or "") + _canonical(body)).encode()).hexdigest()
            if r["prev_hash"] != prev or r["hash"] != expected:
                return False, r["id"]
            prev = r["hash"]
        return True, None

    def query(self, *, actor_id: str | None = None, resource_type: str | None = None,
              resource_id: str | None = None, action: str | None = None, limit: int = 100,
              offset: int = 0) -> list[dict]:
        where, params = [], []
        for col, val in (("actor_id", actor_id), ("resource_type", resource_type),
                         ("resource_id", resource_id), ("action", action)):
            if val:
                where.append(f"{col} = ?")
                params.append(val)
        sql = "SELECT * FROM audit_log" + (" WHERE " + " AND ".join(where) if where else "")
        sql += " ORDER BY id DESC LIMIT ? OFFSET ?"
        return self.db.all(sql, (*params, min(limit, 500), offset))
