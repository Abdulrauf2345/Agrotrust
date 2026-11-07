"""Logistics (spec section 23): shipments, milestone-only location capture.

By design there is no continuous GPS tracking stream - only discrete delivery_events at
pickup/transit/delivery milestones, matching the schema and keeping the driver's location
data minimal (spec section 32 data minimization).
"""
from __future__ import annotations

from ...security.permissions import Principal
from ...shared import geo
from ...shared.context import Context
from ...shared.errors import (ConcurrentModification, NotFound, UnauthorizedResourceAccess, ValidationFailed)
from ...shared.ids import new_id
from ...shared.state_machine import StateMachine

SHIPMENT_SM = StateMachine("shipment", {
    "CREATED": ["ASSIGNED", "FAILED"],
    "ASSIGNED": ["PICKED_UP", "FAILED"],
    "PICKED_UP": ["IN_TRANSIT", "FAILED"],
    "IN_TRANSIT": ["DELIVERED", "FAILED"],
    "DELIVERED": ["CONFIRMED"],
})


class LogisticsService:
    def __init__(self, ctx: Context):
        self.ctx, self.db = ctx, ctx.db

    # --------------------------------------------------------------- fleet
    def register_vehicle(self, principal: Principal, *, org_id: str, plate: str, vehicle_type: str,
                         capacity_kg: int) -> dict:
        principal.require("shipment:manage")
        if not principal.is_org_member(org_id) and not principal.is_admin:
            raise UnauthorizedResourceAccess("not a member of that organization")
        if capacity_kg <= 0:
            raise ValidationFailed("capacity_kg must be positive")
        vid = new_id()
        with self.db.transaction():
            try:
                self.db.execute("INSERT INTO vehicles(id,org_id,plate,vehicle_type,capacity_kg) VALUES (?,?,?,?,?)",
                                (vid, org_id, plate.strip().upper(), vehicle_type, capacity_kg))
            except Exception as e:
                if "UNIQUE" in str(e).upper():
                    raise ValidationFailed("a vehicle with that plate is already registered") from e
                raise
        return self.db.one("SELECT * FROM vehicles WHERE id=?", (vid,))

    def register_driver(self, principal: Principal, *, org_id: str, name: str, phone: str,
                        user_id: str | None = None) -> dict:
        principal.require("shipment:manage")
        if not principal.is_org_member(org_id) and not principal.is_admin:
            raise UnauthorizedResourceAccess("not a member of that organization")
        did = new_id()
        with self.db.transaction():
            self.db.execute("INSERT INTO drivers(id,org_id,user_id,name,phone) VALUES (?,?,?,?,?)",
                            (did, org_id, user_id, name.strip()[:120], phone))
        return self.db.one("SELECT * FROM drivers WHERE id=?", (did,))

    # ------------------------------------------------------------ shipments
    def request(self, principal: Principal, *, order_id: str, pickup_lat: float, pickup_lon: float,
               dropoff_lat: float, dropoff_lon: float, scheduled_pickup: str | None = None) -> dict:
        principal.require("shipment:request")
        order = self.db.one("SELECT buyer_id, seller_id FROM orders WHERE id=?", (order_id,))
        if not order:
            raise NotFound("order not found")
        if principal.user_id not in (order["buyer_id"], order["seller_id"]):
            raise NotFound("order not found")
        geo.validate_point(pickup_lat, pickup_lon)
        geo.validate_point(dropoff_lat, dropoff_lon)
        sid = new_id()
        with self.db.transaction():
            self.db.execute(
                "INSERT INTO shipments(id,order_id,state,pickup_lat,pickup_lon,dropoff_lat,dropoff_lon,"
                "scheduled_pickup,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (sid, order_id, "CREATED", pickup_lat, pickup_lon, dropoff_lat, dropoff_lon, scheduled_pickup,
                 self.ctx.now_iso(), self.ctx.now_iso()))
            self.ctx.publish("shipment.requested", "shipment", sid, {"order_id": order_id})
        return self._load(sid)

    def _load(self, shipment_id: str) -> dict:
        row = self.db.one("SELECT * FROM shipments WHERE id=?", (shipment_id,))
        if not row:
            raise NotFound("shipment not found")
        return row

    def assign(self, principal: Principal, shipment_id: str, *, driver_id: str, vehicle_id: str,
              provider_org_id: str) -> dict:
        principal.require("shipment:manage")
        if not principal.is_org_member(provider_org_id) and not principal.is_admin:
            raise UnauthorizedResourceAccess("not a member of that organization")
        with self.db.transaction():
            s = self._load(shipment_id)
            drv = self.db.one("SELECT org_id FROM drivers WHERE id=? AND active=1", (driver_id,))
            veh = self.db.one("SELECT org_id FROM vehicles WHERE id=? AND active=1", (vehicle_id,))
            if not drv or drv["org_id"] != provider_org_id:
                raise ValidationFailed("driver not found in this organization")
            if not veh or veh["org_id"] != provider_org_id:
                raise ValidationFailed("vehicle not found in this organization")
            return self._move(s, "ASSIGNED", principal.user_id,
                              sets=", driver_id=?, vehicle_id=?, provider_org_id=?",
                              params=(driver_id, vehicle_id, provider_org_id))

    def _move(self, s: dict, new_state: str, actor_id: str, note: str | None = None, sets: str = "",
              params: tuple = (), lat: float | None = None, lon: float | None = None) -> dict:
        SHIPMENT_SM.assert_can(s["state"], new_state)
        res = self.db.execute(
            f"UPDATE shipments SET state=?, version=version+1, updated_at=?{sets} WHERE id=? AND version=?",
            (new_state, self.ctx.now_iso(), *params, s["id"], s["version"]))
        if res.rowcount != 1:
            raise ConcurrentModification("shipment modified concurrently; retry")
        self.db.execute(
            "INSERT INTO delivery_events(shipment_id,event_type,lat,lon,note,actor_id,at) VALUES (?,?,?,?,?,?,?)",
            (s["id"], new_state, lat, lon, note, actor_id, self.ctx.now_iso()))
        self.ctx.publish(f"shipment.{new_state.lower()}", "shipment", s["id"], {"order_id": s["order_id"]})
        return self._load(s["id"])

    def mark_picked_up(self, principal: Principal, shipment_id: str, lat: float, lon: float) -> dict:
        principal.require("shipment:update")
        geo.validate_point(lat, lon)
        with self.db.transaction():
            return self._move(self._load(shipment_id), "PICKED_UP", principal.user_id, lat=lat, lon=lon)

    def mark_in_transit(self, principal: Principal, shipment_id: str) -> dict:
        principal.require("shipment:update")
        with self.db.transaction():
            return self._move(self._load(shipment_id), "IN_TRANSIT", principal.user_id)

    def mark_delivered(self, principal: Principal, shipment_id: str, lat: float, lon: float) -> dict:
        principal.require("shipment:update")
        geo.validate_point(lat, lon)
        with self.db.transaction():
            return self._move(self._load(shipment_id), "DELIVERED", principal.user_id, lat=lat, lon=lon)

    def mark_failed(self, principal: Principal, shipment_id: str, reason: str) -> dict:
        principal.require("shipment:update")
        if not reason:
            raise ValidationFailed("a reason is required")
        with self.db.transaction():
            return self._move(self._load(shipment_id), "FAILED", principal.user_id, note=reason[:500])

    def confirm(self, principal: Principal, shipment_id: str) -> dict:
        """Recipient (buyer) confirms receipt - closes the loop independent of the order's own inspection."""
        with self.db.transaction():
            s = self._load(shipment_id)
            order = self.db.one("SELECT buyer_id FROM orders WHERE id=?", (s["order_id"],))
            if not order or order["buyer_id"] != principal.user_id:
                raise NotFound("shipment not found")
            return self._move(s, "CONFIRMED", principal.user_id)

    def track(self, principal: Principal, shipment_id: str) -> list[dict]:
        s = self._load(shipment_id)
        order = self.db.one("SELECT buyer_id, seller_id FROM orders WHERE id=?", (s["order_id"],))
        if principal.user_id not in (order["buyer_id"], order["seller_id"]) and not principal.has("order:read_any"):
            raise NotFound("shipment not found")
        return self.db.all("SELECT * FROM delivery_events WHERE shipment_id=? ORDER BY id", (shipment_id,))

    # ------------------------------------------------------------- listings
    # Added for the frontend's fleet and shipment-tracking screens - the
    # original route set only exposed single-resource reads (track by id)
    # plus the write actions, with no way to list "my vehicles" or "my
    # shipments". That is a real gap for any UI, not just a nice-to-have.

    def list_vehicles(self, principal: Principal, org_id: str) -> list[dict]:
        if not principal.is_org_member(org_id) and not principal.is_admin:
            raise UnauthorizedResourceAccess("not a member of that organization")
        return self.db.all("SELECT * FROM vehicles WHERE org_id=? ORDER BY plate", (org_id,))

    def list_drivers(self, principal: Principal, org_id: str) -> list[dict]:
        if not principal.is_org_member(org_id) and not principal.is_admin:
            raise UnauthorizedResourceAccess("not a member of that organization")
        return self.db.all("SELECT * FROM drivers WHERE org_id=? ORDER BY name", (org_id,))

    def list_shipments(self, principal: Principal) -> list[dict]:
        """Shipments the caller can legitimately see: as the order's buyer or
        seller, as a member of the assigned logistics provider org, or as a
        platform admin. No single column captures "relevant to this user", so
        this is a three-way OR across the owning relationships rather than one
        simple WHERE org_id=? - matching the same visibility rule track()
        already enforces for a single shipment.
        """
        if principal.is_admin or principal.has("order:read_any"):
            return self.db.all("SELECT * FROM shipments ORDER BY updated_at DESC")
        org_ids = tuple(principal.org_roles.keys())
        placeholders = ",".join("?" * len(org_ids)) if org_ids else "''"
        return self.db.all(
            f"SELECT s.* FROM shipments s JOIN orders o ON o.id = s.order_id "
            f"WHERE o.buyer_id=? OR o.seller_id=? OR s.provider_org_id IN ({placeholders}) "
            f"ORDER BY s.updated_at DESC",
            (principal.user_id, principal.user_id, *org_ids),
        )
