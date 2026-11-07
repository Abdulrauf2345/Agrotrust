import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as api from "./api";

export function useMyFarms() {
  return useQuery({ queryKey: ["farms"], queryFn: api.listMyFarms });
}

export function useFarm(id: string | undefined) {
  return useQuery({
    queryKey: ["farms", id],
    queryFn: () => api.getFarm(id as string),
    enabled: !!id,
  });
}

export function useCreateFarm() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: api.createFarm,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["farms"] });
    },
  });
}

export function useRequestVerification(farmId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api.requestVerification(farmId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["farms", farmId] });
    },
  });
}
