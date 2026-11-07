import { apiRequest } from "@/lib/api/client";
import type { Notification } from "@/types/api";

export function listNotifications(): Promise<Notification[]> {
  return apiRequest<Notification[]>("/api/v1/notifications");
}

export function markRead(id: string): Promise<Notification> {
  return apiRequest<Notification>(`/api/v1/notifications/${id}/read`, { method: "POST" });
}
