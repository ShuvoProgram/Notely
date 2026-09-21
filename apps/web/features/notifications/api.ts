import { api } from "@/lib/api/client";
import type { AppNotification, NotificationsResponse } from "@/lib/api/types";

export const notificationsApi = {
  list: () => api.get<NotificationsResponse>("/notifications"),
  markRead: (id: string) => api.post<AppNotification>(`/notifications/${id}/read`),
  markAllRead: () => api.post<{ marked: number }>("/notifications/read-all"),
};
