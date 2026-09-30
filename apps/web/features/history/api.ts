import { api } from "@/lib/api/client";

/** Change history of AI runs and automation runs (the server's change journal). */

export type BatchKind = "ai_run" | "automation_run";

export interface SummaryLine {
  key: string;
  count: number;
  text: string;
  reversible: boolean;
}

export interface Change {
  id: string;
  kind: string;
  provider: string;
  app: string;
  label: string;
  resource_type: string;
  resource_id: string | null;
  reversible: boolean;
  irreversible_reason: string | null;
  status: "applied" | "reverted" | "revert_skipped" | "revert_failed";
  revert_note: string | null;
  revert_attempts: number;
  reverted_at: string | null;
  created_at: string;
}

export interface RevertState {
  status: "running" | "reverted" | "partial" | "failed";
  requested_at: string;
  finished_at: string | null;
  requested_by: string | null;
  attempts: number;
  summary: { reverted?: number; skipped?: number; failed?: number; not_reversible?: number };
}

export interface Batch {
  kind: BatchKind;
  batch_id: string;
  source: string;
  title: string;
  href: string | null;
  created_at: string;
  summary: SummaryLine[];
  reversible_count: number;
  revert: RevertState | null;
  changes: Change[];
}

export interface BatchPreview extends Batch {
  preview: {
    will_revert: SummaryLine[];
    will_leave: { label: string; app: string; reason: string }[];
    cannot_revert: { label: string; app: string; reason: string | null }[];
  };
}

export const historyApi = {
  list: () => api.get<Batch[]>("/history"),
  preview: (kind: BatchKind, id: string) => api.get<BatchPreview>(`/history/${kind}/${id}`),
  revert: (kind: BatchKind, id: string, retry = false) => api.post<Batch>(`/history/${kind}/${id}/revert`, { confirm: true, retry }),
};

export const historyKeys = {
  all: ["history"] as const,
  list: ["history", "list"] as const,
  batch: (kind: BatchKind, id: string) => ["history", kind, id] as const,
};
