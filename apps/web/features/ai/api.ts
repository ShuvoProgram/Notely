import { api } from "@/lib/api/client";
import { streamGet, streamPost } from "@/lib/api/sse";
import type {
  AIChatEvent,
  AIPreferences,
  AIRun,
  AISettings,
  ModelDraft,
  ModelInfo,
  ModelTestResult,
  UserModel,
  UserModelInput,
  AIThread,
  AIThreadDetail,
  AuditEvent,
  NoteActionEvent,
  NoteAIAction,
} from "@/lib/api/types";

export const aiApi = {
  threads: (options: { archived?: boolean } = {}) => api.get<AIThread[]>(options.archived ? "/ai/threads?archived=true" : "/ai/threads"),
  thread: (id: string) => api.get<AIThreadDetail>(`/ai/threads/${id}`),
  createThread: (body: { title?: string | null; note_id?: string | null } = {}) => api.post<AIThread>("/ai/threads", body),
  updateThread: (id: string, body: { title?: string; archived?: boolean }) => api.patch<AIThread>(`/ai/threads/${id}`, body),
  deleteThread: (id: string) => api.delete<{ deleted: boolean }>(`/ai/threads/${id}`),
  run: (id: string) => api.get<AIRun>(`/ai/runs/${id}`),
  cancel: (runId: string) => api.post<AIRun>(`/ai/runs/${runId}/cancel`),
  settings: () => api.get<AISettings>("/ai/settings"),
  updateSettings: (prefs: AIPreferences) => api.patch<AIPreferences>("/ai/settings", prefs),
  setUserModel: (input: UserModelInput) => api.put<UserModel>("/ai/settings/model", input),
  /** Test the saved configuration, or (with a draft) one that is not stored yet. */
  testUserModel: (draft?: ModelDraft) => api.post<ModelTestResult>("/ai/settings/model/test", draft),
  // Which models a key can use, from the vendor. Empty api_key = the stored key for that provider.
  listUserModels: (input: { provider: string; api_key?: string | null; base_url?: string | null }) =>
    api.post<{ models: ModelInfo[] }>("/ai/settings/model/models", input),
  deleteUserModel: () => api.delete<{ deleted: boolean }>("/ai/settings/model"),
  audit: () => api.get<AuditEvent[]>("/audit"),

  /** Send a message (or, with `retry`, answer the thread's last message again). */
  chat: (
    body: { message?: string; thread_id?: string | null; note_id?: string | null; retry?: boolean },
    onEvent: (e: AIChatEvent) => void,
    signal?: AbortSignal,
  ) => streamPost<AIChatEvent>("/ai/chat", { body, onEvent, signal }),

  /** Re-attach to a run: replays events after `after`, then follows it live. */
  streamRun: (runId: string, after: number, onEvent: (e: AIChatEvent) => void, signal?: AbortSignal) =>
    streamGet<AIChatEvent>(`/ai/runs/${runId}/stream?after=${after}`, { onEvent, signal }),

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
