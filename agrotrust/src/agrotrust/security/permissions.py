"""Roles, permissions and the Principal.

Authorization is layered:
  1. authentication            -> Principal built from the DB (never from token claims)
  2. permission check          -> principal.require("escrow:release")
  3. resource-level check      -> ownership / org membership / assignment, in services
Roles and their permissions are stored in the database so new roles can be added
at runtime; the maps below are only the seed defaults.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..shared.errors import PermissionDenied


class Role:
    FARMER = "FARMER"
    COOPERATIVE_ADMIN = "COOPERATIVE_ADMIN"
    AGGREGATOR = "AGGREGATOR"
    BUYER = "BUYER"
    LENDER = "LENDER"
    FIELD_AGENT = "FIELD_AGENT"
    LOGISTICS_PROVIDER = "LOGISTICS_PROVIDER"
    INSURER = "INSURER"
    PLATFORM_ADMIN = "PLATFORM_ADMIN"


SELF_REGISTERABLE = {Role.FARMER, Role.BUYER, Role.AGGREGATOR, Role.LOGISTICS_PROVIDER}

_COMMON = {"kyc:submit", "wallet:view", "file:upload", "org:create", "notification:read"}
_SELLER = {"listing:create", "listing:manage", "order:read", "order:approve", "escrow:view", "dispute:open",
           "payout:request", "lot:create", "custody:record", "contract:respond", "insurance:buy", "shipment:request"}
_BUYER = {"order:create", "order:read", "payment:initiate", "escrow:view", "escrow:release_own", "dispute:open",
          "payout:request", "contract:create", "contract:respond", "shipment:request", "analytics:buyer"}
_FARM_MGMT = {"farm:create", "farm:read", "farm:update", "farm:request_verification", "loan:apply", "loan:repay",
              "credit:view_own", "analytics:farmer"}

# Buyers can release their own escrow after inspection; sellers (farmers) never can.
ROLE_PERMISSIONS: dict[str, set[str]] = {
    Role.FARMER: _COMMON | _SELLER | _FARM_MGMT | {"sync:push"},
    Role.COOPERATIVE_ADMIN: _COMMON | _SELLER | _FARM_MGMT | {"farm:assign_agent", "org:manage"},
    Role.AGGREGATOR: _COMMON | _SELLER | _BUYER | {"inventory:manage", "org:manage"},
    Role.BUYER: _COMMON | _BUYER,
    Role.LENDER: _COMMON | {"loan:product_create", "loan:approve", "loan:disburse", "loan:read_portfolio",
                            "credit:view_applicants", "org:manage", "analytics:lender"},
    Role.FIELD_AGENT: _COMMON | {"farm:read", "farm:visit", "sync:push"},
    Role.LOGISTICS_PROVIDER: _COMMON | {"shipment:manage", "shipment:update", "org:manage", "order:read"},
    Role.INSURER: _COMMON | {"insurance:manage", "insurance:claim_view", "org:manage"},
    Role.PLATFORM_ADMIN: {"*"},
}

ALL_PERMISSIONS = sorted({p for perms in ROLE_PERMISSIONS.values() for p in perms if p != "*"} | {
    "farm:verify", "farm:read_any", "escrow:release", "escrow:refund", "dispute:resolve", "ledger:view",
    "user:manage", "role:manage", "audit:view", "analytics:platform", "analytics:ops", "kyc:read",
    "config:manage", "order:read_any", "loan:read_any", "insurance:evaluate", "ml:manage", "listing:moderate",
})


@dataclass(frozen=True)
class Principal:
    user_id: str
    roles: frozenset[str]
    permissions: frozenset[str]
    org_roles: dict[str, str] = field(default_factory=dict)  # org_id -> ADMIN|STAFF|MEMBER

    def has(self, permission: str) -> bool:
        return "*" in self.permissions or permission in self.permissions

    def require(self, permission: str) -> None:
        if not self.has(permission):
            raise PermissionDenied(f"missing permission: {permission}", details={"required": permission})

    @property
    def is_admin(self) -> bool:
        return "PLATFORM_ADMIN" in self.roles

    def is_org_member(self, org_id: str) -> bool:
        return org_id in self.org_roles

    def is_org_admin(self, org_id: str) -> bool:
        return self.org_roles.get(org_id) == "ADMIN"
