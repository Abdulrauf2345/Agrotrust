import { apiRequest } from "@/lib/api/client";
import type { Farm } from "@/types/api";

export function listMyFarms(): Promise<Farm[]> {
  return apiRequest<Farm[]>("/api/v1/farms");
}

export function getFarm(id: string): Promise<Farm> {
  return apiRequest<Farm>(`/api/v1/farms/${id}`);
}

export interface CreateFarmPayload {
  name: string;
  state: string;
  lga: string;
  size_hectares: number;
  lat: number;
  lon: number;
}

export function createFarm(payload: CreateFarmPayload): Promise<Farm> {
  return apiRequest<Farm>("/api/v1/farms", { method: "POST", body: payload });
}

export function requestVerification(id: string): Promise<Farm> {
  return apiRequest<Farm>(`/api/v1/farms/${id}/request-verification`, { method: "POST" });
}
