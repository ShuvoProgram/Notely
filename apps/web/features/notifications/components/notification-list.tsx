"use client";

import Link from "next/link";
import * as React from "react";

import {
  AlertTriangle,
  Bell,
  BellRing,
  CalendarCheck,
  CalendarX,
  Check,
  ChevronDown,
  Circle,
  Clock,
  KeyRound,
  Plug,
  Unplug,
  Users,
  Workflow,
  X,
  type IconComponent,
} from "@/components/icons";
import type { AppNotification, NotificationKind } from "@/lib/api/types";
import { cn } from "@/lib/utils";

/*
 * Notification list with stacking. Consecutive notifications of the same kind (five automation
 * runs, three reminders) collapse into one stack: the newest card on top, up to two peeking out
 * behind it and a "+N" count. Activating a stack unfolds it in place; everything else is a plain
 * card. Unfolding is a short spring (and instant under prefers-reduced-motion), never a
 * distraction; stacks only form when they reduce noise (2+ of a kind in a row).
 *
 * Each card opens its target (marking it read), and has quiet actions for read/unread and dismiss
 * that appear on hover or focus, and are always shown on touch screens.
 */

export const KIND: Record<NotificationKind, { icon: IconComponent; tone: string; label: string }> = {
  task_due_soon: { icon: Clock, tone: "text-info", label: "Task reminders" },
  task_overdue: { icon: AlertTriangle, tone: "text-warning", label: "Overdue tasks" },
  task_completed: { icon: Check, tone: "text-success", label: "Completed tasks" },
  integration_connected: { icon: Plug, tone: "text-success", label: "Connections" },
  integration_disconnected: { icon: Unplug, tone: "text-muted-foreground", label: "Disconnections" },
  integration_auth_required: { icon: KeyRound, tone: "text-warning", label: "Sign-in needed" },
  calendar_synced: { icon: CalendarCheck, tone: "text-success", label: "Calendar sync" },
  calendar_sync_failed: { icon: CalendarX, tone: "text-destructive", label: "Calendar sync problems" },
  note_reminder: { icon: BellRing, tone: "text-ai", label: "Note reminders" },
  note_shared: { icon: Users, tone: "text-info", label: "Shared with you" },
  automation: { icon: Workflow, tone: "text-ai", label: "Automation runs" },
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

interface Group {
  key: string;
  kind: NotificationKind;
  items: AppNotification[];
}

/** Runs of the same kind, in inbox order. */
function groupRuns(items: AppNotification[]): Group[] {
  const out: Group[] = [];
  for (const n of items) {
    const last = out[out.length - 1];
    if (last && last.kind === n.kind) last.items.push(n);
    else out.push({ key: n.id, kind: n.kind, items: [n] });
  }
  return out;
}

export interface NotificationHandlers {
  onOpen: (n: AppNotification) => void;
  onToggleRead: (n: AppNotification) => void;
  onDismiss: (n: AppNotification) => void;
}

export function NotificationList({ items, ...handlers }: { items: AppNotification[] } & NotificationHandlers) {
  const groups = React.useMemo(() => groupRuns(items), [items]);
  const [open, setOpen] = React.useState<Set<string>>(() => new Set());
  const toggle = (key: string) =>
    setOpen((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });

  return (
    <ul role="list" aria-label="Notifications" className="flex flex-col gap-2 p-2">
      {groups.map((g) =>
        g.items.length > 1 && !open.has(g.key) ? (
          <Stack key={g.key} group={g} onExpand={() => toggle(g.key)} {...handlers} />
        ) : (
          <React.Fragment key={g.key}>
            {g.items.length > 1 ? (
              <li className="flex items-center justify-between px-1 pt-1">
                <span className="text-xs font-medium text-muted-foreground">
                  {KIND[g.kind]?.label ?? "Notifications"} · {g.items.length}
                </span>
                <button
                  type="button"
                  onClick={() => toggle(g.key)}
                  className="flex cursor-pointer items-center gap-1 rounded-md px-1.5 py-0.5 text-xs font-medium text-muted-foreground outline-none hover:bg-accent hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring"
                >
                  Show less <ChevronDown className="size-3.5 rotate-180" aria-hidden />
                </button>
              </li>
            ) : null}
            {g.items.map((n, i) => (
              <li key={n.id} className="motion-safe:animate-[notely-fade-up_260ms_var(--ease-liquid)_both]" style={{ animationDelay: g.items.length > 1 ? `${i * 40}ms` : undefined }}>
                <Card n={n} {...handlers} />
              </li>
            ))}
          </React.Fragment>
        ),
      )}
    </ul>
  );
}

/** A collapsed run: the newest card on top, two sheets peeking below, activate to unfold. */
function Stack({ group, onExpand, ...handlers }: { group: Group; onExpand: () => void } & NotificationHandlers) {
  const [top, ...rest] = group.items;
  if (!top) return null;
  const unread = group.items.filter((n) => !n.read_at).length;
  const peeks = Math.min(2, rest.length);
  return (
    <li className="group/stack relative isolate" style={{ paddingBottom: peeks * 6 }}>
      {/* peeking sheets (decorative) */}
      {Array.from({ length: peeks }, (_, i) => (
        <span
          key={i}
          aria-hidden
          className="absolute inset-x-0 top-0 rounded-xl border border-glass-border bg-card transition-transform duration-300 ease-liquid group-hover/stack:translate-y-0.5"
          style={{ bottom: 0, transform: `translateY(${(i + 1) * 6}px) scale(${1 - (i + 1) * 0.04})`, zIndex: -1 - i, opacity: 1 - (i + 1) * 0.25 }}
        />
      ))}
      <Card n={top} {...handlers} />
      <button
        type="button"
        onClick={onExpand}
        aria-expanded={false}
        aria-label={`Show ${rest.length} more ${KIND[group.kind]?.label.toLowerCase() ?? "notifications"}${unread > 1 ? `, ${unread} unread` : ""}`}
        className="absolute bottom-[calc(var(--p)+0.375rem)] right-2 flex cursor-pointer items-center gap-1 rounded-full bg-field px-2 py-0.5 text-[11px] font-bold text-muted-foreground ring-1 ring-glass-border outline-none transition-colors hover:bg-accent hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring"
        style={{ ["--p" as string]: `${peeks * 6}px` }}
      >
        +{rest.length} <ChevronDown className="size-3" aria-hidden />
      </button>
    </li>
  );
}

function Card({ n, onOpen, onToggleRead, onDismiss }: { n: AppNotification } & NotificationHandlers) {
  const meta = KIND[n.kind] ?? { icon: Bell, tone: "text-muted-foreground", label: "" };
  const Icon = meta.icon;
  const unread = !n.read_at;

  const content = (
    <>
      <span className={cn("mt-0.5 grid size-8 shrink-0 place-items-center rounded-lg bg-field ring-1 ring-glass-border", meta.tone)}>
        <Icon className="size-4" aria-hidden />
      </span>
      <span className="min-w-0 flex-1 pr-14">
        <span className={cn("line-clamp-1 text-sm", unread ? "font-bold" : "font-medium")}>{n.title}</span>
        {n.body ? <span className="mt-0.5 line-clamp-2 text-xs text-muted-foreground">{n.body}</span> : null}
        <time dateTime={n.created_at} className="mt-1 block text-[11px] text-tertiary">
          {relativeTime(n.created_at)}
        </time>
      </span>
    </>
  );

  const surface = cn(
    "flex w-full cursor-pointer items-start gap-3 rounded-xl border p-3 text-left outline-none transition-[background-color,border-color,transform] duration-200 ease-liquid focus-visible:ring-2 focus-visible:ring-ring active:scale-[0.99]",
    unread ? "border-ai/30 bg-card hover:border-ai/50" : "border-glass-border bg-card/60 hover:bg-card",
  );

  return (
    <div className="group/card relative">
      {n.href ? (
        <Link href={n.href} className={surface} onClick={() => onOpen(n)}>
          {content}
        </Link>
      ) : (
        <button type="button" className={surface} onClick={() => onOpen(n)}>
          {content}
        </button>
      )}
      {unread ? <span aria-hidden className="absolute right-3 top-3.5 size-2 rounded-full bg-ai transition-opacity group-hover/card:opacity-0 group-focus-within/card:opacity-0" /> : null}
      {unread ? <span className="sr-only">Unread</span> : null}
      {/* Quiet actions: on hover/focus with a mouse, always on touch screens. */}
      <div className="absolute right-1.5 top-1.5 flex gap-0.5 opacity-0 transition-opacity group-hover/card:opacity-100 group-focus-within/card:opacity-100 [@media(hover:none)]:opacity-100">
        <IconAction label={unread ? "Mark as read" : "Mark as unread"} onClick={() => onToggleRead(n)}>
          {unread ? <Check aria-hidden /> : <Circle aria-hidden />}
        </IconAction>
        <IconAction label="Dismiss" onClick={() => onDismiss(n)}>
          <X aria-hidden />
        </IconAction>
      </div>
    </div>
  );
}

function IconAction({ label, onClick, children }: { label: string; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={onClick}
      className="grid size-7 cursor-pointer place-items-center rounded-lg text-muted-foreground outline-none transition-colors hover:bg-accent hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring active:scale-95 [&_svg]:size-3.5"
    >
      {children}
    </button>
  );
}
