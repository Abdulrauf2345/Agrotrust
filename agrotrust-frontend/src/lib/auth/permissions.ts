import type { Role } from "@/types/api";

// Mirrors src/agrotrust/security/permissions.py so the UI can hide actions a
// role cannot take. This is a convenience layer only: every one of these
// permissions is re-checked by the backend on the actual request, which is
// the real security boundary. Hiding a button here never substitutes for
// the server-side check.
const COMMON = ["kyc:submit", "wallet:view", "file:upload", "org:create", "notification:read"];
const SELLER = ["listing:create", "listing:manage", "order:read", "order:approve", "escrow:view", "dispute:open"];
const BUYER_ONLY = ["listing:search", "order:create", "order:fund", "escrow:release", "dispute:open"];
const LENDER_ONLY = ["loan-product:manage", "loan-application:decide", "loan:disburse"];
const AGENT_ONLY = ["farm:visit", "farm:verify-submit"];
const LOGISTICS_ONLY = ["shipment:manage", "vehicle:manage", "driver:manage"];
const ADMIN_ONLY = ["admin:users", "admin:audit", "dispute:resolve"];

export const ROLE_PERMISSIONS: Record<Role, readonly string[]> = {
  FARMER: [...COMMON, ...SELLER, "farm:create", "loan-application:create"],
  COOPERATIVE_ADMIN: [...COMMON, ...SELLER, "farm:create"],
  AGGREGATOR: [...COMMON, ...SELLER, "farm:create"],
  BUYER: [...COMMON, ...BUYER_ONLY],
  LENDER: [...COMMON, ...LENDER_ONLY],
  FIELD_AGENT: [...COMMON, ...AGENT_ONLY],
  LOGISTICS_PROVIDER: [...COMMON, ...LOGISTICS_ONLY],
  INSURER: [...COMMON, "insurance:manage"],
  PLATFORM_ADMIN: [...COMMON, ...ADMIN_ONLY, ...SELLER, ...BUYER_ONLY, ...LENDER_ONLY, ...AGENT_ONLY, ...LOGISTICS_ONLY],
};

export function roleHasPermission(roles: Role[], permission: string): boolean {
  return roles.some((role) => ROLE_PERMISSIONS[role]?.includes(permission));
}

export function primaryRole(roles: Role[]): Role | null {
  return roles[0] ?? null;
}
