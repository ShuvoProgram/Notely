import { AlertTriangle, Check, Circle, Loader2, RefreshCw, XCircle } from "lucide-react";

import type { ConnectionStatus } from "@/lib/api/types";
import { cn } from "@/lib/utils";

/** Status is always conveyed by icon + text, never colour alone (WCAG). */
export const STATUS_META: Record<ConnectionStatus, { label: string; hint: string; icon: typeof Check; tone: string }> = {
  pending: { label: "Not connected", hint: "", icon: Circle, tone: "text-muted-foreground" },
  connecting: { label: "Connecting", hint: "Waiting for authorization…", icon: Loader2, tone: "text-muted-foreground" },
  connected: { label: "Connected", hint: "", icon: Check, tone: "text-success" },
  syncing: { label: "Syncing", hint: "Updating your data…", icon: RefreshCw, tone: "text-ai" },
  needs_attention: { label: "Needs attention", hint: "Additional permission or configuration required", icon: AlertTriangle, tone: "text-warning" },
  expired: { label: "Session expired", hint: "Reconnect to continue", icon: AlertTriangle, tone: "text-warning" },
  error: { label: "Connection error", hint: "", icon: XCircle, tone: "text-destructive" },
  disconnected: { label: "Not connected", hint: "", icon: Circle, tone: "text-muted-foreground" },
};

export function relativeTime(iso: string | null): string {
  if (!iso) return "never";
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.round(diff / 60_000);
  if (m < 1) return "just now";
  if (m < 60) return `${m} minute${m === 1 ? "" : "s"} ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h} hour${h === 1 ? "" : "s"} ago`;
  return `${Math.round(h / 24)} day${Math.round(h / 24) === 1 ? "" : "s"} ago`;
}

export function ConnectionStatusBadge({ status, lastChecked, lastError, className }: { status: ConnectionStatus | "none"; lastChecked?: string | null; lastError?: string | null; className?: string }) {
  const meta = status === "none" ? STATUS_META.disconnected : STATUS_META[status];
  const Icon = meta.icon;
  const detail = status === "connected" && lastChecked ? `Last checked ${relativeTime(lastChecked)}` : lastError || meta.hint;
  return (
    <div className={cn("flex items-start gap-2 text-sm", className)}>
      <Icon className={cn("mt-0.5 size-4 shrink-0", meta.tone, (status === "connecting" || status === "syncing") && "animate-spin")} aria-hidden />
      <div className="min-w-0">
        <p className={cn("font-medium", meta.tone)}>{meta.label}</p>
        {detail ? <p className="truncate text-xs text-muted-foreground">{detail}</p> : null}
      </div>
    </div>
  );
}
