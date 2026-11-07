"""Warehouse inventory: signed movements, reason mandatory (schema CHECK), stock = SUM(delta)."""
from __future__ import annotations

from ...security.permissions import Principal
from ...shared.context import Context
from ...shared.errors import NotFound, UnauthorizedResourceAccess, ValidationFailed
from ...shared.ids import new_id


class InventoryService:
    """Warehouse stock ledger: signed movements, reason mandatory (schema CHECK), stock = SUM(delta)."""

    def __init__(self, ctx: Context):
        self.ctx, self.db = ctx, ctx.db

    def create_warehouse(self, principal: Principal, *, org_id: str, name: str, state: str | None = None,
                         lga: str | None = None, lat: float | None = None, lon: float | None = None) -> dict:
        principal.require("inventory:manage")
        if not principal.is_org_member(org_id) and not principal.is_admin:
            raise UnauthorizedResourceAccess("not a member of that organization")
        wid = new_id()
        with self.db.transaction():
            self.db.execute("INSERT INTO warehouses(id,org_id,name,state,lga,lat,lon,created_at) VALUES (?,?,?,?,?,?,?,?)",
                            (wid, org_id, name.strip()[:120], state, lga, lat, lon, self.ctx.now_iso()))
        return self.db.one("SELECT * FROM warehouses WHERE id=?", (wid,))

    def move(self, principal: Principal, *, warehouse_id: str, lot_id: str, movement_type: str, qty_delta,
             reason: str, reference_type: str | None = None, reference_id: str | None = None) -> dict:
        principal.require("inventory:manage")
        valid_types = {"RECEIPT", "TRANSFER_IN", "TRANSFER_OUT", "ADJUSTMENT", "DISPATCH", "RETURN"}
        if movement_type not in valid_types:
            raise ValidationFailed(f"movement_type must be one of {sorted(valid_types)}")
        if not reason or not reason.strip():
            raise ValidationFailed("reason is required for every inventory movement")
        from ...shared.money import to_milli
        delta = to_milli(qty_delta)
        outflow = {"TRANSFER_OUT", "DISPATCH"}
        signed = -abs(delta) if movement_type in outflow else (delta if movement_type != "ADJUSTMENT" else delta)
        if signed == 0:
            raise ValidationFailed("qty_delta must be non-zero")
        with self.db.transaction():
            if not self.db.one("SELECT 1 FROM warehouses WHERE id=?", (warehouse_id,)):
                raise NotFound("warehouse not found")
            if not self.db.one("SELECT 1 FROM lots WHERE id=?", (lot_id,)):
                raise NotFound("lot not found")
            if signed < 0:
                current = self.stock(warehouse_id, lot_id)
                if current + signed < 0:
                    raise ValidationFailed("insufficient stock for this movement",
                                          details={"available_milli": current, "requested_milli": -signed})
            self.db.execute(
                "INSERT INTO inventory_movements(warehouse_id,lot_id,movement_type,qty_delta_milli,reason,"
                "reference_type,reference_id,actor_id,at) VALUES (?,?,?,?,?,?,?,?,?)",
                (warehouse_id, lot_id, movement_type, signed, reason.strip()[:500], reference_type, reference_id,
                 principal.user_id, self.ctx.now_iso()))
        return {"warehouse_id": warehouse_id, "lot_id": lot_id, "stock_milli": self.stock(warehouse_id, lot_id)}

    def stock(self, warehouse_id: str, lot_id: str) -> int:
        return self.db.scalar(
            "SELECT COALESCE(SUM(qty_delta_milli),0) FROM inventory_movements WHERE warehouse_id=? AND lot_id=?",
            (warehouse_id, lot_id)) or 0
