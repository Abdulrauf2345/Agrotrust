import { apiRequest } from "@/lib/api/client";
import type { Organization } from "@/types/api";

export interface OrgMembership extends Organization {
  org_role: "ADMIN" | "STAFF" | "MEMBER";
}

export function fetchMyOrganizations(): Promise<OrgMembership[]> {
  return apiRequest<OrgMembership[]>("/api/v1/organizations/mine");
}

export interface CreateOrganizationPayload {
  name: string;
  type: string;
  state?: string;
  lga?: string;
}

export function createOrganization(payload: CreateOrganizationPayload): Promise<Organization> {
  return apiRequest<Organization>("/api/v1/organizations", {
    method: "POST",
    body: payload,
  });
}
