"""Admin: thin aggregation over IdentityService/OrganizationService/AuditService for
platform-admin operations. Deliberately does not duplicate business logic - it composes the
already-tested services so admin actions get the same audit trail and invariants as everything
else (e.g. suspending a user still goes through IdentityService.set_status, which revokes
sessions; it isn't reimplemented here with a raw UPDATE).
"""
from __future__ import annotations

from ...security.permissions import Principal
from ...shared.context import Context
from ...shared.errors import ValidationFailed


class AdminService:
    def __init__(self, ctx: Context, identity, organizations, audit):
        self.ctx, self.db = ctx, ctx.db
        self.identity, self.organizations, self.audit = identity, organizations, audit

    def list_users(self, principal: Principal, *, status: str | None = None, role: str | None = None,
                   limit: int = 50, offset: int = 0) -> dict:
        principal.require("user:manage")
        limit = max(1, min(int(limit), 200))
        where, params = ["1=1"], []
        if status:
            where.append("u.status=?")
            params.append(status)
        if role:
            where.append("EXISTS (SELECT 1 FROM user_roles ur WHERE ur.user_id=u.id AND ur.role=?)")
            params.append(role)
        total = self.db.scalar(f"SELECT COUNT(*) FROM users u WHERE {' AND '.join(where)}", params)
        rows = self.db.all(f"SELECT u.id, u.phone, u.email, u.full_name, u.status, u.created_at FROM users u"
                           f" WHERE {' AND '.join(where)} ORDER BY u.created_at DESC LIMIT ? OFFSET ?",
                           [*params, limit, offset])
        return {"total": total, "items": rows}

    def user_detail(self, principal: Principal, user_id: str) -> dict:
        principal.require("user:manage")
        user = self.db.one("SELECT id, phone, email, full_name, status, created_at FROM users WHERE id=?", (user_id,))
        if not user:
            raise ValidationFailed("user not found")
        roles = [r["role"] for r in self.db.all("SELECT role FROM user_roles WHERE user_id=?", (user_id,))]
        orgs = self.db.all("SELECT org_id, org_role AS role FROM org_members WHERE user_id=?", (user_id,))
        kyc = self.db.one("SELECT status, updated_at FROM kyc_records WHERE user_id=?", (user_id,))
        return {**user, "roles": roles, "organizations": orgs, "kyc": kyc}

    def audit_trail(self, principal: Principal, *, resource_type: str | None = None, resource_id: str | None = None,
                    actor_id: str | None = None, limit: int = 100) -> list[dict]:
        principal.require("audit:view")
        return self.audit.query(resource_type=resource_type, resource_id=resource_id, actor_id=actor_id, limit=limit)

    def platform_config(self, principal: Principal) -> dict:
        principal.require("config:manage")
        rows = self.db.all("SELECT key, value FROM system_config")
        return {r["key"]: r["value"] for r in rows}

    def set_config(self, principal: Principal, key: str, value: str) -> None:
        principal.require("config:manage")
        if not key or len(key) > 100:
            raise ValidationFailed("invalid config key")
        with self.db.transaction():
            self.db.execute("INSERT INTO system_config(key,value,updated_at,updated_by) VALUES (?,?,?,?)"
                            " ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at,"
                            " updated_by=excluded.updated_by", (key, value, self.ctx.now_iso(), principal.user_id))
            self.audit.record(actor_id=principal.user_id, action="CONFIG_CHANGED", resource_type="system_config",
                              resource_id=key, new={"value": value})
