import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as api from "./api";

export function useNotifications() {
  return useQuery({ queryKey: ["notifications"], queryFn: api.listNotifications });
}

export function useMarkRead() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: api.markRead,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["notifications"] });
    },
  });
}
