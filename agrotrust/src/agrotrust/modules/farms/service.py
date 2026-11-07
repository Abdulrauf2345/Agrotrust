"""Farm registry (spec section 9): CRUD, geo, verification lifecycle, field-agent visits.

Verification lifecycle is intentionally conservative: only a field-agent visit (proving
physical presence within ``max_visit_distance_m`` of the claimed point/polygon) can move a
farm to SUBMITTED; only an admin/cooperative-admin can then VERIFY or REJECT.
"""
from __future__ import annotations

from ...security.permissions import Principal
from ...shared import geo
from ...shared.context import Context
from ...shared.errors import (ConcurrentModification, Conflict, NotFound, UnauthorizedResourceAccess,
                              ValidationFailed)
from ...shared.ids import new_id
from ...shared.state_machine import StateMachine
from ..files.service import FileService

FARM_SM = StateMachine("farm_verification", {
    "UNVERIFIED": ["PENDING"],
    "PENDING": ["ASSIGNED"],
    "ASSIGNED": ["VISITED", "PENDING"],       # re-assignable if the agent cannot make it
    "VISITED": ["SUBMITTED"],
    "SUBMITTED": ["UNDER_REVIEW"],
    "UNDER_REVIEW": ["VERIFIED", "REJECTED"],
    "REJECTED": ["PENDING"],                  # farmer may fix issues and resubmit
})


class FarmService:
    def __init__(self, ctx: Context, files: FileService | None = None):
        self.ctx, self.db, self.files = ctx, ctx.db, files

    # ----------------------------------------------------------------- CRUD
    def create(self, principal: Principal, *, name: str, state: str, lga: str, size_hectares: float, lat: float,
              lon: float, community: str | None = None, org_id: str | None = None,
              boundary_geojson: dict | None = None, crop_ids: list[str] | None = None) -> dict:
        principal.require("farm:create")
        name = (name or "").strip()
        if not 2 <= len(name) <= 120:
            raise ValidationFailed("name must be 2-120 characters")
        if not state or not lga:
            raise ValidationFailed("state and lga are required")
        if not isinstance(size_hectares, (int, float)) or isinstance(size_hectares, bool) or size_hectares <= 0:
            raise ValidationFailed("size_hectares must be a positive number")
        geo.validate_point(lat, lon)
        boundary_text = None
        if boundary_geojson is not None:
            ring = geo.parse_polygon_geojson(boundary_geojson)
            area = geo.ring_area_ha(ring)
            if area <= 0:
                raise ValidationFailed("boundary encloses no area")
            if not geo.point_in_ring(lat, lon, ring):
                raise ValidationFailed("farm point must lie within its own boundary")
            boundary_text = geo.polygon_geojson(ring)
        if org_id and not principal.is_org_member(org_id) and not principal.is_admin:
            raise UnauthorizedResourceAccess("not a member of that organization")
        with self.db.transaction():
            fid, now = new_id(), self.ctx.now_iso()
            self.db.execute(
                "INSERT INTO farms(id,owner_user_id,org_id,name,state,lga,community,size_hectares,lat,lon,"
                "boundary_geojson,verification_status,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (fid, principal.user_id, org_id, name, state, lga, community, size_hectares, lat, lon, boundary_text,
                 "UNVERIFIED", now, now))
            for cid in crop_ids or []:
                if not self.db.one("SELECT 1 FROM crops WHERE id=? AND active=1", (cid,)):
                    raise ValidationFailed(f"unknown crop: {cid}")
                self.db.execute("INSERT INTO farm_crops(farm_id, crop_id) VALUES (?,?)", (fid, cid))
            self.ctx.audit.record(actor_id=principal.user_id, action="FARM_CREATED", resource_type="farm",
                                  resource_id=fid, new={"state": state, "lga": lga})
            self.ctx.publish("farm.created", "farm", fid, {})
            return self._load(fid)

    def _load(self, farm_id: str) -> dict:
        row = self.db.one("SELECT * FROM farms WHERE id=?", (farm_id,))
        if not row:
            raise NotFound("farm not found")
        return row

    def get(self, principal: Principal, farm_id: str) -> dict:
        row = self._load(farm_id)
        if row["owner_user_id"] != principal.user_id and not principal.has("farm:read_any") \
                and row["assigned_agent_id"] != principal.user_id:
            raise UnauthorizedResourceAccess("not your farm")
        return row

    def list_mine(self, principal: Principal) -> list[dict]:
        return self.db.all("SELECT * FROM farms WHERE owner_user_id=? ORDER BY created_at DESC", (principal.user_id,))

    def nearby(self, lat: float, lon: float, radius_km: float, *, verified_only: bool = True, limit: int = 20) -> list[dict]:
        geo.validate_point(lat, lon)
        min_lat, max_lat, min_lon, max_lon = geo.bbox_for_radius(lat, lon, radius_km)
        where = "lat BETWEEN ? AND ? AND lon BETWEEN ? AND ?"
        params = [min_lat, max_lat, min_lon, max_lon]
        if verified_only:
            where += " AND verification_status='VERIFIED'"
        rows = self.db.all(f"SELECT * FROM farms WHERE {where}", params)
        rows = [r for r in rows if geo.haversine_m(lat, lon, r["lat"], r["lon"]) <= radius_km * 1000]
        rows.sort(key=lambda r: geo.haversine_m(lat, lon, r["lat"], r["lon"]))
        return rows[:limit]

    def update(self, principal: Principal, farm_id: str, **fields) -> dict:
        with self.db.transaction():
            row = self._load(farm_id)
            if row["owner_user_id"] != principal.user_id and not principal.is_admin:
                raise UnauthorizedResourceAccess("not your farm")
            if row["verification_status"] not in ("UNVERIFIED", "REJECTED", "PENDING"):
                raise Conflict("cannot edit a farm that is under verification or already verified; "
                               "request re-verification instead")
            allowed = {"name", "community", "size_hectares"}
            sets, params = [], []
            for k, v in fields.items():
                if k not in allowed:
                    raise ValidationFailed(f"cannot update field: {k}")
                sets.append(f"{k}=?")
                params.append(v)
            if not sets:
                return row
            params += [self.ctx.now_iso(), row["version"], farm_id]
            res = self.db.execute(f"UPDATE farms SET {', '.join(sets)}, version=version+1, updated_at=?"
                                  " WHERE version=? AND id=?", params)
            if res.rowcount != 1:
                raise ConcurrentModification("farm was modified concurrently; retry")
            return self._load(farm_id)

    def attach_photo(self, principal: Principal, farm_id: str, file_id: str, kind: str = "PHOTO") -> None:
        with self.db.transaction():
            row = self._load(farm_id)
            if row["owner_user_id"] != principal.user_id and not principal.is_admin:
                raise UnauthorizedResourceAccess("not your farm")
            if self.files:
                self.files.owned(principal, file_id)
            self.db.execute("INSERT INTO farm_files(farm_id, file_id, kind) VALUES (?,?,?)", (farm_id, file_id, kind))

    # ---------------------------------------------------------- verification
    def _transition(self, row: dict, new_state: str, actor_id: str | None, reason: str | None = None,
                    extra_sql: str = "", extra_params: tuple = ()) -> dict:
        FARM_SM.assert_can(row["verification_status"], new_state)
        res = self.db.execute(
            f"UPDATE farms SET verification_status=?, version=version+1, updated_at=?{extra_sql}"
            " WHERE id=? AND version=?",
            (new_state, self.ctx.now_iso(), *extra_params, row["id"], row["version"]))
        if res.rowcount != 1:
            raise ConcurrentModification("farm was modified concurrently; retry")
        self.ctx.log_transition("farm", row["id"], row["verification_status"], new_state, actor_id, reason)
        return self._load(row["id"])

    def request_verification(self, principal: Principal, farm_id: str) -> dict:
        principal.require("farm:request_verification")
        with self.db.transaction():
            row = self._load(farm_id)
            if row["owner_user_id"] != principal.user_id:
                raise UnauthorizedResourceAccess("not your farm")
            return self._transition(row, "PENDING", principal.user_id)

    def assign_agent(self, principal: Principal, farm_id: str, agent_id: str) -> dict:
        principal.require("farm:assign_agent")
        with self.db.transaction():
            row = self._load(farm_id)
            agent = self.db.one("SELECT 1 FROM user_roles WHERE user_id=? AND role='FIELD_AGENT'", (agent_id,))
            if not agent:
                raise ValidationFailed("target user is not a field agent")
            return self._transition(row, "ASSIGNED", principal.user_id,
                                    extra_sql=", assigned_agent_id=?", extra_params=(agent_id,))

    def record_visit(self, principal: Principal, farm_id: str, *, lat: float, lon: float, client_id: str,
                     observations: str = "", visited_at: str | None = None) -> dict:
        """Idempotent on (agent_id, client_id) - safe to replay from an offline queue."""
        principal.require("farm:visit")
        geo.validate_point(lat, lon)
        with self.db.transaction():
            row = self._load(farm_id)
            if row["assigned_agent_id"] != principal.user_id:
                raise UnauthorizedResourceAccess("you are not the assigned agent for this farm")
            existing = self.db.one("SELECT id FROM farm_visits WHERE agent_id=? AND client_id=?",
                                   (principal.user_id, client_id))
            if existing:
                return self._load(farm_id)   # replay: no-op
            if row["boundary_geojson"]:
                ring = geo.parse_polygon_geojson(row["boundary_geojson"])
                distance = geo.distance_to_ring_m(lat, lon, ring)
            else:
                distance = geo.haversine_m(lat, lon, row["lat"], row["lon"])
            if distance > self.ctx.settings.max_visit_distance_m:
                raise ValidationFailed("visit location is too far from the registered farm",
                                       details={"distance_m": round(distance, 1),
                                                "max_m": self.ctx.settings.max_visit_distance_m})
            self.db.execute(
                "INSERT INTO farm_visits(id,farm_id,agent_id,client_id,lat,lon,distance_m,observations,visited_at,"
                "created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (new_id(), farm_id, principal.user_id, client_id, lat, lon, distance, observations[:2000],
                 visited_at or self.ctx.now_iso(), self.ctx.now_iso()))
            return self._transition(row, "VISITED", principal.user_id)

    def submit(self, principal: Principal, farm_id: str) -> dict:
        principal.require("farm:visit")
        with self.db.transaction():
            row = self._load(farm_id)
            if row["assigned_agent_id"] != principal.user_id:
                raise UnauthorizedResourceAccess("you are not the assigned agent for this farm")
            if not self.db.one("SELECT 1 FROM farm_visits WHERE farm_id=? AND agent_id=?", (farm_id, principal.user_id)):
                raise Conflict("no recorded visit for this farm")
            new = self._transition(row, "SUBMITTED", principal.user_id)
            return self._transition(new, "UNDER_REVIEW", principal.user_id)

    def verify(self, principal: Principal, farm_id: str, notes: str = "") -> dict:
        principal.require("farm:verify")
        with self.db.transaction():
            row = self._load(farm_id)
            return self._transition(row, "VERIFIED", principal.user_id, notes,
                                    extra_sql=", verified_at=?, notes=?", extra_params=(self.ctx.now_iso(), notes[:2000]))

    def reject(self, principal: Principal, farm_id: str, reason: str) -> dict:
        principal.require("farm:verify")
        if not reason or len(reason.strip()) < 5:
            raise ValidationFailed("a rejection reason is required")
        with self.db.transaction():
            row = self._load(farm_id)
            return self._transition(row, "REJECTED", principal.user_id, reason, extra_sql=", notes=?",
                                    extra_params=(reason[:2000],))
