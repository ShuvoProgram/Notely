"use client";

import * as React from "react";

import * as chat from "@/features/ai/chat-store";
import { type ThreadChat, useChatStore } from "@/features/ai/chat-store";

export type { LiveAssistant, PendingApproval, StepState, ThreadChat } from "@/features/ai/chat-store";
export { summarizeToolCall } from "@/features/ai/chat-store";

/** What a brand-new conversation (no thread yet) looks like. */
const DRAFT: ThreadChat = {
  threadId: "",
  status: "ready",
  messages: [],
  live: null,
  runId: null,
  runStatus: null,
  approval: null,
  error: null,
  stopped: false,
  busy: false,
  lastSeq: -1,
};

/**
 * One conversation's view of the shared chat store. Switching `threadId` only changes what is
 * shown: requests in the thread being left keep streaming into it, and this component only
 * re-renders for changes to the thread it shows.
 */
export function useChat(threadId: string | null, { onThreadCreated }: { onThreadCreated?: (id: string) => void } = {}) {
  const thread = useChatStore((s) => (threadId ? s.threads[threadId] : undefined));
  const [sendError, setSendError] = React.useState<string | null>(null);

  // (The panel is keyed by thread, so `sendError` never outlives its conversation.)
  React.useEffect(() => {
    // First visit loads the history; returning to a thread quietly refreshes it (another tab may
    // have added to it) without disturbing a reply that is streaming here.
    if (threadId) void chat.load(threadId, { force: true });
  }, [threadId]);

  const state: ThreadChat = thread ?? (threadId ? { ...DRAFT, threadId, status: "loading" } : DRAFT);

  const send = React.useCallback(
    async (text: string, noteId?: string | null) => {
      setSendError(null);
      try {
        const id = await chat.send(threadId, text, noteId);
        if (id && id !== threadId) onThreadCreated?.(id);
      } catch (error) {
        setSendError(error instanceof Error ? error.message : "Couldn't send that.");
      }
    },
    [threadId, onThreadCreated],
  );
  const decide = React.useCallback((ids: string[]) => threadId && chat.decide(threadId, ids), [threadId]);
  const stop = React.useCallback(async () => {
    if (threadId) await chat.stop(threadId);
  }, [threadId]);
  const retry = React.useCallback(() => threadId && chat.retry(threadId), [threadId]);

  return { state: sendError && !threadId ? { ...state, error: sendError } : state, send, decide, stop, retry };
}
