import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as api from "./api";

export function useLots(farmId?: string) {
  return useQuery({
    queryKey: ["traceability", "lots", farmId ?? null],
    queryFn: () => api.listLots(farmId),
  });
}

export function useLot(id: string | undefined) {
  return useQuery({
    queryKey: ["traceability", "lots", "detail", id],
    queryFn: () => api.getLot(id as string),
    enabled: Boolean(id),
  });
}

export function useLotHistory(id: string | undefined) {
  return useQuery({
    queryKey: ["traceability", "lots", id, "history"],
    queryFn: () => api.lotHistory(id as string),
    enabled: Boolean(id),
  });
}

export function useCreateLot() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: api.createLot,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["traceability", "lots"] });
    },
  });
}

export function useRecordWeighing(lotId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: api.RecordWeighingPayload) => api.recordWeighing(lotId, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["traceability", "lots", lotId, "history"] });
    },
  });
}

export function useRecordInspection(lotId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: api.RecordInspectionPayload) => api.recordInspection(lotId, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["traceability", "lots", "detail", lotId] });
      queryClient.invalidateQueries({ queryKey: ["traceability", "lots", lotId, "history"] });
    },
  });
}
