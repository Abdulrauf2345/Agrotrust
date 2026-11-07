"""Unified notification service. Enqueue is a cheap INSERT inside the caller's
transaction (never blocks payments on SMS); a worker dispatches with retries."""
from __future__ import annotations

import json
from datetime import timedelta
from string import Template
from typing import Iterable

from ...integrations.notification_providers import NotificationProvider, Recipient
from ...shared.clock import to_iso
from ...shared.context import Context
from ...shared.errors import NotFound
from ...shared.ids import new_id

# template -> (default channels, body, sensitive)
TEMPLATES: dict[str, tuple[tuple[str, ...], str, bool]] = {
    "otp": (("SMS",), "Your AgroTrust code is $code. It expires in $minutes minutes. Never share it.", True),
    "order_created": (("SMS", "IN_APP"), "New order $order_id for $qty $unit of $crop. Please confirm it.", False),
    "order_confirmed": (("IN_APP",), "Order $order_id was confirmed. Fund the escrow to proceed.", False),
    "order_funded": (("SMS", "IN_APP"), "Order $order_id is funded and secured in escrow. You can prepare the delivery.", False),
    "order_in_transit": (("IN_APP",), "Order $order_id is on its way.", False),
    "order_delivered": (("SMS", "IN_APP"), "Order $order_id was delivered. Please inspect and confirm.", False),
    "order_completed": (("IN_APP",), "Order $order_id is complete.", False),
    "order_cancelled": (("IN_APP",), "Order $order_id was cancelled.", False),
    "escrow_released": (("SMS", "IN_APP"), "NGN $amount from order $order_id was released to your wallet.", False),
    "escrow_refunded": (("SMS", "IN_APP"), "NGN $amount from order $order_id was refunded to your wallet.", False),
    "dispute_opened": (("SMS", "IN_APP"), "A dispute was opened on order $order_id.", False),
    "dispute_resolved": (("SMS", "IN_APP"), "The dispute on order $order_id was resolved.", False),
    "farm_verified": (("SMS", "IN_APP"), "Your farm $farm_name has been verified.", False),
    "farm_rejected": (("SMS", "IN_APP"), "Verification of farm $farm_name was rejected: $reason", False),
    "farm_assigned": (("IN_APP",), "You were assigned to verify farm $farm_name.", False),
    "loan_approved": (("SMS", "IN_APP"), "Your loan application was approved.", False),
    "loan_rejected": (("SMS", "IN_APP"), "Your loan application was not approved.", False),
    "loan_repayment_due": (("SMS", "IN_APP"), "Loan repayment of NGN $amount is due on $due_date.", False),
    "loan_overdue": (("SMS", "IN_APP"), "Your loan repayment of NGN $amount is overdue.", False),
    "insurance_payout": (("SMS", "IN_APP"), "Insurance payout of NGN $amount was credited for farm $farm_name.", False),
}
MAX_ATTEMPTS = 5


class NotificationService:
    def __init__(self, ctx: Context, providers: dict[str, NotificationProvider]):
        self.ctx, self.providers = ctx, providers

    @property
    def db(self):
        return self.ctx.db

    def enqueue(self, user_id: str, template: str, params: dict | None = None, *, channels: Iterable[str] | None = None,
                dedupe_key: str | None = None) -> list[str]:
        default_channels, _, _ = TEMPLATES[template]
        user = self.db.one("SELECT phone, email FROM users WHERE id=?", (user_id,))
        if not user:
            return []
        ids = []
        now = self.ctx.now_iso()
        for ch in (channels or default_channels):
            if ch == "EMAIL" and not user["email"]:
                continue
            nid = new_id()
            res = self.db.execute(
                "INSERT INTO notifications(id, user_id, channel, template, params, status, attempts, next_attempt_at, dedupe_key, created_at)"
                " VALUES (?,?,?,?,?,'PENDING',0,?,?,?) ON CONFLICT DO NOTHING",
                (nid, user_id, ch, template, json.dumps(params or {}, default=str), now,
                 f"{dedupe_key}:{ch}" if dedupe_key else None, now))
            if res.rowcount:
                ids.append(nid)
        return ids

    def render(self, template: str, params: dict) -> str:
        return Template(TEMPLATES[template][1]).safe_substitute({k: str(v) for k, v in params.items()})

    def dispatch_pending(self, limit: int = 100) -> dict[str, int]:
        stats = {"sent": 0, "retry": 0, "failed": 0}
        now_iso = self.ctx.now_iso()
        rows = self.db.all("SELECT id FROM notifications WHERE status='PENDING' AND next_attempt_at <= ? ORDER BY created_at LIMIT ?",
                           (now_iso, limit))
        for r in rows:
            lease = to_iso(self.ctx.clock.now() + timedelta(minutes=2))
            with self.db.transaction():  # claim: bump attempts + lease so no other worker sends it
                claimed = self.db.execute(
                    "UPDATE notifications SET attempts = attempts + 1, next_attempt_at = ? WHERE id=? AND status='PENDING' AND next_attempt_at <= ?",
                    (lease, r["id"], now_iso))
                if not claimed.rowcount:
                    continue
                n = self.db.one("SELECT n.*, u.phone, u.email FROM notifications n JOIN users u ON u.id = n.user_id WHERE n.id=?", (r["id"],))
            params = json.loads(n["params"])
            message = self.render(n["template"], params)
            sensitive = TEMPLATES[n["template"]][2]
            try:
                if n["channel"] != "IN_APP":
                    self.providers[n["channel"]].send(Recipient(n["user_id"], n["phone"], n["email"]), message)
            except Exception as exc:  # noqa: BLE001 - provider failures must never crash the worker
                with self.db.transaction():
                    if n["attempts"] >= MAX_ATTEMPTS:
                        self.db.execute("UPDATE notifications SET status='FAILED', last_error=? WHERE id=?", (str(exc)[:300], n["id"]))
                        stats["failed"] += 1
                    else:
                        backoff = timedelta(seconds=min(3600, 2 ** n["attempts"] * 15))
                        self.db.execute("UPDATE notifications SET last_error=?, next_attempt_at=? WHERE id=?",
                                        (str(exc)[:300], to_iso(self.ctx.clock.now() + backoff), n["id"]))
                        stats["retry"] += 1
                continue
            with self.db.transaction():
                keep = None if sensitive else message   # OTP text is never persisted
                self.db.execute("UPDATE notifications SET status='SENT', sent_at=?, rendered=?, params=? WHERE id=?",
                                (self.ctx.now_iso(), keep, "{}" if sensitive else n["params"], n["id"]))
            stats["sent"] += 1
        return stats

    # -- in-app inbox -----------------------------------------------------------
    def inbox(self, user_id: str, unread_only: bool = False, limit: int = 50) -> list[dict]:
        sql = "SELECT id, template, rendered, created_at, read_at FROM notifications WHERE user_id=? AND channel='IN_APP' AND status='SENT'"
        if unread_only:
            sql += " AND read_at IS NULL"
        return self.db.all(sql + " ORDER BY created_at DESC LIMIT ?", (user_id, min(limit, 200)))

    def mark_read(self, user_id: str, notification_id: str) -> None:
        with self.db.transaction():
            res = self.db.execute("UPDATE notifications SET read_at=? WHERE id=? AND user_id=? AND channel='IN_APP'",
                                  (self.ctx.now_iso(), notification_id, user_id))
            if not res.rowcount:
                raise NotFound("notification not found")
