"use client";

import { useQueryClient } from "@tanstack/react-query";
import * as React from "react";

import { aiApi } from "@/features/ai/api";
import { ApiError } from "@/lib/api/client";
import type { AIChatEvent, AIMessage, AIProposal, AISource, RunStatus } from "@/lib/api/types";

export interface StepState {
  call_id: string;
  tool: string;
  label: string;
  status: "running" | "completed" | "failed";
  result_preview?: string;
}

export interface PendingApproval {
  approval_id: string;
  run_id: string;
  proposals: AIProposal[];
}

/** A message being produced by the current run (not yet persisted). */
export interface LiveAssistant {
  text: string;
  steps: StepState[];
  sources: AISource[];
}

export interface ChatState {
  threadId: string | null;
  messages: AIMessage[];
  live: LiveAssistant | null;
  runId: string | null;
  runStatus: RunStatus | null;
  approval: PendingApproval | null;
  error: string | null;
  busy: boolean;
}

const initialState: ChatState = {
  threadId: null,
  messages: [],
  live: null,
  runId: null,
  runStatus: null,
  approval: null,
  error: null,
  busy: false,
};

export function useChat(initialThreadId: string | null) {
  const queryClient = useQueryClient();
  const [state, setState] = React.useState<ChatState>({ ...initialState, threadId: initialThreadId });
  const abortRef = React.useRef<AbortController | null>(null);
  const ownedThreadRef = React.useRef<string | null>(null);

  // Load an existing thread's history. A thread this hook created itself (the URL catches up
  // after the first `run` event) is already in state and must not be reloaded mid-stream.
  React.useEffect(() => {
    let cancelled = false;
    if (!initialThreadId) {
      ownedThreadRef.current = null;
      abortRef.current?.abort();
      setState({ ...initialState });
      return;
    }
    if (ownedThreadRef.current === initialThreadId) return;
    ownedThreadRef.current = initialThreadId;
    setState({ ...initialState, threadId: initialThreadId });
    aiApi
      .thread(initialThreadId)
      .then((detail) => {
        if (cancelled) return;
        const run = detail.active_run;
        const pending = run?.approvals.find((a) => a.status === "pending");
        setState((s) => ({
          ...s,
          messages: detail.messages,
          runId: run?.id ?? null,
          runStatus: run?.status ?? null,
          approval:
            run && pending
              ? {
                  approval_id: pending.id,
                  run_id: run.id,
                  proposals: run.tool_calls
                    .filter((tc) => pending.tool_call_ids.includes(tc.call_id))
                    .map((tc) => ({
                      call_id: tc.call_id,
                      tool_name: tc.tool_name,
                      provider: tc.provider,
                      risk: tc.risk_level,
                      summary: summarizeToolCall(tc.tool_name, tc.arguments),
                      arguments: tc.arguments,
                    })),
                }
              : null,
          live:
            run && run.status === "waiting_for_approval"
              ? { text: "", steps: run.steps.filter((st) => st.call_id).map((st) => ({ call_id: st.call_id!, tool: st.tool ?? "", label: st.label ?? "", status: (st.status as StepState["status"]) ?? "completed" })), sources: [] }
              : null,
        }));
      })
      .catch((error: unknown) => {
        if (!cancelled) setState((s) => ({ ...s, error: error instanceof ApiError ? error.message : "Couldn't load this conversation." }));
      });
    return () => {
      cancelled = true;
    };
  }, [initialThreadId]);

  const handleEvent = React.useCallback(
    (event: AIChatEvent) => {
      setState((s) => {
        switch (event.type) {
          case "run":
            ownedThreadRef.current = event.thread_id;
            return { ...s, threadId: event.thread_id, runId: event.run_id, runStatus: event.status };
          case "token":
            return { ...s, live: { ...(s.live ?? { text: "", steps: [], sources: [] }), text: (s.live?.text ?? "") + event.text } };
          case "step": {
            const live = s.live ?? { text: "", steps: [], sources: [] };
            const existing = live.steps.findIndex((st) => st.call_id === event.call_id);
            const step: StepState = { call_id: event.call_id, tool: event.tool, label: event.label, status: event.status, result_preview: event.result_preview };
            const steps = existing >= 0 ? live.steps.map((st, i) => (i === existing ? step : st)) : [...live.steps, step];
            return { ...s, live: { ...live, steps } };
          }
          case "approval_required":
            return { ...s, approval: { approval_id: event.approval_id, run_id: event.run_id, proposals: event.proposals }, runStatus: "waiting_for_approval" };
          case "message": {
            const message: AIMessage = {
              id: event.message_id,
              role: "assistant",
              content: event.content,
              sources: event.sources.length ? event.sources : null,
              run_id: s.runId,
              created_at: new Date().toISOString(),
              steps: s.live?.steps.length ? s.live.steps : undefined,
            };
            return { ...s, messages: [...s.messages, message], live: null };
          }
          case "done":
            return { ...s, runStatus: event.status, busy: false, live: event.status === "waiting_for_approval" ? s.live : null };
          case "error":
            return { ...s, error: event.message, busy: false };
          default:
            return s;
        }
      });
    },
    [],
  );

  const runStream = React.useCallback(
    async (start: (signal: AbortSignal) => Promise<void>) => {
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      setState((s) => ({ ...s, busy: true, error: null }));
      try {
        await start(controller.signal);
      } catch (error) {
        if (controller.signal.aborted) return;
        setState((s) => ({ ...s, busy: false, error: error instanceof ApiError ? error.message : "Lost the connection to Notely." }));
      } finally {
        if (abortRef.current === controller) abortRef.current = null;
        queryClient.invalidateQueries({ queryKey: ["ai", "threads"] });
        queryClient.invalidateQueries({ queryKey: ["tasks"] });
        queryClient.invalidateQueries({ queryKey: ["notes"] });
      }
    },
    [queryClient],
  );

  const send = React.useCallback(
    (text: string, noteId?: string | null) => {
      const trimmed = text.trim();
      if (!trimmed) return;
      const optimistic: AIMessage = { id: `local-${Date.now()}`, role: "user", content: trimmed, sources: null, run_id: null, created_at: new Date().toISOString() };
      setState((s) => ({ ...s, messages: [...s.messages, optimistic], live: { text: "", steps: [], sources: [] }, approval: null }));
      void runStream((signal) => aiApi.chat({ message: trimmed, thread_id: state.threadId, note_id: noteId ?? null }, handleEvent, signal));
    },
    [handleEvent, runStream, state.threadId],
  );

  const decide = React.useCallback(
    (approvedCallIds: string[]) => {
      const approval = state.approval;
      if (!approval) return;
      setState((s) => ({ ...s, approval: null, live: s.live ?? { text: "", steps: [], sources: [] } }));
      void runStream((signal) =>
        aiApi.approve(
          { run_id: approval.run_id, approval_id: approval.approval_id, approved_call_ids: approvedCallIds, reject_all: approvedCallIds.length === 0 },
          handleEvent,
          signal,
        ),
      );
    },
    [handleEvent, runStream, state.approval],
  );

  const stop = React.useCallback(async () => {
    abortRef.current?.abort();
    if (state.runId) {
      try {
        await aiApi.cancel(state.runId);
      } catch {
        // best effort
      }
    }
    setState((s) => ({ ...s, busy: false, live: null, approval: null, runStatus: "cancelled" }));
  }, [state.runId]);

  React.useEffect(() => () => abortRef.current?.abort(), []);

  return { state, send, decide, stop };
}

export function summarizeToolCall(tool: string, args: Record<string, unknown>): string {
  const title = typeof args.title === "string" ? `“${args.title}”` : "";
  switch (tool) {
    case "create_task":
      return `Create task ${title}`.trim();
    case "create_note":
      return `Create note ${title}`.trim();
    case "complete_task":
      return "Mark a task as done";
    case "search_notes":
      return `Search notes for “${String(args.query ?? "")}”`;
    default:
      return tool.replace(/_/g, " ");
  }
}
