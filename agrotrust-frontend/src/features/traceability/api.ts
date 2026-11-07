import { apiRequest } from "@/lib/api/client";
import type { CustodyEvent, Lot, QualityInspection, WeighingRecord } from "@/types/api";

export interface CreateLotPayload {
  farm_id: string;
  crop_id: string;
  quantity: string;
  unit: string;
  harvest_date: string;
  quality_grade?: string;
}

export function createLot(payload: CreateLotPayload): Promise<Lot> {
  return apiRequest<Lot>("/api/v1/lots", { method: "POST", body: payload });
}

export function listLots(farmId?: string): Promise<Lot[]> {
  return apiRequest<Lot[]>("/api/v1/lots", { query: { farm_id: farmId } });
}

export function getLot(id: string): Promise<Lot> {
  return apiRequest<Lot>(`/api/v1/lots/${id}`);
}

export function getLotByCode(code: string): Promise<Lot> {
  return apiRequest<Lot>(`/api/v1/lots/by-code/${code}`);
}

export interface LotHistory {
  events: CustodyEvent[];
  chain_valid: boolean;
  first_tampered_id: number | null;
}

export function lotHistory(id: string): Promise<LotHistory> {
  return apiRequest<LotHistory>(`/api/v1/lots/${id}/history`);
}

export interface RecordWeighingPayload {
  gross_kg: number;
  tare_kg: number;
  warehouse_id?: string;
}

export function recordWeighing(lotId: string, payload: RecordWeighingPayload): Promise<WeighingRecord> {
  return apiRequest<WeighingRecord>(`/api/v1/lots/${lotId}/weighing`, { method: "POST", body: payload });
}

export interface RecordInspectionPayload {
  grade: string;
  passed: boolean;
  moisture_pct?: number;
  defects_pct?: number;
  notes?: string;
}

export function recordInspection(lotId: string, payload: RecordInspectionPayload): Promise<QualityInspection> {
  return apiRequest<QualityInspection>(`/api/v1/lots/${lotId}/inspection`, { method: "POST", body: payload });
}
