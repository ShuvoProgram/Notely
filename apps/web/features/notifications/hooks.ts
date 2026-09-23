"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import * as React from "react";

import { notificationsApi } from "@/features/notifications/api";
import type { NotificationsResponse } from "@/lib/api/types";
import { playSfx } from "@/lib/sfx/player";

// Ids already shown once in this page session. Seeded on the first response so a reload is
// silent; only notifications that arrive *afterwards* (reminders, shares, sync results) chime.
const seen = new Set<string>();
let seeded = false;

export const notificationKeys = { all: ["notifications"] as const };

/** The inbox, polled quietly so reminders show up without a refresh. */
export function useNotifications(enabled = true) {
  const query = useQuery({
    queryKey: notificationKeys.all,
    queryFn: notificationsApi.list,
    enabled,
    refetchInterval: 60_000,
    refetchOnWindowFocus: true,
    staleTime: 15_000,
  });
  const items = query.data?.items;
  React.useEffect(() => {
    if (!items) return;
    let fresh = false;
    for (const n of items) {
      if (!seen.has(n.id)) {
        seen.add(n.id);
        if (seeded && !n.read_at) fresh = true;
      }
    }
    seeded = true;
    if (fresh) playSfx("notification");
  }, [items]);
  return query;
}

export function useNotificationActions() {
  const queryClient = useQueryClient();
  const patch = (fn: (prev: NotificationsResponse) => NotificationsResponse) =>
    queryClient.setQueryData<NotificationsResponse>(notificationKeys.all, (prev) => (prev ? fn(prev) : prev));
  const markRead = useMutation({
    mutationFn: notificationsApi.markRead,
    onMutate: (id) => {
      const now = new Date().toISOString();
      patch((prev) => ({
        unread: Math.max(0, prev.unread - (prev.items.find((n) => n.id === id && !n.read_at) ? 1 : 0)),
        items: prev.items.map((n) => (n.id === id && !n.read_at ? { ...n, read_at: now } : n)),
      }));
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: notificationKeys.all }),
  });
  const markAllRead = useMutation({
    mutationFn: notificationsApi.markAllRead,
    onMutate: () => {
      const now = new Date().toISOString();
      patch((prev) => ({ unread: 0, items: prev.items.map((n) => (n.read_at ? n : { ...n, read_at: now })) }));
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: notificationKeys.all }),
  });
  const markUnread = useMutation({
    mutationFn: notificationsApi.markUnread,
    onMutate: (id) =>
      patch((prev) => ({
        unread: prev.unread + (prev.items.find((n) => n.id === id && n.read_at) ? 1 : 0),
        items: prev.items.map((n) => (n.id === id ? { ...n, read_at: null } : n)),
      })),
    onSettled: () => queryClient.invalidateQueries({ queryKey: notificationKeys.all }),
  });
  const dismiss = useMutation({
    mutationFn: notificationsApi.dismiss,
    onMutate: (id) =>
      patch((prev) => ({
        unread: Math.max(0, prev.unread - (prev.items.find((n) => n.id === id && !n.read_at) ? 1 : 0)),
        items: prev.items.filter((n) => n.id !== id),
      })),
    onSettled: () => queryClient.invalidateQueries({ queryKey: notificationKeys.all }),
  });
  return { markRead, markUnread, dismiss, markAllRead };
}
