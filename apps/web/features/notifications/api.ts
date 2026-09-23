import { api } from "@/lib/api/client";
import type { AppNotification, NotificationsResponse } from "@/lib/api/types";

export const notificationsApi = {
  list: () => api.get<NotificationsResponse>("/notifications"),
  markRead: (id: string) => api.post<AppNotification>(`/notifications/${id}/read`),
  markUnread: (id: string) => api.post<AppNotification>(`/notifications/${id}/unread`),
  /** Leave the inbox for good (the server keeps a tombstone so reminders aren't raised again). */
  dismiss: (id: string) => api.delete<{ dismissed: boolean }>(`/notifications/${id}`),
  markAllRead: () => api.post<{ marked: number }>("/notifications/read-all"),
};
