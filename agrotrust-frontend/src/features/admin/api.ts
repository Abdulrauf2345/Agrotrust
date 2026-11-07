import { apiRequest } from "@/lib/api/client";
import type { AdminUserDetail, AdminUserSummary, AuditLogEntry, Dispute, Organization } from "@/types/api";

export interface ListUsersParams {
  status?: string;
  role?: string;
  limit?: number;
  offset?: number;
}

export function listUsers(params: ListUsersParams = {}): Promise<{ total: number; items: AdminUserSummary[] }> {
  return apiRequest<{ total: number; items: AdminUserSummary[] }>("/api/v1/admin/users", { query: params });
}

export function getUserDetail(id: string): Promise<AdminUserDetail> {
  return apiRequest<AdminUserDetail>(`/api/v1/admin/users/${id}`);
}

export interface AuditQueryParams {
  resource_type?: string;
  resource_id?: string;
  actor_id?: string;
  limit?: number;
}

export function auditTrail(params: AuditQueryParams = {}): Promise<AuditLogEntry[]> {
  return apiRequest<AuditLogEntry[]>("/api/v1/admin/audit", { query: params });
}

export function listAllOrganizations(): Promise<Organization[]> {
  return apiRequest<Organization[]>("/api/v1/organizations");
}

export function listDisputes(): Promise<Dispute[]> {
  return apiRequest<Dispute[]>("/api/v1/disputes");
}

export function getDispute(id: string): Promise<Dispute> {
  return apiRequest<Dispute>(`/api/v1/disputes/${id}`);
}

export interface ResolveDisputePayload {
  seller_amount_minor: number;
  buyer_amount_minor: number;
  resolution?: string;
}

export function resolveDispute(id: string, payload: ResolveDisputePayload): Promise<unknown> {
  return apiRequest(`/api/v1/disputes/${id}/resolve`, { method: "POST", body: payload });
}
