"""Traceability (spec section 22): lot creation and a per-lot custody hash-chain.

Each lot's custody events are hash-chained independently (chain key = lot_id), the same
tamper-evidence pattern as AuditService, so a farm-to-fork history can be verified lot by lot
even though the events table also serves many other lots. Weighing/quality/inventory here
model the physical world; the double-entry ledger (separately) models the money.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from ...security.permissions import Principal
from ...shared.context import Context
from ...shared.errors import NotFound, UnauthorizedResourceAccess, ValidationFailed
from ...shared.ids import lot_code, new_id

_EVENTS = {"HARVESTED", "AGGREGATED", "WAREHOUSED", "DISPATCHED", "IN_TRANSIT", "DELIVERED", "INSPECTED", "SPLIT",
           "RETURNED"}


def _canon(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


class TraceabilityService:
    def __init__(self, ctx: Context):
        self.ctx, self.db = ctx, ctx.db

    # ------------------------------------------------------------------- lots
    def create_lot(self, principal: Principal, *, farm_id: str, crop_id: str, quantity, unit: str,
                   harvest_date: str, quality_grade: str = "UNGRADED") -> dict:
        principal.require("lot:create")
        from ...shared.money import to_milli
        qty = to_milli(quantity)
        if qty <= 0:
            raise ValidationFailed("quantity must be positive")
        farm = self.db.one("SELECT owner_user_id FROM farms WHERE id=?", (farm_id,))
        if not farm:
            raise NotFound("farm not found")
        if farm["owner_user_id"] != principal.user_id and not principal.is_admin:
            raise UnauthorizedResourceAccess("not your farm")
        year = int(harvest_date[:4]) if harvest_date and harvest_date[:4].isdigit() else self.ctx.clock.now().year
        with self.db.transaction():
            lid = new_id()
            code = self._unique_code(year)
            self.db.execute(
                "INSERT INTO lots(id,code,farm_id,crop_id,owner_user_id,quantity_milli,unit,harvest_date,"
                "quality_grade,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (lid, code, farm_id, crop_id, principal.user_id, qty, unit, harvest_date, quality_grade,
                 self.ctx.now_iso()))
            self.record_event(lid, event_type="HARVESTED", actor_id=principal.user_id, weight_milli=qty,
                              location_label=f"farm:{farm_id}")
            self.ctx.publish("lot.created", "lot", lid, {"code": code})
            return self.get_lot(lid)

    def _unique_code(self, year: int) -> str:
        for _ in range(20):
            code = lot_code(year)
            if not self.db.one("SELECT 1 FROM lots WHERE code=?", (code,)):
                return code
        raise RuntimeError("could not generate a unique lot code")  # astronomically unlikely

    def get_lot(self, lot_id: str) -> dict:
        row = self.db.one("SELECT * FROM lots WHERE id=?", (lot_id,))
        if not row:
            raise NotFound("lot not found")
        return row

    def get_by_code(self, code: str) -> dict:
        row = self.db.one("SELECT * FROM lots WHERE code=?", (code,))
        if not row:
            raise NotFound("lot not found")
        return row

    def list_lots(self, principal: Principal, farm_id: str | None = None) -> list[dict]:
        """A lot's owner sees their own lots; an admin sees everything.
        Optionally scoped to one farm. Added for the frontend's traceability
        screens - the original route set had no "my lots" list, only
        single-lot reads by id or code."""
        if farm_id:
            farm = self.db.one("SELECT owner_user_id FROM farms WHERE id=?", (farm_id,))
            if not farm:
                raise NotFound("farm not found")
            if farm["owner_user_id"] != principal.user_id and not principal.is_admin:
                raise UnauthorizedResourceAccess("not your farm")
            return self.db.all("SELECT * FROM lots WHERE farm_id=? ORDER BY created_at DESC", (farm_id,))
        if principal.is_admin:
            return self.db.all("SELECT * FROM lots ORDER BY created_at DESC")
        return self.db.all("SELECT * FROM lots WHERE owner_user_id=? ORDER BY created_at DESC", (principal.user_id,))

    # -------------------------------------------------------------- custody
    def record_event(self, lot_id: str, *, event_type: str, actor_id: str, from_party: str | None = None,
                     to_party: str | None = None, location_label: str | None = None, lat: float | None = None,
                     lon: float | None = None, weight_milli: int | None = None, reference_type: str | None = None,
                     reference_id: str | None = None, note: str | None = None) -> dict:
        if event_type not in _EVENTS:
            raise ValidationFailed(f"event_type must be one of {sorted(_EVENTS)}")
        if not self.db.in_transaction:
            raise RuntimeError("record_event must run inside a transaction")
        if not self.db.one("SELECT 1 FROM lots WHERE id=?", (lot_id,)):
            raise NotFound("lot not found")
        prev = self.db.scalar("SELECT hash FROM custody_events WHERE lot_id=? ORDER BY id DESC LIMIT 1", (lot_id,))
        row = {"lot_id": lot_id, "event_type": event_type, "from_party": from_party, "to_party": to_party,
               "location_label": location_label, "lat": lat, "lon": lon, "weight_milli": weight_milli,
               "reference_type": reference_type, "reference_id": reference_id, "note": note, "actor_id": actor_id,
               "at": self.ctx.now_iso()}
        digest = hashlib.sha256(((prev or "") + _canon(row)).encode()).hexdigest()
        res = self.db.execute(
            "INSERT INTO custody_events(lot_id,event_type,from_party,to_party,location_label,lat,lon,weight_milli,"
            "reference_type,reference_id,note,actor_id,at,prev_hash,hash) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (lot_id, event_type, from_party, to_party, location_label, lat, lon, weight_milli, reference_type,
             reference_id, note, actor_id, row["at"], prev, digest))
        return self.db.one("SELECT * FROM custody_events WHERE id=?", (res.lastrowid,))

    def history(self, lot_id: str) -> list[dict]:
        if not self.db.one("SELECT 1 FROM lots WHERE id=?", (lot_id,)):
            raise NotFound("lot not found")
        return self.db.all("SELECT * FROM custody_events WHERE lot_id=? ORDER BY id", (lot_id,))

    def verify_chain(self, lot_id: str) -> tuple[bool, int | None]:
        prev = None
        for r in self.history(lot_id):
            body = {k: r[k] for k in ("lot_id", "event_type", "from_party", "to_party", "location_label", "lat",
                                      "lon", "weight_milli", "reference_type", "reference_id", "note", "actor_id", "at")}
            expected = hashlib.sha256(((prev or "") + _canon(body)).encode()).hexdigest()
            if r["prev_hash"] != prev or r["hash"] != expected:
                return False, r["id"]
            prev = r["hash"]
        return True, None

    # ------------------------------------------------------------ weighing / QC
    def record_weighing(self, principal: Principal, lot_id: str, *, gross_kg: float, tare_kg: float,
                        warehouse_id: str | None = None) -> dict:
        if gross_kg < tare_kg:
            raise ValidationFailed("gross weight cannot be less than tare weight")
        from ...shared.money import to_milli
        gross, tare = to_milli(gross_kg), to_milli(tare_kg)
        with self.db.transaction():
            if not self.db.one("SELECT 1 FROM lots WHERE id=?", (lot_id,)):
                raise NotFound("lot not found")
            wid = new_id()
            self.db.execute(
                "INSERT INTO weighing_records(id,lot_id,warehouse_id,gross_milli,tare_milli,net_milli,actor_id,at)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (wid, lot_id, warehouse_id, gross, tare, gross - tare, principal.user_id, self.ctx.now_iso()))
            return self.db.one("SELECT * FROM weighing_records WHERE id=?", (wid,))

    def record_inspection(self, principal: Principal, lot_id: str, *, grade: str, passed: bool,
                          moisture_pct: float | None = None, defects_pct: float | None = None,
                          notes: str = "") -> dict:
        if grade not in ("A", "B", "C", "REJECT"):
            raise ValidationFailed("grade must be A, B, C or REJECT")
        with self.db.transaction():
            if not self.db.one("SELECT 1 FROM lots WHERE id=?", (lot_id,)):
                raise NotFound("lot not found")
            qid = new_id()
            self.db.execute(
                "INSERT INTO quality_inspections(id,lot_id,inspector_id,grade,moisture_pct,defects_pct,passed,notes,at)"
                " VALUES (?,?,?,?,?,?,?,?,?)",
                (qid, lot_id, principal.user_id, grade, moisture_pct, defects_pct, 1 if passed else 0, notes[:1000],
                 self.ctx.now_iso()))
            self.record_event(lot_id, event_type="INSPECTED", actor_id=principal.user_id,
                              note=f"grade={grade} passed={passed}")
            if grade in ("A", "B", "C"):
                self.db.execute("UPDATE lots SET quality_grade=? WHERE id=?", (grade, lot_id))
            return self.db.one("SELECT * FROM quality_inspections WHERE id=?", (qid,))
