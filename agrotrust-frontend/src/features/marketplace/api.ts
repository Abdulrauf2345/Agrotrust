import { apiRequest } from "@/lib/api/client";
import type { Listing, ListingSearchResult } from "@/types/api";

export type ListingSearchParams = {
  q?: string;
  crop_id?: string;
  state?: string;
  lga?: string;
  sort?: "newest" | "price_asc" | "price_desc" | "quantity";
  limit?: number;
  offset?: number;
};

export function searchListings(params: ListingSearchParams = {}): Promise<ListingSearchResult> {
  return apiRequest<ListingSearchResult>("/api/v1/listings", { query: params });
}

export function getListing(id: string): Promise<Listing> {
  return apiRequest<Listing>(`/api/v1/listings/${id}`);
}

export interface CreateListingPayload {
  crop_id: string;
  title: string;
  description?: string;
  quantity: string;
  unit: string;
  price: string;
  state: string;
  lga: string;
  farm_id?: string;
}

export function createListing(payload: CreateListingPayload): Promise<Listing> {
  return apiRequest<Listing>("/api/v1/listings", { method: "POST", body: payload });
}

export interface Crop {
  id: string;
  code: string;
  name: string;
  default_unit: string;
}

export function listCrops(): Promise<Crop[]> {
  return apiRequest<Crop[]>("/api/v1/crops");
}
