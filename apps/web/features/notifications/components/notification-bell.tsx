"use client";

import { AlertTriangle, Bell, CalendarCheck, CalendarX, Check, CheckCheck, Clock, KeyRound, Plug, Unplug, type LucideIcon } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { EmptyState } from "@/components/layout/empty-state";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useNotificationActions, useNotifications } from "@/features/notifications/hooks";
import type { AppNotification, NotificationKind } from "@/lib/api/types";
import { cn } from "@/lib/utils";

const KIND: Record<NotificationKind, { icon: LucideIcon; tone: string }> = {
  task_due_soon: { icon: Clock, tone: "text-info" },
  task_overdue: { icon: AlertTriangle, tone: "text-warning" },
  task_completed: { icon: Check, tone: "text-success" },
  integration_connected: { icon: Plug, tone: "text-success" },
  integration_disconnected: { icon: Unplug, tone: "text-muted-foreground" },
  integration_auth_required: { icon: KeyRound, tone: "text-warning" },
  calendar_synced: { icon: CalendarCheck, tone: "text-success" },
  calendar_sync_failed: { icon: CalendarX, tone: "text-destructive" },
};

export function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.round(diff / 60_000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.round(h / 24);
  return d < 7 ? `${d}d ago` : new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

/** Header bell: unread badge, glass popover inbox, per-item and bulk mark-as-read. */
export function NotificationBell() {
  const [open, setOpen] = React.useState(false);
  const inbox = useNotifications();
  const { markRead, markAllRead } = useNotificationActions();
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
                <span aria-hidden className="absolute -right-0.5 -top-0.5 grid h-4 min-w-4 place-items-center rounded-full bg-ai px-1 text-[10px] font-semibold leading-none text-primary-foreground ring-1 ring-background">
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
        <div className="scrollbar-thin max-h-[min(60vh,26rem)] overflow-y-auto" role="list" aria-label="Notifications">
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
            items.map((n) => <Row key={n.id} n={n} onOpen={() => setOpen(false)} onRead={() => markRead.mutate(n.id)} />)
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

function Row({ n, onOpen, onRead }: { n: AppNotification; onOpen: () => void; onRead: () => void }) {
  const meta = KIND[n.kind] ?? { icon: Bell, tone: "text-muted-foreground" };
  const Icon = meta.icon;
  const unread = !n.read_at;
  const body = (
    <>
      <span className={cn("mt-0.5 grid size-7 shrink-0 place-items-center rounded-lg bg-muted/60", meta.tone)}>
        <Icon className="size-3.5" aria-hidden />
      </span>
      <span className="min-w-0 flex-1">
        <span className={cn("block truncate text-sm", unread ? "font-medium" : "text-foreground/80")}>{n.title}</span>
        {n.body ? <span className="block truncate text-xs text-muted-foreground">{n.body}</span> : null}
        <time dateTime={n.created_at} className="mt-0.5 block text-[11px] text-muted-foreground/70">
          {relativeTime(n.created_at)}
        </time>
      </span>
      {unread ? <span aria-label="Unread" className="mt-2 size-1.5 shrink-0 rounded-full bg-ai" /> : null}
    </>
  );
  const className = cn("group flex w-full items-start gap-3 px-3 py-2.5 text-left outline-none transition-colors hover:bg-muted/40 focus-visible:bg-muted/40", unread && "bg-ai-soft/30");
  return (
    <div role="listitem" className="relative">
      {n.href ? (
        <Link
          href={n.href}
          className={className}
          onClick={() => {
            if (unread) onRead();
            onOpen();
          }}
        >
          {body}
        </Link>
      ) : (
        <button type="button" className={className} onClick={() => unread && onRead()}>
          {body}
        </button>
      )}
      {unread ? (
        <Button variant="ghost" size="icon-xs" aria-label="Mark as read" onClick={onRead} className="absolute right-2 top-2 opacity-0 group-hover:opacity-100 focus-visible:opacity-100">
          <Check aria-hidden />
        </Button>
      ) : null}
    </div>
  );
}
