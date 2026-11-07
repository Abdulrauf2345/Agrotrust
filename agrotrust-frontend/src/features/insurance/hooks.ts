import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as api from "./api";

export function usePolicies() {
  return useQuery({
    queryKey: ["insurance", "policies"],
    queryFn: api.listPolicies,
  });
}

export function usePolicy(id: string | undefined) {
  return useQuery({
    queryKey: ["insurance", "policies", id],
    queryFn: () => api.getPolicy(id as string),
    enabled: Boolean(id),
  });
}

export function useBuyPolicy() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: api.buyPolicy,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["insurance", "policies"] });
    },
  });
}

export function usePayPremium(policyId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api.payPremium(policyId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["insurance", "policies"] });
    },
  });
}
