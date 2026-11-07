import { apiRequest } from "@/lib/api/client";
import type { BuyerAnalytics, FarmerAnalytics, PlatformAnalytics } from "@/types/api";

export function fetchMyAnalytics(): Promise<FarmerAnalytics> {
  return apiRequest<FarmerAnalytics>("/api/v1/analytics/me");
}

export function fetchBuyerAnalytics(): Promise<BuyerAnalytics> {
  return apiRequest<BuyerAnalytics>("/api/v1/analytics/buyer");
}

export function fetchPlatformAnalytics(): Promise<PlatformAnalytics> {
  return apiRequest<PlatformAnalytics>("/api/v1/analytics/platform");
}
