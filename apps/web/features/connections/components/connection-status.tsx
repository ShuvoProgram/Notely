import { AlertTriangle, Check, Circle, Clock, Loader2, RefreshCw, WifiOff, type IconComponent } from "@/components/icons";

import type { Connection, ConnectionStatus } from "@/lib/api/types";
import { cn } from "@/lib/utils";

/** What the user should do next. Drives the one button every card shows. */
export type ConnectionAction = "connect" | "manage" | "reconnect" | "retry" | null;

export interface ConnectionView {
  /** Visual state, coarser than the API status so every state has one clear look. */
  state: "connected" | "connecting" | "syncing" | "attention" | "error" | "rate_limited" | "disconnected";
  label: string;
  /** Shorter label for cards ("Needs attention" instead of "Connection needs attention"). */
  shortLabel?: string;
  /** One supporting line: what happened, or when it was last checked. */
  detail: string;
  icon: IconComponent;
  tone: string;
  spinning?: boolean;
  action: ConnectionAction;
}

export function relativeTime(iso: string | null): string {
  if (!iso) return "never";
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.round(diff / 60_000);
  if (m < 1) return "just now";
  if (m < 60) return `${m} min ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h} hour${h === 1 ? "" : "s"} ago`;
  return `${Math.round(h / 24)} day${Math.round(h / 24) === 1 ? "" : "s"} ago`;
}

/**
 * Turns the API's status + last error into one consistent presentation. Status is always
 * icon + text, never colour alone. The API only reports `expired` when a refresh was actually
 * rejected by the vendor, so "Reconnect" here means it is genuinely required.
 */
export function describeConnection(conn: Connection | null, providerName: string, opts?: { available?: boolean; refreshing?: boolean }): ConnectionView {
  if (opts?.refreshing) {
    return { state: "connecting", label: "Reconnecting…", detail: `Checking ${providerName}`, icon: RefreshCw, tone: "text-muted-foreground", spinning: true, action: null };
  }
  const status: ConnectionStatus | "none" = conn && conn.status !== "disconnected" ? conn.status : "none";
  switch (status) {
    case "none":
    case "pending":
      return {
        state: "disconnected",
        label: "Not connected",
        detail: opts?.available === false ? "Not available on this deployment" : "",
        icon: Circle,
        tone: "text-muted-foreground",
        action: opts?.available === false ? null : "connect",
      };
    case "connecting":
      return { state: "connecting", label: "Connecting…", detail: "Waiting for authorization", icon: Loader2, tone: "text-muted-foreground", spinning: true, action: null };
    case "syncing":
      return { state: "syncing", label: "Syncing…", detail: "Updating your data", icon: RefreshCw, tone: "text-ai", spinning: true, action: "manage" };
    case "connected": {
      const at = conn?.last_sync_at ?? conn?.last_checked_at ?? null;
      return {
        state: "connected",
        label: "Connected",
        detail: at ? `${conn?.last_sync_at ? "Last synced" : "Last checked"} ${relativeTime(at)}` : conn?.external_account_name ? conn.external_account_name : "",
        icon: Check,
        tone: "text-success",
        action: "manage",
      };
    }
    case "expired":
      return { state: "attention", label: "Connection needs attention", shortLabel: "Needs attention", detail: "Authorization expired", icon: AlertTriangle, tone: "text-warning", action: "reconnect" };
    case "needs_attention":
      return {
        state: "attention",
        label: "Connection needs attention",
        shortLabel: "Needs attention",
        detail: conn?.last_error ?? "Additional permission or configuration required",
        icon: AlertTriangle,
        tone: "text-warning",
        action: conn?.last_error_code === "permission_denied" || conn?.last_error_code === "admin_approval_required" ? "reconnect" : "manage",
      };
    case "error":
      if (conn?.last_error_code === "rate_limited") {
        return { state: "rate_limited", label: "Rate limited", detail: `${providerName} asked us to slow down`, icon: Clock, tone: "text-warning", action: "retry" };
      }
      return { state: "error", label: "Connection unavailable", detail: conn?.last_error ?? `Unable to sync with ${providerName}`, icon: WifiOff, tone: "text-destructive", action: "retry" };
    default:
      return { state: "disconnected", label: "Not connected", detail: "", icon: Circle, tone: "text-muted-foreground", action: "connect" };
  }
}

export const ACTION_LABEL: Record<Exclude<ConnectionAction, null>, string> = {
  connect: "Connect",
  manage: "Manage",
  reconnect: "Reconnect",
  retry: "Try again",
};

/** Icon + label + one detail line. Used on cards and on the detail page. */
export function ConnectionStatusBadge({ view, className, compact }: { view: ConnectionView; className?: string; compact?: boolean }) {
  const Icon = view.icon;
  return (
    <div className={cn("flex min-w-0 items-start gap-2", compact ? "text-xs" : "text-sm", className)}>
      <Icon className={cn("mt-0.5 size-4 shrink-0", view.tone, view.spinning && "animate-spin")} aria-hidden />
      <div className="min-w-0">
        <p className={cn("truncate font-medium", view.tone)}>{compact ? (view.shortLabel ?? view.label) : view.label}</p>
        {view.detail ? <p className="truncate text-xs text-muted-foreground">{view.detail}</p> : null}
      </div>
    </div>
  );
}
