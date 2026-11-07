import { apiRequest } from "@/lib/api/client";
import type { EscrowSnapshot, Order } from "@/types/api";

export function createOrder(listingId: string, quantity: string, deliveryAddress?: string): Promise<Order> {
  return apiRequest<Order>("/api/v1/orders", {
    method: "POST",
    body: { listing_id: listingId, quantity, delivery_address: deliveryAddress },
  });
}

export function listMyOrders(role: "buyer" | "seller", state?: string): Promise<Order[]> {
  return apiRequest<Order[]>("/api/v1/orders", { query: { role, state } });
}

export function getOrder(id: string): Promise<Order> {
  return apiRequest<Order>(`/api/v1/orders/${id}`);
}

export function getEscrow(orderId: string): Promise<EscrowSnapshot> {
  return apiRequest<EscrowSnapshot>(`/api/v1/orders/${orderId}/escrow`);
}

export function confirmOrder(id: string): Promise<Order> {
  return apiRequest<Order>(`/api/v1/orders/${id}/confirm`, { method: "POST" });
}

export function fundOrder(id: string): Promise<Order> {
  return apiRequest<Order>(`/api/v1/orders/${id}/fund`, { method: "POST" });
}

export function releaseOrder(id: string, idempotencyKey: string): Promise<Order> {
  return apiRequest<Order>(`/api/v1/orders/${id}/release`, { method: "POST", idempotencyKey });
}

export function prepareOrder(id: string): Promise<Order> {
  return apiRequest<Order>(`/api/v1/orders/${id}/prepare`, { method: "POST" });
}

export function dispatchOrder(id: string): Promise<Order> {
  return apiRequest<Order>(`/api/v1/orders/${id}/dispatch`, { method: "POST" });
}

export function markDelivered(id: string, deliveredQuantity: string): Promise<Order> {
  return apiRequest<Order>(`/api/v1/orders/${id}/deliver`, {
    method: "POST",
    body: { delivered_quantity: deliveredQuantity },
  });
}

export function inspectOrder(id: string, acceptedQuantity: string, qualityResult?: string): Promise<Order> {
  return apiRequest<Order>(`/api/v1/orders/${id}/inspect`, {
    method: "POST",
    body: { accepted_quantity: acceptedQuantity, quality_result: qualityResult },
  });
}

export function cancelOrder(id: string, reason?: string): Promise<Order> {
  return apiRequest<Order>(`/api/v1/orders/${id}/cancel`, { method: "POST", body: { reason } });
}

export function openDispute(id: string, reason: string): Promise<unknown> {
  return apiRequest(`/api/v1/orders/${id}/disputes`, { method: "POST", body: { reason } });
}
