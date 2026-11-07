import { apiRequest } from "@/lib/api/client";
import type { DeliveryEvent, Driver, Shipment, Vehicle } from "@/types/api";

export interface RegisterVehiclePayload {
  org_id: string;
  plate: string;
  vehicle_type: string;
  capacity_kg: number;
}

export function registerVehicle(payload: RegisterVehiclePayload): Promise<Vehicle> {
  return apiRequest<Vehicle>("/api/v1/vehicles", { method: "POST", body: payload });
}

export function listVehicles(orgId: string): Promise<Vehicle[]> {
  return apiRequest<Vehicle[]>("/api/v1/vehicles", { query: { org_id: orgId } });
}

export interface RegisterDriverPayload {
  org_id: string;
  name: string;
  phone: string;
}

export function registerDriver(payload: RegisterDriverPayload): Promise<Driver> {
  return apiRequest<Driver>("/api/v1/drivers", { method: "POST", body: payload });
}

export function listDrivers(orgId: string): Promise<Driver[]> {
  return apiRequest<Driver[]>("/api/v1/drivers", { query: { org_id: orgId } });
}

export function listShipments(): Promise<Shipment[]> {
  return apiRequest<Shipment[]>("/api/v1/shipments");
}

export interface RequestShipmentPayload {
  order_id: string;
  pickup_lat: number;
  pickup_lon: number;
  dropoff_lat: number;
  dropoff_lon: number;
}

export function requestShipment(payload: RequestShipmentPayload): Promise<Shipment> {
  return apiRequest<Shipment>("/api/v1/shipments", { method: "POST", body: payload });
}

export interface AssignShipmentPayload {
  driver_id: string;
  vehicle_id: string;
  provider_org_id: string;
}

export function assignShipment(id: string, payload: AssignShipmentPayload): Promise<Shipment> {
  return apiRequest<Shipment>(`/api/v1/shipments/${id}/assign`, { method: "POST", body: payload });
}

export function markPickedUp(id: string, lat: number, lon: number): Promise<Shipment> {
  return apiRequest<Shipment>(`/api/v1/shipments/${id}/picked-up`, { method: "POST", body: { lat, lon } });
}

export function markInTransit(id: string): Promise<Shipment> {
  return apiRequest<Shipment>(`/api/v1/shipments/${id}/in-transit`, { method: "POST" });
}

export function markDelivered(id: string, lat: number, lon: number): Promise<Shipment> {
  return apiRequest<Shipment>(`/api/v1/shipments/${id}/delivered`, { method: "POST", body: { lat, lon } });
}

export function confirmShipment(id: string): Promise<Shipment> {
  return apiRequest<Shipment>(`/api/v1/shipments/${id}/confirm`, { method: "POST" });
}

export function markFailed(id: string, reason: string): Promise<Shipment> {
  return apiRequest<Shipment>(`/api/v1/shipments/${id}/failed`, { method: "POST", body: { reason } });
}

export function trackShipment(id: string): Promise<DeliveryEvent[]> {
  return apiRequest<DeliveryEvent[]>(`/api/v1/shipments/${id}/track`);
}
