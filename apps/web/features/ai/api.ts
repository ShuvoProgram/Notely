import { api } from "@/lib/api/client";
import { streamPost } from "@/lib/api/sse";
import type {
  AIChatEvent,
  AIPreferences,
  AIRun,
  AISettings, ModelTestResult, UserModel, UserModelInput,
  AIThread,
  AIThreadDetail,
  AuditEvent,
  NoteActionEvent,
  NoteAIAction,
} from "@/lib/api/types";

export const aiApi = {
  threads: () => api.get<AIThread[]>("/ai/threads"),
  thread: (id: string) => api.get<AIThreadDetail>(`/ai/threads/${id}`),
  deleteThread: (id: string) => api.delete<{ deleted: boolean }>(`/ai/threads/${id}`),
  run: (id: string) => api.get<AIRun>(`/ai/runs/${id}`),
  cancel: (runId: string) => api.post<AIRun>(`/ai/runs/${runId}/cancel`),
  settings: () => api.get<AISettings>("/ai/settings"),
  updateSettings: (prefs: AIPreferences) => api.patch<AIPreferences>("/ai/settings", prefs),
  setUserModel: (input: UserModelInput) => api.put<UserModel>("/ai/settings/model", input),
  testUserModel: () => api.post<ModelTestResult>("/ai/settings/model/test"),
  deleteUserModel: () => api.delete<{ deleted: boolean }>("/ai/settings/model"),
  audit: () => api.get<AuditEvent[]>("/audit"),

  chat: (
    body: { message: string; thread_id?: string | null; note_id?: string | null },
    onEvent: (e: AIChatEvent) => void,
    signal?: AbortSignal,
  ) => streamPost<AIChatEvent>("/ai/chat", { body, onEvent, signal }),

  approve: (
    body: { run_id: string; approval_id: string; approved_call_ids?: string[]; reject_all?: boolean },
    onEvent: (e: AIChatEvent) => void,
    signal?: AbortSignal,
  ) => streamPost<AIChatEvent>("/ai/approve", { body, onEvent, signal }),

  noteAction: (
    body: { note_id: string; action: NoteAIAction; instruction?: string; selection?: string },
    onEvent: (e: NoteActionEvent) => void,
    signal?: AbortSignal,
  ) => streamPost<NoteActionEvent>("/ai/actions", { body, onEvent, signal }),
};
