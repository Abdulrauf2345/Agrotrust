import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as api from "./api";

export function useAdminUsers(params: api.ListUsersParams = {}) {
  return useQuery({
    queryKey: ["admin", "users", params],
    queryFn: () => api.listUsers(params),
  });
}

export function useAdminUserDetail(id: string | undefined) {
  return useQuery({
    queryKey: ["admin", "users", "detail", id],
    queryFn: () => api.getUserDetail(id as string),
    enabled: Boolean(id),
  });
}

export function useAuditTrail(params: api.AuditQueryParams = {}) {
  return useQuery({
    queryKey: ["admin", "audit", params],
    queryFn: () => api.auditTrail(params),
  });
}

export function useAllOrganizations() {
  return useQuery({
    queryKey: ["admin", "organizations"],
    queryFn: api.listAllOrganizations,
  });
}

export function useAdminDisputes() {
  return useQuery({
    queryKey: ["admin", "disputes"],
    queryFn: api.listDisputes,
  });
}

export function useResolveDispute() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...payload }: { id: string } & api.ResolveDisputePayload) => api.resolveDispute(id, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "disputes"] });
    },
  });
}
