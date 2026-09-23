import { api } from "@/lib/api/client";

import type { Automation, AutomationInput, Catalog, Draft, Issue, Run, RunDetail, Template, Workflow } from "./types";

const base = "/automations";

export const automationsApi = {
  list: () => api.get<Automation[]>(base),
  get: (id: string) => api.get<Automation>(`${base}/${id}`),
  create: (input: AutomationInput) => api.post<Automation>(base, input),
  update: (id: string, input: AutomationInput) => api.patch<Automation>(`${base}/${id}`, input),
  remove: (id: string) => api.delete<{ deleted: boolean }>(`${base}/${id}`),
  duplicate: (id: string) => api.post<Automation>(`${base}/${id}/duplicate`, {}),
  setEnabled: (id: string, enabled: boolean) => api.post<Automation>(`${base}/${id}/enabled`, { enabled }),
  run: (id: string) => api.post<Run>(`${base}/${id}/run`, { idempotency_key: crypto.randomUUID() }),
  test: (id: string, stepId?: string) => api.post<Run>(`${base}/${id}/test`, { step_id: stepId ?? null }),
  runs: (id: string) => api.get<Run[]>(`${base}/${id}/runs`),
  runDetail: (id: string, runId: string) => api.get<RunDetail>(`${base}/${id}/runs/${runId}`),
  retryStep: (id: string, runId: string, stepId: string) => api.post<Run>(`${base}/${id}/runs/${runId}/steps/${stepId}/retry`, {}),
  decide: (id: string, approvalId: string, approved: boolean) => api.post<Run>(`${base}/${id}/approvals/${approvalId}`, { approved }),
  catalog: () => api.get<Catalog>(`${base}/catalog`),
  validate: (workflow: Workflow) => api.post<{ valid: boolean; issues: Issue[]; error: string | null }>(`${base}/validate`, { workflow }),
  templates: () => api.get<Template[]>(`${base}/templates`),
  saveTemplate: (id: string, name?: string) => api.post<Template>(`${base}/${id}/template`, { name: name ?? null }),
  deleteTemplate: (id: string) => api.delete<{ deleted: boolean }>(`${base}/templates/${id}`),
  draft: (prompt: string, current?: { name: string; workflow: Workflow; schedule_kind: string; schedule_config: Record<string, unknown>; timezone: string }) =>
    api.post<Draft>(`${base}/draft`, {
      prompt,
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
      current: current ?? null,
    }),
};

export const TERMINAL_RUN = new Set(["completed", "stopped", "failed", "skipped", "waiting_for_approval"]);
