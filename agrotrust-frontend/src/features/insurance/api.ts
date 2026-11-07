import { apiRequest } from "@/lib/api/client";
import type { InsurancePolicy } from "@/types/api";

export interface BuyPolicyPayload {
  farm_id: string;
  coverage_minor: number;
  premium_minor: number;
  trigger_metric: string;
  comparator: string;
  threshold: number;
  window_start: string;
  window_end: string;
}

export function buyPolicy(payload: BuyPolicyPayload): Promise<InsurancePolicy> {
  return apiRequest<InsurancePolicy>("/api/v1/insurance/policies", { method: "POST", body: payload });
}

export function listPolicies(): Promise<InsurancePolicy[]> {
  return apiRequest<InsurancePolicy[]>("/api/v1/insurance/policies");
}

export function getPolicy(id: string): Promise<InsurancePolicy> {
  return apiRequest<InsurancePolicy>(`/api/v1/insurance/policies/${id}`);
}

export function payPremium(id: string): Promise<InsurancePolicy> {
  return apiRequest<InsurancePolicy>(`/api/v1/insurance/policies/${id}/pay-premium`, { method: "POST" });
}
