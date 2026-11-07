import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as api from "./api";
import type { Order } from "@/types/api";

export function useMyOrders(role: "buyer" | "seller", state?: string) {
  return useQuery({ queryKey: ["orders", role, state], queryFn: () => api.listMyOrders(role, state) });
}

export function useOrder(id: string | undefined) {
  return useQuery({
    queryKey: ["orders", id],
    queryFn: () => api.getOrder(id as string),
    enabled: !!id,
  });
}

export function useEscrow(orderId: string | undefined) {
  return useQuery({
    queryKey: ["escrow", orderId],
    queryFn: () => api.getEscrow(orderId as string),
    enabled: !!orderId,
  });
}

// Every order-state transition invalidates both the order and its escrow
// snapshot, since several transitions (fund, release) move both at once.
function useInvalidateOrder(orderId: string) {
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({ queryKey: ["orders", orderId] });
    void queryClient.invalidateQueries({ queryKey: ["escrow", orderId] });
    void queryClient.invalidateQueries({ queryKey: ["orders", "buyer"] });
    void queryClient.invalidateQueries({ queryKey: ["orders", "seller"] });
  };
}

export function useConfirmOrder(orderId: string) {
  const invalidate = useInvalidateOrder(orderId);
  return useMutation<Order, Error, void>({
    mutationFn: () => api.confirmOrder(orderId),
    onSuccess: invalidate,
  });
}

export function useFundOrder(orderId: string) {
  const invalidate = useInvalidateOrder(orderId);
  return useMutation<Order, Error, void>({
    mutationFn: () => api.fundOrder(orderId),
    onSuccess: invalidate,
  });
}

export function useReleaseOrder(orderId: string) {
  const invalidate = useInvalidateOrder(orderId);
  return useMutation<Order, Error, void>({
    mutationFn: () => api.releaseOrder(orderId, crypto.randomUUID()),
    onSuccess: invalidate,
  });
}

export function usePrepareOrder(orderId: string) {
  const invalidate = useInvalidateOrder(orderId);
  return useMutation<Order, Error, void>({
    mutationFn: () => api.prepareOrder(orderId),
    onSuccess: invalidate,
  });
}

export function useDispatchOrder(orderId: string) {
  const invalidate = useInvalidateOrder(orderId);
  return useMutation<Order, Error, void>({
    mutationFn: () => api.dispatchOrder(orderId),
    onSuccess: invalidate,
  });
}

export function useMarkDelivered(orderId: string) {
  const invalidate = useInvalidateOrder(orderId);
  return useMutation<Order, Error, string>({
    mutationFn: (deliveredQuantity) => api.markDelivered(orderId, deliveredQuantity),
    onSuccess: invalidate,
  });
}

export function useInspectOrder(orderId: string) {
  const invalidate = useInvalidateOrder(orderId);
  return useMutation<Order, Error, { acceptedQuantity: string; qualityResult?: string }>({
    mutationFn: ({ acceptedQuantity, qualityResult }) => api.inspectOrder(orderId, acceptedQuantity, qualityResult),
    onSuccess: invalidate,
  });
}

export function useCancelOrder(orderId: string) {
  const invalidate = useInvalidateOrder(orderId);
  return useMutation<Order, Error, string | undefined>({
    mutationFn: (reason) => api.cancelOrder(orderId, reason),
    onSuccess: invalidate,
  });
}

export function useOpenDispute(orderId: string) {
  const invalidate = useInvalidateOrder(orderId);
  return useMutation<unknown, Error, string>({
    mutationFn: (reason) => api.openDispute(orderId, reason),
    onSuccess: invalidate,
  });
}
