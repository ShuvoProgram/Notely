"use client";

import { Bell, CheckCheck } from "@/components/icons";
import Link from "next/link";
import * as React from "react";

import { EmptyState } from "@/components/layout/empty-state";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useNotificationActions, useNotifications } from "@/features/notifications/hooks";
import { NotificationList } from "@/features/notifications/components/notification-list";


/** Header bell: unread badge and the inbox (a stacking notification list) in a popover. */
export function NotificationBell() {
  const [open, setOpen] = React.useState(false);
  const inbox = useNotifications();
  const { markRead, markUnread, dismiss, markAllRead } = useNotificationActions();
  const unread = inbox.data?.unread ?? 0;
  const items = inbox.data?.items ?? [];

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <Tooltip>
        <TooltipTrigger asChild>
          <PopoverTrigger asChild>
            <Button variant="ghost" size="icon" className="relative" aria-label={unread ? `Notifications, ${unread} unread` : "Notifications"}>
              <Bell aria-hidden />
              {unread ? (
                <span aria-hidden className="absolute -right-0.5 -top-0.5 grid h-4 min-w-4 place-items-center rounded-full bg-ai px-1 text-[11px] font-semibold leading-none text-primary-foreground ring-1 ring-background">
                  {unread > 9 ? "9+" : unread}
                </span>
              ) : null}
            </Button>
          </PopoverTrigger>
        </TooltipTrigger>
        <TooltipContent>Notifications</TooltipContent>
      </Tooltip>
      <PopoverContent align="end" sideOffset={8} className="w-[min(24rem,calc(100vw-1.5rem))] p-0">
        <header className="flex items-center justify-between border-b border-glass-border px-3 py-2">
          <p className="text-sm font-semibold">
            Notifications
            {unread ? <span className="ml-2 text-xs font-normal text-muted-foreground">{unread} unread</span> : null}
          </p>
          <Button variant="ghost" size="sm" disabled={!unread || markAllRead.isPending} onClick={() => markAllRead.mutate()} className="h-7 text-xs">
            <CheckCheck aria-hidden /> Mark all read
          </Button>
        </header>
        <div className="scrollbar-thin max-h-[min(65vh,30rem)] overflow-y-auto overscroll-contain">
          {inbox.isPending ? (
            <div className="space-y-2 p-3" aria-busy>
              {Array.from({ length: 3 }).map((_, i) => (
                <div key={i} className="shimmer h-12 rounded-lg" />
              ))}
            </div>
          ) : inbox.isError ? (
            <p role="alert" className="p-4 text-sm text-destructive">
              Couldn’t load notifications.
            </p>
          ) : items.length ? (
            <NotificationList
              items={items}
              onOpen={(n) => {
                if (!n.read_at) markRead.mutate(n.id);
                if (n.href) setOpen(false);
              }}
              onToggleRead={(n) => (n.read_at ? markUnread.mutate(n.id) : markRead.mutate(n.id))}
              onDismiss={(n) => dismiss.mutate(n.id)}
            />
          ) : (
            <EmptyState icon={Bell} className="py-8" title="You’re all caught up" description="Task reminders and integration updates show up here." />
          )}
        </div>
        <footer className="border-t border-glass-border px-3 py-2 text-right">
          <Link href="/app/settings/notifications" onClick={() => setOpen(false)} className="text-xs text-muted-foreground underline-offset-2 hover:text-foreground hover:underline">
            Notification settings
          </Link>
        </footer>
      </PopoverContent>
    </Popover>
  );
}
