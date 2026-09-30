"use client";

import { useQuery } from "@tanstack/react-query";
import { formatDistanceToNowStrict } from "date-fns";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import * as React from "react";

import {
  AlertTriangle,
  CheckCircle2,
  ChevronLeftIcon,
  ChevronRightIcon,
  Circle,
  CircleSlash,
  type IconComponent,
  Loader2,
  RefreshCw,
  XCircle,
} from "@/components/icons";
import { EmptyState } from "@/components/layout/empty-state";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { adminApi, adminKeys, type Permission } from "@/features/admin/api";
import { messageFor } from "@/features/auth/components/auth-form-error";
import { ApiError } from "@/lib/api/client";
import { cn } from "@/lib/utils";

// --- formatting -----------------------------------------------------------------------------------

const numberFmt = new Intl.NumberFormat();
const compactFmt = new Intl.NumberFormat(undefined, { notation: "compact", maximumFractionDigits: 1 });

export const fmt = {
  n: (v: number | null | undefined) => (v === null || v === undefined ? "—" : numberFmt.format(v)),
  compact: (v: number | null | undefined) => (v === null || v === undefined ? "—" : v >= 10_000 ? compactFmt.format(v) : numberFmt.format(v)),
  pct: (v: number | null | undefined) => (v === null || v === undefined ? "—" : `${v}%`),
  date: (v: string | null | undefined) =>
    v ? new Date(v).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" }) : "—",
  dateTime: (v: string | null | undefined) =>
    v ? new Date(v).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "—",
  ago: (v: string | null | undefined) => (v ? `${formatDistanceToNowStrict(new Date(v))} ago` : "Never"),
  ms: (v: number | null | undefined) => {
    if (v === null || v === undefined) return "—";
    if (v < 1000) return `${v} ms`;
    if (v < 60_000) return `${(v / 1000).toFixed(v < 10_000 ? 1 : 0)} s`;
    return `${Math.floor(v / 60_000)}m ${Math.round((v % 60_000) / 1000)}s`;
  },
  label: (v: string | null | undefined) => (v ? v.replace(/[._]/g, " ").replace(/^\w/, (c) => c.toUpperCase()) : "—"),
};

export function Time({ value, relative = false }: { value: string | null | undefined; relative?: boolean }) {
  if (!value) return <span className="text-muted-foreground">—</span>;
  return (
    <time dateTime={value} title={new Date(value).toLocaleString()} className="whitespace-nowrap tabular-nums">
      {relative ? fmt.ago(value) : fmt.dateTime(value)}
    </time>
  );
}

// --- session / permissions ------------------------------------------------------------------------

export function useAdminMe() {
  return useQuery({ queryKey: adminKeys.me, queryFn: adminApi.me, staleTime: 60_000 });
}

/** Hides controls the role can't use. Convenience only: the API refuses them regardless. */
export function useCan(permission: Permission): boolean {
  const me = useAdminMe();
  return Boolean(me.data?.permissions.includes(permission));
}

// --- URL state ------------------------------------------------------------------------------------

/** Filters live in the URL so a filtered view can be shared, reloaded and navigated back to. */
export function useUrlState<K extends string>(keys: readonly K[]) {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const values = Object.fromEntries(keys.map((k) => [k, params.get(k) ?? ""])) as Record<K, string>;
  const set = React.useCallback(
    (patch: Partial<Record<K | "page", string | number | null>>) => {
      const next = new URLSearchParams(params.toString());
      for (const [k, v] of Object.entries(patch)) {
        if (v === null || v === undefined || v === "") next.delete(k);
        else next.set(k, String(v));
      }
      // Any filter change goes back to the first page.
      if (!("page" in patch)) next.delete("page");
      const qs = next.toString();
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
    [params, pathname, router],
  );
  const page = Math.max(1, Number(params.get("page") ?? 1) || 1);
  return { values, set, page };
}

export function useDebounced<T>(value: T, delay = 300): T {
  const [v, setV] = React.useState(value);
  React.useEffect(() => {
    const t = setTimeout(() => setV(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return v;
}

// --- status ---------------------------------------------------------------------------------------

export type Tone = "success" | "warning" | "danger" | "neutral" | "info";

const TONE: Record<Tone, { cls: string; icon: IconComponent }> = {
  success: { cls: "border-success/30 bg-success/10 text-success", icon: CheckCircle2 },
  warning: { cls: "border-warning/35 bg-warning/10 text-warning", icon: AlertTriangle },
  danger: { cls: "border-destructive/35 bg-destructive/10 text-destructive", icon: XCircle },
  neutral: { cls: "border-glass-border bg-muted/40 text-muted-foreground", icon: Circle },
  info: { cls: "border-ai/30 bg-ai-soft text-ai", icon: Loader2 },
};

/** Status is always icon + words, never colour alone. */
export function StatusPill({ tone, children, icon, className }: { tone: Tone; children: React.ReactNode; icon?: IconComponent; className?: string }) {
  const Icon = icon ?? TONE[tone].icon;
  return (
    <span className={cn("inline-flex h-6 w-fit shrink-0 items-center gap-1 whitespace-nowrap rounded-full border px-2 text-xs font-medium", TONE[tone].cls, className)}>
      <Icon className="size-3.5" aria-hidden />
      {children}
    </span>
  );
}

export function executionTone(status: string): Tone {
  if (status === "completed" || status === "stopped") return "success";
  if (status === "failed") return "danger";
  if (status === "waiting_for_approval") return "warning";
  if (status === "running" || status === "queued") return "info";
  return "neutral";
}

export function AccountStatus({ active }: { active: boolean }) {
  return active ? <StatusPill tone="success">Active</StatusPill> : <StatusPill tone="danger" icon={CircleSlash}>Suspended</StatusPill>;
}

export function RoleBadge({ role }: { role: string }) {
  if (role === "user") return <span className="text-xs text-muted-foreground">Member</span>;
  const label = { admin: "Admin", support: "Support", viewer: "Read-only admin" }[role] ?? role;
  return (
    <span className="inline-flex h-5 items-center rounded-full border border-ai/30 bg-ai-soft px-2 text-[11px] font-semibold uppercase tracking-wide text-ai">
      {label}
    </span>
  );
}

// --- layout pieces --------------------------------------------------------------------------------

export function Section({
  title,
  description,
  actions,
  children,
  className,
  flush = false,
}: {
  title: React.ReactNode;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  /** Content runs edge to edge (tables). */
  flush?: boolean;
}) {
  return (
    <Card className={cn("min-w-0", className)}>
      <CardHeader className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <CardTitle>{title}</CardTitle>
          {description ? <CardDescription className="mt-0.5">{description}</CardDescription> : null}
        </div>
        {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
      </CardHeader>
      <CardContent className={cn(flush && "px-0")}>{children}</CardContent>
    </Card>
  );
}

export function StatCard({
  label,
  value,
  hint,
  icon: Icon,
  tone,
  href,
}: {
  label: string;
  value: React.ReactNode;
  hint?: React.ReactNode;
  icon?: IconComponent;
  tone?: "danger" | "warning" | "success";
  href?: string;
}) {
  const body = (
    <>
      <div className="flex items-center justify-between gap-2">
        <p className="truncate text-xs font-medium text-muted-foreground">{label}</p>
        {Icon ? (
          <Icon
            className={cn(
              "size-4 shrink-0",
              tone === "danger" ? "text-destructive" : tone === "warning" ? "text-warning" : tone === "success" ? "text-success" : "text-muted-foreground",
            )}
            aria-hidden
          />
        ) : null}
      </div>
      <p className="mt-1.5 text-2xl font-semibold tabular-nums tracking-tight">{value}</p>
      {hint ? <p className="mt-0.5 truncate text-xs text-muted-foreground">{hint}</p> : null}
    </>
  );
  const cls = "glass block min-w-0 rounded-2xl px-4 py-3.5";
  return href ? (
    <Link href={href} className={cn(cls, "liquid-press outline-none transition-colors hover:bg-muted/30 focus-visible:ring-2 focus-visible:ring-ring")}>
      {body}
    </Link>
  ) : (
    <div className={cls}>{body}</div>
  );
}

export function StatGrid({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div className={cn("grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-4", className)}>{children}</div>;
}

// --- query states ---------------------------------------------------------------------------------

export function LoadingBlock({ rows = 4, className }: { rows?: number; className?: string }) {
  return (
    <div className={cn("space-y-2", className)} aria-busy="true" aria-label="Loading">
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className="h-10 w-full" />
      ))}
    </div>
  );
}

export function StatsSkeleton({ count = 4 }: { count?: number }) {
  return (
    <StatGrid>
      {Array.from({ length: count }).map((_, i) => (
        <Skeleton key={i} className="h-[92px] rounded-2xl" />
      ))}
    </StatGrid>
  );
}

export function ErrorBlock({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const reauth = error instanceof ApiError && error.code === "ADMIN_REAUTH_REQUIRED";
  return (
    <EmptyState
      icon={AlertTriangle}
      tone="danger"
      title={reauth ? "Please sign in again" : "Couldn't load this"}
      description={messageFor(error)}
      action={
        reauth ? (
          <Button asChild>
            <Link href="/admin/reauth">Sign in again</Link>
          </Button>
        ) : onRetry ? (
          <Button variant="outline" onClick={onRetry}>
            <RefreshCw aria-hidden /> Try again
          </Button>
        ) : null
      }
    />
  );
}

// --- controls -------------------------------------------------------------------------------------

export const RANGES = [7, 30, 90] as const;

/** Time window for a report. A radio group, so arrow keys move between options. */
export function RangePicker({ value, onChange }: { value: number; onChange: (days: number) => void }) {
  return (
    <div role="radiogroup" aria-label="Time range" className="glass inline-flex rounded-lg p-0.5">
      {RANGES.map((d) => (
        <button
          key={d}
          type="button"
          role="radio"
          aria-checked={value === d}
          tabIndex={value === d ? 0 : -1}
          onClick={() => onChange(d)}
          onKeyDown={(e) => {
            const i = RANGES.indexOf(value as (typeof RANGES)[number]);
            if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
              e.preventDefault();
              const next = RANGES[(i + (e.key === "ArrowRight" ? 1 : RANGES.length - 1)) % RANGES.length] ?? d;
              onChange(next);
              (e.currentTarget.parentElement?.querySelector(`[data-days="${next}"]`) as HTMLElement | null)?.focus();
            }
          }}
          data-days={d}
          className={cn(
            "h-7 rounded-md px-2.5 text-xs font-medium tabular-nums outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring",
            value === d ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground",
          )}
        >
          {d}d
        </button>
      ))}
    </div>
  );
}

export function useRange(defaultDays = 30) {
  const { values, set } = useUrlState(["days"] as const);
  const parsed = Number(values.days);
  const days = RANGES.includes(parsed as (typeof RANGES)[number]) ? parsed : defaultDays;
  return { days, setDays: (d: number) => set({ days: d === defaultDays ? null : d }) };
}

export function Pagination({ page, pageSize, total, onPage }: { page: number; pageSize: number; total: number; onPage: (page: number) => void }) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  const from = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const to = Math.min(total, page * pageSize);
  return (
    <nav aria-label="Pagination" className="flex items-center justify-between gap-3 px-4 pt-3 text-xs text-muted-foreground">
      <p className="tabular-nums">
        {fmt.n(from)}–{fmt.n(to)} of {fmt.n(total)}
      </p>
      <div className="flex items-center gap-1">
        <Button variant="outline" size="icon-sm" disabled={page <= 1} onClick={() => onPage(page - 1)} aria-label="Previous page">
          <ChevronLeftIcon aria-hidden />
        </Button>
        <span className="px-2 tabular-nums">
          {page} / {pages}
        </span>
        <Button variant="outline" size="icon-sm" disabled={page >= pages} onClick={() => onPage(page + 1)} aria-label="Next page">
          <ChevronRightIcon aria-hidden />
        </Button>
      </div>
    </nav>
  );
}

export function FilterBar({ children, onReset, active }: { children: React.ReactNode; onReset?: () => void; active?: boolean }) {
  return (
    <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Filters">
      {children}
      {active && onReset ? (
        <Button variant="ghost" size="sm" onClick={onReset}>
          Clear filters
        </Button>
      ) : null}
    </div>
  );
}

// --- data table -----------------------------------------------------------------------------------

export interface Column<T> {
  key: string;
  header: React.ReactNode;
  cell: (row: T) => React.ReactNode;
  /** Numbers right-align and use tabular figures. */
  numeric?: boolean;
  className?: string;
  /** The row's title on phones (exactly one column should set it). */
  primary?: boolean;
  /** Leave out of the phone card layout. */
  hideOnMobile?: boolean;
}

/**
 * One table, two layouts. From `md` up: a real <table> (sticky header, horizontal scroll only
 * inside the card if columns still don't fit). Below `md`: each row becomes a compact card with
 * the primary cell as its title and the rest as label/value pairs, so nothing scrolls sideways.
 */
export function DataTable<T>({
  rows,
  columns,
  rowKey,
  rowHref,
  empty,
  caption,
}: {
  rows: T[];
  columns: Column<T>[];
  rowKey: (row: T) => string;
  rowHref?: (row: T) => string;
  empty?: React.ReactNode;
  caption: string;
}) {
  const router = useRouter();
  if (!rows.length) return <>{empty}</>;
  const primary = columns.find((c) => c.primary) ?? columns[0];
  if (!primary) return null;
  return (
    <>
      <div className="scrollbar-thin hidden overflow-x-auto md:block">
        <table className="w-full min-w-[640px] border-collapse text-sm">
          <caption className="sr-only">{caption}</caption>
          <thead>
            <tr className="border-b border-glass-border text-left text-xs font-medium text-muted-foreground">
              {columns.map((c) => (
                <th key={c.key} scope="col" className={cn("whitespace-nowrap px-4 py-2 font-medium first:pl-5 last:pr-5", c.numeric && "text-right", c.className)}>
                  {c.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const href = rowHref?.(row);
              return (
                <tr
                  key={rowKey(row)}
                  className={cn("border-b border-glass-border/60 last:border-0", href && "cursor-pointer transition-colors hover:bg-muted/30")}
                  onClick={
                    href
                      ? (e) => {
                          // Let real links, buttons and text selection behave normally.
                          if ((e.target as HTMLElement).closest("a,button") || window.getSelection()?.toString()) return;
                          router.push(href);
                        }
                      : undefined
                  }
                >
                  {columns.map((c) => (
                    <td key={c.key} className={cn("px-4 py-2.5 align-middle first:pl-5 last:pr-5", c.numeric && "text-right tabular-nums", c.className)}>
                      {c === primary && href ? (
                        <Link href={href} className="rounded-sm outline-none hover:underline focus-visible:ring-2 focus-visible:ring-ring">
                          {c.cell(row)}
                        </Link>
                      ) : (
                        c.cell(row)
                      )}
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <ul className="divide-y divide-glass-border md:hidden" aria-label={caption}>
        {rows.map((row) => {
          const href = rowHref?.(row);
          const inner = (
            <>
              <div className="min-w-0 font-medium">{primary.cell(row)}</div>
              <dl className="mt-1.5 grid grid-cols-2 gap-x-4 gap-y-1.5 text-xs">
                {columns
                  .filter((c) => c !== primary && !c.hideOnMobile)
                  .map((c) => (
                    <div key={c.key} className="min-w-0">
                      <dt className="text-muted-foreground">{c.header}</dt>
                      <dd className="mt-0.5 min-w-0 truncate">{c.cell(row)}</dd>
                    </div>
                  ))}
              </dl>
            </>
          );
          return (
            <li key={rowKey(row)}>
              {href ? (
                <Link href={href} className="block px-4 py-3 outline-none transition-colors hover:bg-muted/30 focus-visible:bg-muted/40">
                  {inner}
                </Link>
              ) : (
                <div className="px-4 py-3">{inner}</div>
              )}
            </li>
          );
        })}
      </ul>
    </>
  );
}

export function Muted({ children }: { children: React.ReactNode }) {
  return <span className="text-muted-foreground">{children}</span>;
}

/** Key/value list for detail panels. */
export function Facts({ items, className }: { items: [React.ReactNode, React.ReactNode][]; className?: string }) {
  return (
    <dl className={cn("grid grid-cols-1 gap-x-6 gap-y-3 text-sm sm:grid-cols-2", className)}>
      {items.map(([k, v], i) => (
        <div key={i} className="min-w-0">
          <dt className="text-xs text-muted-foreground">{k}</dt>
          <dd className="mt-0.5 min-w-0 break-words">{v}</dd>
        </div>
      ))}
    </dl>
  );
}
