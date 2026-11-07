import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as api from "./api";

export function useVehicles(orgId: string | undefined) {
  return useQuery({
    queryKey: ["logistics", "vehicles", orgId],
    queryFn: () => api.listVehicles(orgId as string),
    enabled: Boolean(orgId),
  });
}

export function useDrivers(orgId: string | undefined) {
  return useQuery({
    queryKey: ["logistics", "drivers", orgId],
    queryFn: () => api.listDrivers(orgId as string),
    enabled: Boolean(orgId),
  });
}

export function useRegisterVehicle() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: api.registerVehicle,
    onSuccess: (vehicle) => {
      queryClient.invalidateQueries({ queryKey: ["logistics", "vehicles", vehicle.org_id] });
    },
  });
}

export function useRegisterDriver() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: api.registerDriver,
    onSuccess: (driver) => {
      queryClient.invalidateQueries({ queryKey: ["logistics", "drivers", driver.org_id] });
    },
  });
}

export function useShipments() {
  return useQuery({
    queryKey: ["logistics", "shipments"],
    queryFn: api.listShipments,
  });
}

// There is no GET /shipments/:id on the backend, only the list route and
// /track. Rather than inventing an endpoint the backend doesn't have, the
// detail page reads the record out of the already-fetched list query.
export function useShipment(id: string | undefined) {
  const { data, ...rest } = useShipments();
  return { ...rest, data: data?.find((s) => s.id === id) };
}

export function useShipmentTrack(shipmentId: string | undefined) {
  return useQuery({
    queryKey: ["logistics", "shipments", shipmentId, "track"],
    queryFn: () => api.trackShipment(shipmentId as string),
    enabled: Boolean(shipmentId),
  });
}

function useShipmentMutation<TArgs extends unknown[]>(fn: (...args: TArgs) => Promise<unknown>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (args: TArgs) => fn(...args),
    onSuccess: () => {
      // Shipment state transitions are infrequent, manual actions, not a
      // high-frequency stream, so a broad invalidate (list + whichever
      // detail/track queries are mounted) is simpler and safe here, unlike
      // the escrow-release path which needs surgical cache updates.
      queryClient.invalidateQueries({ queryKey: ["logistics", "shipments"] });
    },
  });
}

export function useRequestShipment() {
  return useShipmentMutation<[api.RequestShipmentPayload]>(api.requestShipment);
}

export function useAssignShipment() {
  return useShipmentMutation<[string, api.AssignShipmentPayload]>(api.assignShipment);
}

export function useMarkPickedUp() {
  return useShipmentMutation<[string, number, number]>(api.markPickedUp);
}

export function useMarkInTransit() {
  return useShipmentMutation<[string]>(api.markInTransit);
}

export function useMarkDelivered() {
  return useShipmentMutation<[string, number, number]>(api.markDelivered);
}

export function useConfirmShipment() {
  return useShipmentMutation<[string]>(api.confirmShipment);
}

export function useMarkFailed() {
  return useShipmentMutation<[string, string]>(api.markFailed);
}
