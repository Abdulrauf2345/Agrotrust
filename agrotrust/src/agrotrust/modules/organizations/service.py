"""Organizations (cooperatives, lenders, aggregators, ...) and tenant membership."""
from __future__ import annotations

from ...security.permissions import Principal, Role
from ...shared import geo
from ...shared.context import Context
from ...shared.errors import Conflict, NotFound, PermissionDenied, UnauthorizedResourceAccess, ValidationFailed
from ...shared.ids import new_id

ORG_TYPES = {"COOPERATIVE", "LENDER", "NGO", "BUYER", "AGGREGATOR", "LOGISTICS", "INSURER", "PROCESSOR", "OTHER"}
_ROLE_ORG_TYPES = {
    Role.COOPERATIVE_ADMIN: {"COOPERATIVE"}, Role.LENDER: {"LENDER"}, Role.AGGREGATOR: {"AGGREGATOR"},
    Role.LOGISTICS_PROVIDER: {"LOGISTICS"}, Role.INSURER: {"INSURER"}, Role.BUYER: {"BUYER", "PROCESSOR"},
}


class OrganizationService:
    def __init__(self, ctx: Context):
        self.ctx = ctx

    @property
    def db(self):
        return self.ctx.db

    def create(self, principal: Principal, *, name: str, type: str, state: str | None = None, lga: str | None = None,
               lat: float | None = None, lon: float | None = None) -> dict:
        principal.require("org:create")
        if type not in ORG_TYPES:
            raise ValidationFailed("invalid organization type", details={"allowed": sorted(ORG_TYPES)})
        if not principal.is_admin:
            allowed = set().union(*(_ROLE_ORG_TYPES.get(r, set()) for r in principal.roles)) if principal.roles else set()
            if type not in allowed:
                raise PermissionDenied(f"your role cannot create a {type} organization")
        name = (name or "").strip()
        if not 2 <= len(name) <= 120:
            raise ValidationFailed("name must be 2-120 characters")
        if (lat is None) != (lon is None):
            raise ValidationFailed("provide both lat and lon")
        if lat is not None:
            s = self.ctx.settings
            lat, lon = geo.validate_point(lat, lon, geo.Bounds(s.geo_min_lat, s.geo_max_lat, s.geo_min_lon, s.geo_max_lon))
        org_id, now = new_id(), self.ctx.now_iso()
        with self.db.transaction():
            self.db.execute("INSERT INTO organizations(id, name, type, state, lga, lat, lon, created_by, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                            (org_id, name, type, state, lga, lat, lon, principal.user_id, now, now))
            self.db.execute("INSERT INTO org_members(org_id, user_id, org_role, created_at) VALUES (?,?,?,?)",
                            (org_id, principal.user_id, "ADMIN", now))
            self.ctx.audit.record(actor_id=principal.user_id, action="ORG_CREATED", resource_type="organization", resource_id=org_id, new={"name": name, "type": type})
        return self.db.one("SELECT * FROM organizations WHERE id=?", (org_id,))

    def get(self, principal: Principal, org_id: str) -> dict:
        org = self.db.one("SELECT * FROM organizations WHERE id=?", (org_id,))
        if not org:
            raise NotFound("organization not found")
        if not (principal.is_admin or principal.is_org_member(org_id)):
            raise UnauthorizedResourceAccess("not a member of this organization")   # tenant isolation
        org["members"] = self.db.all("SELECT user_id, org_role FROM org_members WHERE org_id=?", (org_id,))
        return org

    def add_member(self, principal: Principal, org_id: str, user_id: str, org_role: str = "MEMBER") -> None:
        if org_role not in ("ADMIN", "STAFF", "MEMBER"):
            raise ValidationFailed("invalid org role")
        with self.db.transaction():
            if not self.db.one("SELECT 1 AS x FROM organizations WHERE id=?", (org_id,)):
                raise NotFound("organization not found")
            if not (principal.is_admin or principal.is_org_admin(org_id)):
                raise UnauthorizedResourceAccess("only organization admins can manage members")
            if not self.db.one("SELECT 1 AS x FROM users WHERE id=? AND status='ACTIVE'", (user_id,)):
                raise NotFound("user not found")
            res = self.db.execute("INSERT INTO org_members(org_id, user_id, org_role, created_at) VALUES (?,?,?,?) ON CONFLICT DO NOTHING",
                                  (org_id, user_id, org_role, self.ctx.now_iso()))
            if not res.rowcount:
                raise Conflict("already a member")
            self.ctx.audit.record(actor_id=principal.user_id, action="ORG_MEMBER_ADDED", resource_type="organization", resource_id=org_id,
                                  new={"user_id": user_id, "org_role": org_role})

    def remove_member(self, principal: Principal, org_id: str, user_id: str) -> None:
        with self.db.transaction():
            if not (principal.is_admin or principal.is_org_admin(org_id)):
                raise UnauthorizedResourceAccess("only organization admins can manage members")
            m = self.db.one("SELECT org_role FROM org_members WHERE org_id=? AND user_id=?", (org_id, user_id))
            if not m:
                raise NotFound("membership not found")
            if m["org_role"] == "ADMIN" and self.db.scalar("SELECT COUNT(*) FROM org_members WHERE org_id=? AND org_role='ADMIN'", (org_id,)) <= 1:
                raise Conflict("cannot remove the last organization admin")
            self.db.execute("DELETE FROM org_members WHERE org_id=? AND user_id=?", (org_id, user_id))
            self.ctx.audit.record(actor_id=principal.user_id, action="ORG_MEMBER_REMOVED", resource_type="organization", resource_id=org_id, old={"user_id": user_id})

    def mine(self, principal: Principal) -> list[dict]:
        return self.db.all("SELECT o.*, m.org_role FROM organizations o JOIN org_members m ON m.org_id=o.id WHERE m.user_id=? ORDER BY o.name", (principal.user_id,))

    def list_all(self, principal: Principal) -> list[dict]:
        """Every organization on the platform. Admin-only - added for the
        admin tools screen, which needs to browse organizations beyond the
        caller's own memberships."""
        if not principal.is_admin:
            raise PermissionDenied("only platform admins can list all organizations")
        return self.db.all("SELECT * FROM organizations ORDER BY created_at DESC")

    def nearby(self, *, type: str, lat: float, lon: float, radius_km: float = 50, limit: int = 20) -> list[dict]:
        """Nearby aggregators / logistics providers (public directory: names and coarse location only)."""
        lat, lon = geo.validate_point(lat, lon)
        min_lat, max_lat, min_lon, max_lon = geo.bbox_for_radius(lat, lon, radius_km)
        rows = self.db.all(
            "SELECT id, name, type, state, lga, lat, lon FROM organizations WHERE type=? AND status='ACTIVE'"
            " AND lat BETWEEN ? AND ? AND lon BETWEEN ? AND ?", (type, min_lat, max_lat, min_lon, max_lon))
        out = []
        for r in rows:
            d = geo.haversine_m(lat, lon, r["lat"], r["lon"])
            if d <= radius_km * 1000:
                r["distance_km"] = round(d / 1000, 2)
                out.append(r)
        return sorted(out, key=lambda r: r["distance_km"])[:limit]
