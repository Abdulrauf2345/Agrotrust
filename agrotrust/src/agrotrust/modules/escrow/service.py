"""Escrow (spec section 14): buyer funds are locked at funding and released only by a
legitimate, state-checked path. All money movement is a balanced ledger entry.

Money never leaves escrow except via ``settle`` (release / partial / refund), which
* checks the escrow state and a version CAS,
* verifies seller+buyer amounts equal exactly what was held,
* posts ONE ledger entry keyed ``escrow_settle:<id>`` (a duplicate is impossible, even
  if the escrow row were somehow reset).
"""
from __future__ import annotations

from ...security.permissions import Principal
from ...shared.context import Context
from ...shared.errors import (ConcurrentModification, Conflict, NotFound, UnauthorizedResourceAccess,
                              ValidationFailed)
from ...shared.ids import new_id
from ...shared.money import Money
from ...shared.state_machine import StateMachine
from ..ledger.service import ESCROW_HOLD, FEE_REVENUE, C, D, LedgerService, wallet_code

ESCROW_SM = StateMachine("escrow", {
    "CREATED": ["FUNDED", "CANCELLED"],
    "FUNDED": ["IN_TRANSIT", "REFUNDED", "DISPUTED"],
    "IN_TRANSIT": ["DELIVERED", "REFUNDED", "DISPUTED"],
    "DELIVERED": ["INSPECTED", "RELEASED", "DISPUTED"],
    "INSPECTED": ["RELEASED", "DISPUTED"],
    "DISPUTED": ["RESOLVED"],
    "RESOLVED": ["RELEASED", "REFUNDED"],
})


class EscrowService:
    def __init__(self, ctx: Context, ledger: LedgerService):
        self.ctx, self.db, self.ledger = ctx, ctx.db, ledger

    def fee_for(self, seller_gross_minor: int) -> int:
        return Money(seller_gross_minor).bps(self.ctx.settings.platform_fee_bps).minor

    # ---------------------------------------------------------------- queries
    def get_for_order(self, principal: Principal, order_id: str) -> dict:
        e = self.db.one("SELECT * FROM escrows WHERE order_id=?", (order_id,))
        if not e or not (principal.user_id in (e["buyer_id"], e["seller_id"]) or principal.has("ledger:view")):
            raise NotFound("escrow not found")
        return e

    def _by_order(self, order_id: str) -> dict:
        e = self.db.one("SELECT * FROM escrows WHERE order_id=?", (order_id,))
        if not e:
            raise NotFound("escrow not found")
        return e

    # ------------------------------------------------------------- internals
    def fund(self, order: dict, actor_id: str) -> dict:
        """Move buyer wallet -> escrow. Fails with InsufficientFunds (ledger overdraft guard)."""
        if not self.db.in_transaction:
            raise RuntimeError("escrow.fund must run inside a transaction")
        if self.db.one("SELECT 1 FROM escrows WHERE order_id=?", (order["id"],)):
            raise Conflict("escrow already exists for this order")
        eid, now = new_id(), self.ctx.now_iso()
        self.ledger.ensure_wallet(order["buyer_id"])
        self.ledger.post(reference=f"escrow_fund:{eid}", entry_type="ESCROW_FUND",
                         description=f"Escrow funded for order {order['id']}",
                         lines=[D(wallet_code(order["buyer_id"]), order["total_minor"]),
                                C(ESCROW_HOLD, order["total_minor"])], actor_id=actor_id)
        self.db.execute(
            "INSERT INTO escrows(id,order_id,buyer_id,seller_id,amount_minor,currency,state,created_at,updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (eid, order["id"], order["buyer_id"], order["seller_id"], order["total_minor"], order["currency"],
             "FUNDED", now, now))
        self.ctx.log_transition("escrow", eid, None, "FUNDED", actor_id)
        self.ctx.publish("escrow.funded", "escrow", eid, {"order_id": order["id"]})
        return self.db.one("SELECT * FROM escrows WHERE id=?", (eid,))

    def _transition(self, e: dict, new_state: str, actor_id: str | None, reason: str | None = None,
                    extra_sql: str = "", extra_params: tuple = ()) -> None:
        ESCROW_SM.assert_can(e["state"], new_state)
        res = self.db.execute(
            f"UPDATE escrows SET state=?, version=version+1, updated_at=?{extra_sql} WHERE id=? AND version=?",
            (new_state, self.ctx.now_iso(), *extra_params, e["id"], e["version"]))
        if res.rowcount != 1:
            raise ConcurrentModification("escrow was modified concurrently; retry")
        self.ctx.log_transition("escrow", e["id"], e["state"], new_state, actor_id, reason)

    def advance(self, order_id: str, new_state: str, actor_id: str | None, reason: str | None = None) -> dict:
        """Non-monetary transitions (IN_TRANSIT / DELIVERED / INSPECTED / DISPUTED)."""
        if new_state in ("RELEASED", "REFUNDED", "RESOLVED"):
            raise ValidationFailed("monetary transitions go through settle()/resolve()")
        e = self._by_order(order_id)
        self._transition(e, new_state, actor_id, reason)
        return self._by_order(order_id)

    def mark_resolved(self, order_id: str, actor_id: str, split: tuple[int, int], reason: str) -> dict:
        """Admin dispute resolution decides the split; settlement follows in the same txn."""
        e = self._by_order(order_id)
        seller_gross, buyer_amt = split
        if seller_gross < 0 or buyer_amt < 0 or seller_gross + buyer_amt != e["amount_minor"]:
            raise ValidationFailed("split must be non-negative and equal the escrow amount exactly",
                                   details={"escrow_amount": e["amount_minor"]})
        self._transition(e, "RESOLVED", actor_id, reason,
                         ", pending_seller_minor=?, pending_fee_minor=?, pending_refund_minor=?",
                         (seller_gross, self.fee_for(seller_gross), buyer_amt))
        return self.settle(order_id, seller_gross, buyer_amt, actor_id, reason)

    def settle(self, order_id: str, seller_gross: int, buyer_refund: int, actor_id: str | None,
               reason: str | None = None) -> dict:
        """Release (seller_gross>0) or refund (seller_gross==0). One ledger entry, one CAS."""
        if not self.db.in_transaction:
            raise RuntimeError("escrow.settle must run inside a transaction")
        e = self._by_order(order_id)
        if e["state"] in ("RELEASED", "REFUNDED"):
            raise Conflict("escrow already settled")
        if seller_gross < 0 or buyer_refund < 0 or seller_gross + buyer_refund != e["amount_minor"]:
            raise ValidationFailed("settlement must equal the held amount exactly")
        fee = self.fee_for(seller_gross)
        net = seller_gross - fee
        lines = [D(ESCROW_HOLD, e["amount_minor"])]
        if net > 0:
            self.ledger.ensure_wallet(e["seller_id"])
            lines.append(C(wallet_code(e["seller_id"]), net))
        if fee > 0:
            lines.append(C(FEE_REVENUE, fee))
        if buyer_refund > 0:
            self.ledger.ensure_wallet(e["buyer_id"])
            lines.append(C(wallet_code(e["buyer_id"]), buyer_refund))
        target = "REFUNDED" if seller_gross == 0 else "RELEASED"
        self.ledger.post(reference=f"escrow_settle:{e['id']}", entry_type="ESCROW_SETTLE",
                         description=f"Escrow {target.lower()} for order {order_id}", lines=lines, actor_id=actor_id)
        self._transition(e, target, actor_id, reason,
                         ", seller_minor=?, fee_minor=?, refunded_minor=?", (net, fee, buyer_refund))
        self.ctx.publish(f"escrow.{target.lower()}", "escrow", e["id"],
                         {"order_id": order_id, "seller_minor": net, "fee_minor": fee, "refund_minor": buyer_refund})
        return self._by_order(order_id)

    def refund_full(self, order_id: str, actor_id: str | None, reason: str) -> dict:
        e = self._by_order(order_id)
        return self.settle(order_id, 0, e["amount_minor"], actor_id, reason)
