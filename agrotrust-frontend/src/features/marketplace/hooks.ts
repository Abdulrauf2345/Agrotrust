import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as api from "./api";
import type { ListingSearchParams } from "./api";

export function useListingSearch(params: ListingSearchParams) {
  return useQuery({
    queryKey: ["listings", "search", params],
    queryFn: () => api.searchListings(params),
    placeholderData: (previous) => previous,
  });
}

export function useListing(id: string | undefined) {
  return useQuery({
    queryKey: ["listings", id],
    queryFn: () => api.getListing(id as string),
    enabled: !!id,
  });
}

export function useCrops() {
  return useQuery({ queryKey: ["crops"], queryFn: api.listCrops, staleTime: Infinity });
}

export function useCreateListing() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: api.createListing,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["listings"] });
    },
  });
}
