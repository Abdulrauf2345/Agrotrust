import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as api from "./api";

export function useMyOrganizations() {
  return useQuery({
    queryKey: ["organizations", "mine"],
    queryFn: api.fetchMyOrganizations,
  });
}

export function useCreateOrganization() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: api.createOrganization,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["organizations", "mine"] });
    },
  });
}
