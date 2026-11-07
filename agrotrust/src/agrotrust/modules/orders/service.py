"""Orders: lifecycle, quantity reservation, escrow coupling, disputes (spec sections 12-14)."""
from __future__ import annotations

from ...security.permissions import Principal
from ...shared.context import Context
from ...shared.errors import (ConcurrentModification, Conflict, NotFound, PermissionDenied, ValidationFailed)
from ...shared.ids import new_id
from ...shared.money import line_total_minor, to_milli
from ...shared.state_machine import StateMachine
from ..escrow.service import EscrowService
from ..marketplace.service import MarketplaceService
from ..payments.idempotency import IdempotencyService

ORDER_SM = StateMachine("order", {
    "CREATED": ["CONFIRMED", "CANCELLED"],
    "CONFIRMED": ["FUNDED", "CANCELLED"],
    "FUNDED": ["PREPARING", "CANCELLED"],
    "PREPARING": ["IN_TRANSIT", "CANCELLED"],
    "IN_TRANSIT": ["DELIVERED", "DELIVERY_FAILED"],
    "DELIVERY_FAILED": ["IN_TRANSIT", "CANCELLED"],
    "DELIVERED": ["INSPECTED", "DISPUTED", "COMPLETED"],
    "INSPECTED": ["COMPLETED", "DISPUTED"],
    "DISPUTED": ["COMPLETED"],
})
_ESCROW_HELD_STATES = {"FUNDED", "PREPARING", "IN_TRANSIT", "DELIVERY_FAILED"}


class OrderService:
    def __init__(self, ctx: Context, market: MarketplaceService, escrow: EscrowService, idem: IdempotencyService):
        self.ctx, self.db, self.market, self.escrow, self.idem = ctx, ctx.db, market, escrow, idem

    # ---------------------------------------------------------------- helpers
    def _load(self, order_id: str) -> dict:
        o = self.db.one("SELECT * FROM orders WHERE id=?", (order_id,))
        if not o:
            raise NotFound("order not found")
        return o

    def get(self, principal: Principal, order_id: str) -> dict:
        o = self.db.one("SELECT * FROM orders WHERE id=?", (order_id,))
        if not o or not (principal.user_id in (o["buyer_id"], o["seller_id"]) or principal.has("order:read_any")):
            raise NotFound("order not found")     # never reveal existence to outsiders
        return o

    def list_mine(self, principal: Principal, role: str = "buyer", state: str | None = None) -> list[dict]:
        col = "buyer_id" if role == "buyer" else "seller_id"
        sql, params = f"SELECT * FROM orders WHERE {col}=?", [principal.user_id]
        if state:
            sql += " AND state=?"
            params.append(state)
        return self.db.all(sql + " ORDER BY created_at DESC LIMIT 200", params)

    def _move(self, o: dict, new_state: str, actor_id: str, reason: str | None = None, sets: str = "",
              params: tuple = ()) -> dict:
        ORDER_SM.assert_can(o["state"], new_state)
        res = self.db.execute(
            f"UPDATE orders SET state=?, version=version+1, updated_at=?{sets} WHERE id=? AND version=?",
            (new_state, self.ctx.now_iso(), *params, o["id"], o["version"]))
        if res.rowcount != 1:
            raise ConcurrentModification("order modified concurrently; retry")
        self.ctx.log_transition("order", o["id"], o["state"], new_state, actor_id, reason)
        self.ctx.publish(f"order.{new_state.lower()}", "order", o["id"], {})
        return self._load(o["id"])

    def _as_seller(self, p: Principal, o: dict) -> None:
        if p.user_id != o["seller_id"]:
            raise NotFound("order not found") if not p.has("order:read_any") else PermissionDenied("sellers only")

    def _as_buyer(self, p: Principal, o: dict) -> None:
        if p.user_id != o["buyer_id"]:
            raise NotFound("order not found") if not p.has("order:read_any") else PermissionDenied("buyers only")

    # -------------------------------------------------------------- lifecycle
    def create(self, principal: Principal, *, listing_id: str, quantity, delivery_address: str = "") -> dict:
        principal.require("order:create")
        qty = to_milli(quantity)
        if qty <= 0:
            raise ValidationFailed("quantity must be positive")
        with self.db.transaction():
            listing = self.db.one("SELECT * FROM listings WHERE id=?", (listing_id,))
            if not listing:
                raise NotFound("listing not found")
            if listing["seller_id"] == principal.user_id:
                raise Conflict("you cannot buy your own listing")
            total = line_total_minor(listing["price_minor"], qty)
            if total <= 0:
                raise ValidationFailed("order total rounds to zero")
            self.market.reserve(listing_id, qty)      # atomic; raises Conflict if insufficient
            oid, now = new_id(), self.ctx.now_iso()
            self.db.execute(
                "INSERT INTO orders(id,buyer_id,seller_id,listing_id,crop_id,qty_milli,unit,unit_price_minor,total_minor,"
                "currency,state,delivery_address,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (oid, principal.user_id, listing["seller_id"], listing_id, listing["crop_id"], qty, listing["unit"],
                 listing["price_minor"], total, listing["currency"], "CREATED", delivery_address[:500], now, now))
            self.ctx.log_transition("order", oid, None, "CREATED", principal.user_id)
            self.ctx.publish("order.created", "order", oid, {"listing_id": listing_id})
            return self._load(oid)

    def confirm(self, principal: Principal, order_id: str) -> dict:
        principal.require("order:approve")
        with self.db.transaction():
            o = self._load(order_id)
            self._as_seller(principal, o)
            return self._move(o, "CONFIRMED", principal.user_id)

    def fund(self, principal: Principal, order_id: str) -> dict:
        principal.require("order:create")
        with self.db.transaction():
            o = self._load(order_id)
            self._as_buyer(principal, o)
            ORDER_SM.assert_can(o["state"], "FUNDED")
            self.escrow.fund(o, principal.user_id)          # raises InsufficientFunds -> whole txn rolls back
            return self._move(o, "FUNDED", principal.user_id)

    def prepare(self, principal: Principal, order_id: str) -> dict:
        principal.require("order:approve")
        with self.db.transaction():
            o = self._load(order_id)
            self._as_seller(principal, o)
            return self._move(o, "PREPARING", principal.user_id)

    def dispatch(self, principal: Principal, order_id: str) -> dict:
        principal.require("order:approve")
        with self.db.transaction():
            o = self._load(order_id)
            self._as_seller(principal, o)
            was_failed = o["state"] == "DELIVERY_FAILED"
            new = self._move(o, "IN_TRANSIT", principal.user_id)
            if not was_failed:
                self.escrow.advance(order_id, "IN_TRANSIT", principal.user_id)
            return new

    def delivery_failed(self, principal: Principal, order_id: str, reason: str) -> dict:
        principal.require("order:approve")
        with self.db.transaction():
            o = self._load(order_id)
            self._as_seller(principal, o)
            return self._move(o, "DELIVERY_FAILED", principal.user_id, reason)

    def mark_delivered(self, principal: Principal, order_id: str, delivered_quantity) -> dict:
        principal.require("order:approve")
        dq = to_milli(delivered_quantity)
        with self.db.transaction():
            o = self._load(order_id)
            self._as_seller(principal, o)
            if not 0 < dq <= o["qty_milli"]:
                raise ValidationFailed("delivered quantity must be >0 and not exceed the ordered quantity")
            new = self._move(o, "DELIVERED", principal.user_id, sets=", delivered_qty_milli=?", params=(dq,))
            self.escrow.advance(order_id, "DELIVERED", principal.user_id)
            return new

    def inspect(self, principal: Principal, order_id: str, accepted_quantity, quality_result: str = "") -> dict:
        principal.require("order:create")
        aq = to_milli(accepted_quantity)
        with self.db.transaction():
            o = self._load(order_id)
            self._as_buyer(principal, o)
            if not 0 <= aq <= (o["delivered_qty_milli"] or 0):
                raise ValidationFailed("accepted quantity cannot exceed delivered quantity")
            new = self._move(o, "INSPECTED", principal.user_id,
                             sets=", accepted_qty_milli=?, quality_result=?", params=(aq, quality_result[:500]))
            self.escrow.advance(order_id, "INSPECTED", principal.user_id)
            return new

    def release(self, principal: Principal, order_id: str, idempotency_key: str) -> dict:
        """Buyer releases escrow after inspection. Idempotent, atomic, exactly-once."""
        principal.require("escrow:release_own")

        def cmd():
            o = self._load(order_id)
            self._as_buyer(principal, o)
            if o["state"] != "INSPECTED":
                raise Conflict("order must be INSPECTED before release", details={"state": o["state"]})
            gross = line_total_minor(o["unit_price_minor"], o["accepted_qty_milli"])
            gross = min(gross, o["total_minor"])
            self.escrow.settle(order_id, gross, o["total_minor"] - gross, principal.user_id, "buyer release")
            self._move(o, "COMPLETED", principal.user_id)
            return {"order_id": order_id, "state": "COMPLETED"}
        # partial acceptance: any un-accepted goods are refunded, remaining stock returns to the listing
        res = self.idem.run(scope=principal.user_id, key=idempotency_key, endpoint=f"POST /orders/{order_id}/release",
                            payload={"order_id": order_id}, fn=cmd)
        return {**res.body, "replayed": res.replayed}

    def cancel(self, principal: Principal, order_id: str, reason: str) -> dict:
        if not reason or not reason.strip():
            raise ValidationFailed("a cancellation reason is required")
        with self.db.transaction():
            o = self._load(order_id)
            if principal.user_id not in (o["buyer_id"], o["seller_id"]):
                raise NotFound("order not found")
            ORDER_SM.assert_can(o["state"], "CANCELLED")
            if o["state"] == "PREPARING" and principal.user_id == o["buyer_id"]:
                raise PermissionDenied("buyer cannot cancel once the seller is preparing; open a dispute if needed")
            if o["state"] in _ESCROW_HELD_STATES and self.db.one("SELECT 1 FROM escrows WHERE order_id=?", (order_id,)):
                self.escrow.refund_full(order_id, principal.user_id, f"order cancelled: {reason}")
            self.market.release(o["listing_id"], o["qty_milli"])
            return self._move(o, "CANCELLED", principal.user_id, reason, sets=", cancel_reason=?", params=(reason[:500],))

    # --------------------------------------------------------------- disputes
    def open_dispute(self, principal: Principal, order_id: str, reason: str) -> dict:
        principal.require("dispute:open")
        if not reason or len(reason.strip()) < 10:
            raise ValidationFailed("please describe the problem (at least 10 characters)")
        with self.db.transaction():
            o = self._load(order_id)
            if principal.user_id not in (o["buyer_id"], o["seller_id"]):
                raise NotFound("order not found")
            ORDER_SM.assert_can(o["state"], "DISPUTED")
            e = self.db.one("SELECT id FROM escrows WHERE order_id=?", (order_id,))
            did = new_id()
            try:
                self.db.execute("INSERT INTO disputes(id,order_id,escrow_id,opened_by,reason,state,opened_at)"
                                " VALUES (?,?,?,?,?,'OPEN',?)",
                                (did, order_id, e["id"], principal.user_id, reason.strip()[:2000], self.ctx.now_iso()))
            except Exception as ex:
                if "UNIQUE" in str(ex).upper():
                    raise Conflict("an open dispute already exists for this order") from ex
                raise
            self._move(o, "DISPUTED", principal.user_id, reason)
            self.escrow.advance(order_id, "DISPUTED", principal.user_id, reason)
            self.ctx.publish("dispute.opened", "dispute", did, {"order_id": order_id})
            return self.db.one("SELECT * FROM disputes WHERE id=?", (did,))

    def resolve_dispute(self, principal: Principal, dispute_id: str, *, seller_amount_minor: int,
                        buyer_amount_minor: int, resolution: str) -> dict:
        principal.require("dispute:resolve")
        if not resolution or len(resolution.strip()) < 5:
            raise ValidationFailed("a written resolution is required")
        for v in (seller_amount_minor, buyer_amount_minor):
            if not isinstance(v, int) or isinstance(v, bool):
                raise ValidationFailed("amounts must be integer minor units")
        with self.db.transaction():
            d = self.db.one("SELECT * FROM disputes WHERE id=?", (dispute_id,))
            if not d:
                raise NotFound("dispute not found")
            if d["state"] != "OPEN":
                raise Conflict("dispute already resolved")
            o = self._load(d["order_id"])
            self.escrow.mark_resolved(o["id"], principal.user_id, (seller_amount_minor, buyer_amount_minor), resolution)
            self.db.execute("UPDATE disputes SET state='RESOLVED', resolution=?, seller_amount_minor=?,"
                            " buyer_amount_minor=?, resolved_by=?, resolved_at=? WHERE id=?",
                            (resolution.strip()[:2000], seller_amount_minor, buyer_amount_minor, principal.user_id,
                             self.ctx.now_iso(), dispute_id))
            self._move(o, "COMPLETED", principal.user_id, f"dispute resolved: {resolution}")
            return self.db.one("SELECT * FROM disputes WHERE id=?", (dispute_id,))

    def list_disputes(self, principal: Principal) -> list[dict]:
        """A party to the order sees their own disputes; an admin (who holds
        dispute:resolve) sees every open and resolved dispute on the
        platform. Added for the frontend's admin dispute queue - the
        original route set could only open or resolve a dispute by id, with
        no way to list them."""
        if principal.has("dispute:resolve") or principal.is_admin:
            return self.db.all("SELECT * FROM disputes ORDER BY opened_at DESC")
        return self.db.all(
            "SELECT d.* FROM disputes d JOIN orders o ON o.id = d.order_id"
            " WHERE o.buyer_id=? OR o.seller_id=? ORDER BY d.opened_at DESC",
            (principal.user_id, principal.user_id),
        )

    def get_dispute(self, principal: Principal, dispute_id: str) -> dict:
        d = self.db.one("SELECT * FROM disputes WHERE id=?", (dispute_id,))
        if not d:
            raise NotFound("dispute not found")
        o = self._load(d["order_id"])
        if principal.user_id not in (o["buyer_id"], o["seller_id"]) and not principal.has("dispute:resolve") \
                and not principal.is_admin:
            raise NotFound("dispute not found")
        return d

    # ----------------------------------------------------------------- worker
    def auto_release_stale(self, after_hours: int = 72) -> int:
        """Buyer silent after delivery for N hours -> full acceptance and release (spec: no stuck escrow)."""
        from datetime import timedelta
        from ...shared.clock import to_iso
        cutoff = to_iso(self.ctx.clock.now() - timedelta(hours=after_hours))
        rows = self.db.all(
            "SELECT o.id FROM orders o JOIN state_transitions t ON t.entity_type='order' AND t.entity_id=o.id"
            " AND t.to_state='DELIVERED' WHERE o.state='DELIVERED' AND t.at<=?", (cutoff,))
        n = 0
        for r in rows:
            with self.db.transaction():
                o = self._load(r["id"])
                if o["state"] != "DELIVERED":
                    continue
                aq = o["delivered_qty_milli"]
                self._move(o, "INSPECTED", "system", "auto-accepted after buyer inactivity",
                           sets=", accepted_qty_milli=?, quality_result=?", params=(aq, "auto-accepted"))
                self.escrow.advance(o["id"], "INSPECTED", "system")
                o = self._load(o["id"])
                gross = min(line_total_minor(o["unit_price_minor"], aq), o["total_minor"])
                self.escrow.settle(o["id"], gross, o["total_minor"] - gross, "system", "auto-release")
                self._move(o, "COMPLETED", "system", "auto-release")
                n += 1
        return n
