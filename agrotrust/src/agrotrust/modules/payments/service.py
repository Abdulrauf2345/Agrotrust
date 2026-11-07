"""Payments: charges, webhooks, payouts (spec sections 16-17).

Rules:
* Money is credited ONLY after the provider confirms it server-side (verify_charge), and the
  confirmed amount/currency must equal what we asked for. A webhook body is never trusted alone.
* Webhooks: signature checked on the RAW body, deduplicated on (provider, event_id), processed
  in one transaction with the ledger posting, so a replay can never credit twice.
* Deposits land in the payer's wallet (LIABILITY); escrow funding is a wallet -> escrow move.
* Payouts reserve funds first (wallet -> PAYOUT_PENDING), then call the provider, then settle
  or release the reservation.
"""
from __future__ import annotations

import json
from typing import Callable

from ...integrations.payment_providers import PaymentProvider
from ...security.permissions import Principal
from ...shared.context import Context
from ...shared.errors import (Conflict, NotFound, PaymentVerificationFailed, ProviderError, ValidationFailed,
                              WebhookSignatureInvalid)
from ...shared.ids import new_id
from ..ledger.service import BANK, PAYOUT_PENDING, C, D, LedgerService, wallet_code

SettleHook = Callable[[dict], None]


class PaymentService:
    def __init__(self, ctx: Context, ledger: LedgerService, provider: PaymentProvider):
        self.ctx, self.db, self.ledger, self.provider = ctx, ctx.db, ledger, provider
        self._settle_hooks: list[SettleHook] = []

    def on_charge_settled(self, hook: SettleHook) -> None:
        """Hooks run inside the settlement transaction (e.g. auto-fund an escrow)."""
        self._settle_hooks.append(hook)

    # ---------------------------------------------------------------- charge
    def create_charge(self, principal: Principal, *, amount_minor: int, order_id: str | None = None,
                      reference: str | None = None) -> dict:
        principal.require("payment:initiate")
        if not isinstance(amount_minor, int) or isinstance(amount_minor, bool) or amount_minor <= 0:
            raise ValidationFailed("amount_minor must be a positive integer")
        if order_id:
            order = self.db.one("SELECT buyer_id FROM orders WHERE id=?", (order_id,))
            if not order:
                raise NotFound("order not found")
            if order["buyer_id"] != principal.user_id:
                raise NotFound("order not found")   # do not reveal existence to non-parties
        reference = reference or f"chg_{new_id().replace('-', '')}"
        pid = new_id()
        with self.db.transaction():
            self.db.execute(
                "INSERT INTO payments(id,kind,order_id,user_id,provider,reference,amount_minor,currency,status,"
                "created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (pid, "CHARGE", order_id, principal.user_id, self.provider.name, reference, amount_minor, "NGN",
                 "PENDING", self.ctx.now_iso(), self.ctx.now_iso()))
        # network call OUTSIDE the transaction; our unique reference makes retries safe
        init = self.provider.initialize_charge(reference=reference, amount_minor=amount_minor, currency="NGN",
                                               customer=principal.user_id)
        with self.db.transaction():
            self.db.execute("UPDATE payments SET provider_reference=?, checkout_url=?, updated_at=? WHERE id=?",
                            (init.provider_reference, init.checkout_url, self.ctx.now_iso(), pid))
        return self.db.one("SELECT * FROM payments WHERE id=?", (pid,))

    def get(self, principal: Principal, payment_id: str) -> dict:
        p = self.db.one("SELECT * FROM payments WHERE id=?", (payment_id,))
        if not p or (p["user_id"] != principal.user_id and not principal.is_admin):
            raise NotFound("payment not found")
        return p

    # --------------------------------------------------------------- webhook
    def handle_webhook(self, raw_body: bytes, signature: str) -> dict:
        if not self.provider.verify_webhook_signature(raw_body, signature):
            raise WebhookSignatureInvalid("invalid webhook signature")
        try:
            evt = json.loads(raw_body)
            event_id, event_type = str(evt["id"]), str(evt["event"])
            reference = evt["data"]["reference"]
        except (ValueError, KeyError, TypeError):
            raise ValidationFailed("malformed webhook payload")
        prior = self.db.one("SELECT status FROM webhook_events WHERE provider=? AND event_id=?",
                            (self.provider.name, event_id))
        if prior and prior["status"] in ("PROCESSED", "IGNORED"):
            return {"status": "duplicate"}
        verified = None
        if event_type == "charge.success":
            verified = self.provider.verify_charge(reference)   # outside txn
        with self.db.transaction():
            row = self.db.one("SELECT * FROM webhook_events WHERE provider=? AND event_id=?",
                              (self.provider.name, event_id))
            if row and row["status"] in ("PROCESSED", "IGNORED"):
                return {"status": "duplicate"}
            if not row:
                self.db.execute(
                    "INSERT INTO webhook_events(id,provider,event_id,event_type,payload,signature_valid,status,"
                    "received_at) VALUES (?,?,?,?,?,1,'RECEIVED',?)",
                    (new_id(), self.provider.name, event_id, event_type, raw_body.decode(), self.ctx.now_iso()))
            self.db.execute("UPDATE webhook_events SET attempts=attempts+1 WHERE provider=? AND event_id=?",
                            (self.provider.name, event_id))
            if event_type == "charge.success":
                result = self._settle_charge(reference, verified)
                status = "PROCESSED"
            else:
                result, status = {"status": "ignored"}, "IGNORED"
            self.db.execute("UPDATE webhook_events SET status=?, processed_at=? WHERE provider=? AND event_id=?",
                            (status, self.ctx.now_iso(), self.provider.name, event_id))
            return result

    def reconcile_charge(self, reference: str) -> dict:
        """Poll the provider (for missed webhooks). Same settlement path, so also idempotent."""
        verified = self.provider.verify_charge(reference)
        with self.db.transaction():
            return self._settle_charge(reference, verified)

    def _settle_charge(self, reference: str, verified) -> dict:
        pay = self.db.one("SELECT * FROM payments WHERE reference=? AND kind='CHARGE'", (reference,))
        if not pay:
            return {"status": "unknown_reference"}
        if pay["status"] != "PENDING":
            return {"status": "already_" + pay["status"].lower()}
        if verified.status == "PENDING":
            return {"status": "still_pending"}
        if verified.status == "FAILED":
            self.db.execute("UPDATE payments SET status='FAILED', failure_reason='provider declined', updated_at=?"
                            " WHERE id=?", (self.ctx.now_iso(), pay["id"]))
            return {"status": "failed"}
        if verified.amount_minor != pay["amount_minor"] or verified.currency != pay["currency"]:
            self.db.execute("UPDATE payments SET status='FAILED', failure_reason='amount mismatch', updated_at=?"
                            " WHERE id=?", (self.ctx.now_iso(), pay["id"]))
            self.ctx.audit.record(actor_id=None, action="PAYMENT_AMOUNT_MISMATCH", resource_type="payment",
                                  resource_id=pay["id"], context={"expected": pay["amount_minor"],
                                                                  "got": verified.amount_minor})
            self.ctx.publish("payment.amount_mismatch", "payment", pay["id"],
                             {"expected": pay["amount_minor"], "got": verified.amount_minor})   # ops alert
            return {"status": "amount_mismatch", "payment_id": pay["id"]}   # committed: FAILED + audit, no credit
        self.ledger.ensure_wallet(pay["user_id"])
        self.ledger.post(reference=f"deposit:{pay['id']}", entry_type="DEPOSIT",
                         description=f"Deposit {reference}",
                         lines=[D(BANK, pay["amount_minor"]), C(wallet_code(pay["user_id"]), pay["amount_minor"])])
        self.db.execute("UPDATE payments SET status='SUCCEEDED', updated_at=? WHERE id=?", (self.ctx.now_iso(), pay["id"]))
        self.ctx.audit.record(actor_id=None, action="PAYMENT_SUCCEEDED", resource_type="payment", resource_id=pay["id"],
                              new={"amount_minor": pay["amount_minor"]})
        self.ctx.publish("payment.succeeded", "payment", pay["id"], {"order_id": pay["order_id"]})
        pay = self.db.one("SELECT * FROM payments WHERE id=?", (pay["id"],))
        for hook in self._settle_hooks:
            hook(pay)
        return {"status": "succeeded", "payment_id": pay["id"]}

    # ---------------------------------------------------------------- payout
    def request_payout(self, principal: Principal, *, amount_minor: int, destination: dict,
                       client_ref: str) -> dict:
        principal.require("payout:request")
        if not isinstance(amount_minor, int) or isinstance(amount_minor, bool) or amount_minor <= 0:
            raise ValidationFailed("amount_minor must be a positive integer")
        if not destination.get("account_number") or not destination.get("bank_code"):
            raise ValidationFailed("destination needs account_number and bank_code")
        reference = f"po_{principal.user_id}_{client_ref}"
        pid = new_id()
        with self.db.transaction():
            existing = self.db.one("SELECT * FROM payments WHERE reference=?", (reference,))
            if existing:
                return existing
            self.ledger.ensure_wallet(principal.user_id)
            self.ledger.post(reference=f"payout_reserve:{pid}", entry_type="PAYOUT_RESERVE",
                             description="Withdrawal reserved",
                             lines=[D(wallet_code(principal.user_id), amount_minor), C(PAYOUT_PENDING, amount_minor)],
                             actor_id=principal.user_id)
            self.db.execute(
                "INSERT INTO payments(id,kind,user_id,provider,reference,amount_minor,currency,status,meta,created_at,"
                "updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (pid, "PAYOUT", principal.user_id, self.provider.name, reference, amount_minor, "NGN", "PENDING",
                 json.dumps({"bank_code": destination["bank_code"], "last4": str(destination["account_number"])[-4:]}),
                 self.ctx.now_iso(), self.ctx.now_iso()))
        return self._execute_payout(pid, destination)

    def _execute_payout(self, pid: str, destination: dict) -> dict:
        pay = self.db.one("SELECT * FROM payments WHERE id=?", (pid,))
        try:
            res = self.provider.send_payout(reference=pay["reference"], amount_minor=pay["amount_minor"],
                                            currency=pay["currency"], destination=destination)
        except ProviderError:
            return pay   # stays PENDING; retry_payout / reconciliation finishes it. Funds stay reserved.
        with self.db.transaction():
            cur = self.db.one("SELECT status FROM payments WHERE id=?", (pid,))
            if cur["status"] != "PENDING":
                return self.db.one("SELECT * FROM payments WHERE id=?", (pid,))
            if res.status == "SUCCEEDED":
                self.ledger.post(reference=f"payout_settle:{pid}", entry_type="PAYOUT_SETTLE", description="Payout sent",
                                 lines=[D(PAYOUT_PENDING, pay["amount_minor"]), C(BANK, pay["amount_minor"])])
                self.db.execute("UPDATE payments SET status='SUCCEEDED', provider_reference=?, updated_at=? WHERE id=?",
                                (res.provider_reference, self.ctx.now_iso(), pid))
            elif res.status == "FAILED":
                self.ledger.post(reference=f"payout_release:{pid}", entry_type="PAYOUT_RELEASE",
                                 description="Payout failed; funds returned",
                                 lines=[D(PAYOUT_PENDING, pay["amount_minor"]),
                                        C(wallet_code(pay["user_id"]), pay["amount_minor"])])
                self.db.execute("UPDATE payments SET status='FAILED', failure_reason=?, updated_at=? WHERE id=?",
                                (res.failure_reason, self.ctx.now_iso(), pid))
        return self.db.one("SELECT * FROM payments WHERE id=?", (pid,))

    def retry_payout(self, payment_id: str, destination: dict) -> dict:
        """Ops/worker retry for a payout stuck PENDING (provider reference makes it safe)."""
        pay = self.db.one("SELECT * FROM payments WHERE id=? AND kind='PAYOUT'", (payment_id,))
        if not pay:
            raise NotFound("payout not found")
        if pay["status"] != "PENDING":
            raise Conflict("payout is not pending")
        return self._execute_payout(payment_id, destination)
