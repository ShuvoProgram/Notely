"use client";

import { AlertTriangle, Check, CloudOff, Loader2 } from "@/components/icons";

import type { SaveStatus } from "@/features/notes/use-autosave";
import { cn } from "@/lib/utils";

const LABELS: Record<SaveStatus, string> = {
  idle: "",
  dirty: "Unsaved changes",
  saving: "Saving…",
  saved: "Saved",
  offline: "Offline — changes kept locally",
  conflict: "Changed elsewhere",
  error: "Couldn't save",
};

export function SaveStatusIndicator({ status, message }: { status: SaveStatus; message?: string | null }) {
  if (status === "idle") return null;
  const Icon =
    status === "saving" ? Loader2 : status === "saved" ? Check : status === "offline" ? CloudOff : status === "dirty" ? null : AlertTriangle;
  const tone =
    status === "error" || status === "conflict"
      ? "text-warning"
      : status === "saved"
        ? "text-success"
        : "text-muted-foreground";
  return (
    <span
      role="status"
      aria-live="polite"
      className={cn("inline-flex items-center gap-1.5 text-xs", tone)}
      title={message ?? undefined}
    >
      {Icon ? <Icon className={cn("size-3.5", status === "saving" && "animate-spin")} aria-hidden /> : null}
      {LABELS[status]}
    </span>
  );
}
