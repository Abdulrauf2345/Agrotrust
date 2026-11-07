import { useQuery } from "@tanstack/react-query";
import * as api from "./api";

export function useMyAnalytics() {
  return useQuery({ queryKey: ["analytics", "me"], queryFn: api.fetchMyAnalytics, retry: false });
}

export function useBuyerAnalytics() {
  return useQuery({ queryKey: ["analytics", "buyer"], queryFn: api.fetchBuyerAnalytics, retry: false });
}

export function usePlatformAnalytics() {
  return useQuery({ queryKey: ["analytics", "platform"], queryFn: api.fetchPlatformAnalytics, retry: false });
}
