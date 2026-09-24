"use client";

/**
 * Every AI conversation the user has open in this tab, keyed by thread id.
 *
 * Conversations are fully independent:
 *   - each thread has its own messages, live reply, run, approval, error and busy flag;
 *   - each thread owns at most one stream (its own AbortController); starting, stopping or
 *     failing one never touches another;
 *   - streams outlive the component that started them, so switching conversations (or leaving
 *     the AI page) does not interrupt a reply; it keeps landing in its own thread;
 *   - every event is routed by the thread that opened the stream and checked against the
 *     event's own `thread_id` / `run_id` / `seq`, so a late, stale or replayed event can never
 *     show up in the wrong conversation or twice.
 *
 * After a reload, `load()` restores a thread from the server and re-attaches to a run that is
 * still going (`GET /ai/runs/{id}/stream`), replaying what was missed.
 */

import { create } from "zustand";

import { aiApi } from "@/features/ai/api";
import { ApiError } from "@/lib/api/client";
import { playSfx } from "@/lib/sfx/player";
import type { AIChatEvent, AIMessage, AIPlan, AIProposal, AIRun, AISource, AIStep, AIThreadDetail, PlanStep, RunStatus } from "@/lib/api/types";

export type StepState = AIStep;

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
  plan: AIPlan | null;
  /** A passing status from the server (e.g. "provider busy, retrying in 12s…"). */
  notice?: string | null;
  /** When this reply started (ms since epoch): drives the elapsed timer and "Worked for …". */
  startedAt: number;
}

export interface ThreadChat {
  threadId: string;
  /** `loading` until the history arrived; `load_error` if it could not be fetched. */
  status: "loading" | "ready" | "load_error";
  messages: AIMessage[];
  live: LiveAssistant | null;
  runId: string | null;
  runStatus: RunStatus | null;
  approval: PendingApproval | null;
  /** The last request in this thread failed (the message is shown with Retry). */
  error: string | null;
  /** The user stopped the last request (shown with Retry). */
  stopped: boolean;
  /** A request is in flight for this thread (only this thread's composer is affected). */
  busy: boolean;
  /** Highest `seq` applied for `runId`: replays and reconnects skip what was already seen. */
  lastSeq: number;
}

interface ChatStore {
  threads: Record<string, ThreadChat>;
}

const emptyLive = (startedAt: number = Date.now()): LiveAssistant => ({ text: "", steps: [], sources: [], plan: null, startedAt });

const blank = (threadId: string): ThreadChat => ({
  threadId,
  status: "loading",
  messages: [],
  live: null,
  runId: null,
  runStatus: null,
  approval: null,
  error: null,
  stopped: false,
  busy: false,
  lastSeq: -1,
});

export const useChatStore = create<ChatStore>(() => ({ threads: {} }));

// --- plumbing outside React state ------------------------------------------------------------

/** One open stream per thread. Replacing or aborting it affects that thread only. */
const streams = new Map<string, AbortController>();
const loading = new Map<string, Promise<void>>();
const reconnects = new Map<string, number>();
/** Bumped whenever this tab changes a thread; a history fetch that raced a change only merges. */
const revisions = new Map<string, number>();
const touch = (threadId: string) => revisions.set(threadId, (revisions.get(threadId) ?? 0) + 1);
const MAX_RECONNECTS = 3;
/** Stop pressed before the server said which run it started: cancel it as soon as it does. */
const pendingStops = new Set<string>();

let onActivity: (() => void) | null = null;
/** Called when a run starts or settles (e.g. to refresh the conversation list). */
export function setChatActivityListener(listener: (() => void) | null) {
  onActivity = listener;
}

function get(threadId: string): ThreadChat | undefined {
  return useChatStore.getState().threads[threadId];
}

function update(threadId: string, fn: (t: ThreadChat) => ThreadChat) {
  useChatStore.setState((s) => {
    const current = s.threads[threadId];
    if (!current) return s; // deleted meanwhile: drop late updates
    const next = fn(current);
    return next === current ? s : { threads: { ...s.threads, [threadId]: next } };
  });
}

function put(thread: ThreadChat) {
  useChatStore.setState((s) => ({ threads: { ...s.threads, [thread.threadId]: thread } }));
}

// --- loading and re-attaching ----------------------------------------------------------------

/** Load a thread's history once (or again with `force`), then re-attach to a run in progress. */
export function load(threadId: string, { force = false }: { force?: boolean } = {}): Promise<void> {
  const existing = get(threadId);
  if (existing && !force && existing.status !== "load_error") return loading.get(threadId) ?? Promise.resolve();
  if (loading.has(threadId)) return loading.get(threadId)!;
  if (!existing) put(blank(threadId));
  else update(threadId, (t) => ({ ...t, status: t.status === "ready" ? "ready" : "loading" }));

  const revision = revisions.get(threadId) ?? 0;
  const promise = aiApi
    .thread(threadId)
    .then((detail) => {
      // A send (or a stream) that happened meanwhile owns the live state and may already hold
      // newer messages than this response: only add what is missing.
      if (streams.has(threadId) || (revisions.get(threadId) ?? 0) !== revision) {
        update(threadId, (t) => ({ ...t, status: "ready", messages: mergeMessages(detail.messages, t.messages) }));
        return;
      }
      update(threadId, (t) => ({ ...t, ...fromDetail(detail) }));
      const run = detail.active_run;
      if (run && (run.status === "running" || run.status === "queued")) attach(threadId, run.id, -1);
    })
    .catch((error: unknown) => {
      update(threadId, (t) => ({ ...t, status: t.status === "ready" ? "ready" : "load_error", error: error instanceof ApiError ? error.message : "Couldn't load this conversation." }));
    })
    .finally(() => loading.delete(threadId));
  loading.set(threadId, promise);
  return promise;
}

function fromDetail(detail: AIThreadDetail): Partial<ThreadChat> {
  const run = detail.active_run;
  const last = detail.last_run;
  const pending = run?.approvals.find((a) => a.status === "pending");
  const unanswered = detail.messages.at(-1)?.role === "user";
  return {
    status: "ready",
    messages: detail.messages,
    runId: run?.id ?? null,
    runStatus: run?.status ?? last?.status ?? null,
    lastSeq: -1,
    busy: Boolean(run && (run.status === "running" || run.status === "queued")),
    approval: run && pending ? { approval_id: pending.id, run_id: run.id, proposals: proposalsOf(run, pending.tool_call_ids) } : null,
    live: run ? liveFromRun(run) : null,
    // Without an open run, a last request left without an answer failed or was stopped.
    error: !run && unanswered && last?.status === "failed" ? (last.error_message ?? failureText(last.error)) : null,
    stopped: !run && unanswered && last?.status === "cancelled",
  };
}

function attach(threadId: string, runId: string, after: number) {
  void runStream(threadId, (signal, emit) => aiApi.streamRun(runId, after, emit, signal));
}

// --- actions ---------------------------------------------------------------------------------

/**
 * Send a message. Without a thread, a conversation is created first; its id is returned so the
 * caller can navigate to it. The reply streams into that thread whatever is on screen.
 */
export async function send(threadId: string | null, text: string, noteId?: string | null): Promise<string | null> {
  const trimmed = text.trim();
  if (!trimmed) return threadId;
  let id = threadId;
  if (!id) {
    try {
      const thread = await aiApi.createThread({ note_id: noteId ?? null });
      id = thread.id;
      put({ ...blank(id), status: "ready" });
      onActivity?.();
    } catch (error) {
      throw error instanceof ApiError ? error : new ApiError(0, { code: "NETWORK", message: "Couldn't start a conversation.", details: {} });
    }
  }
  const current = get(id);
  if (!current) put({ ...blank(id), status: "ready" });
  if (get(id)?.busy) return id; // one request at a time per thread (the server enforces it too)

  const now = Date.now();
  const optimistic: AIMessage = { id: `local-${now}`, role: "user", content: trimmed, sources: null, run_id: null, created_at: new Date(now).toISOString() };
  touch(id);
  update(id, (t) => ({ ...t, messages: [...t.messages, optimistic], live: emptyLive(now), approval: null, error: null, stopped: false, runId: null, lastSeq: -1 }));
  playSfx("ai-start");
  const target = id;
  void runStream(target, (signal, emit) => aiApi.chat({ message: trimmed, thread_id: target, note_id: noteId ?? null }, emit, signal), {
    optimisticId: optimistic.id,
  });
  return id;
}

/** Answer the thread's last (failed or stopped) message again, without repeating it. */
export function retry(threadId: string) {
  const t = get(threadId);
  if (!t || t.busy) return;
  touch(threadId);
  update(threadId, (s) => ({ ...s, error: null, stopped: false, live: emptyLive(), runId: null, lastSeq: -1 }));
  playSfx("ai-start");
  void runStream(threadId, (signal, emit) => aiApi.chat({ thread_id: threadId, retry: true }, emit, signal));
}

export function decide(threadId: string, approvedCallIds: string[]) {
  const approval = get(threadId)?.approval;
  if (!approval) return;
  touch(threadId);
  // Same run, new stream: the server numbers this stream's events from 0 again.
  update(threadId, (t) => ({ ...t, approval: null, live: t.live ?? emptyLive(), lastSeq: -1 }));
  void runStream(threadId, (signal, emit) =>
    aiApi.approve({ run_id: approval.run_id, approval_id: approval.approval_id, approved_call_ids: approvedCallIds, reject_all: approvedCallIds.length === 0 }, emit, signal),
  );
}

/** Stop this thread's request. Other threads keep going. */
export async function stop(threadId: string) {
  const t = get(threadId);
  if (!t) return;
  const runId = t.runId;
  touch(threadId);
  reconnects.delete(threadId);
  update(threadId, (s) => ({ ...s, busy: false, live: null, approval: null, runStatus: "cancelled", stopped: s.messages.at(-1)?.role === "user", error: null }));
  if (!runId && streams.has(threadId)) {
    // Runs outlive their stream, so closing it would not stop anything: keep listening just
    // until the run's id arrives (`handleEvent`), then cancel it.
    pendingStops.add(threadId);
    return;
  }
  streams.get(threadId)?.abort();
  streams.delete(threadId);
  if (runId) await cancelRun(runId);
  onActivity?.();
}

async function cancelRun(runId: string) {
  try {
    await aiApi.cancel(runId);
  } catch {
    // Best effort: the run is detached from this tab either way.
  }
}

/** Drop a deleted thread: abort its stream and forget its state. */
export function forget(threadId: string) {
  pendingStops.delete(threadId);
  streams.get(threadId)?.abort();
  streams.delete(threadId);
  reconnects.delete(threadId);
  useChatStore.setState((s) => {
    if (!(threadId in s.threads)) return s;
    const rest = { ...s.threads };
    delete rest[threadId];
    return { threads: rest };
  });
}

// --- streaming -------------------------------------------------------------------------------

async function runStream(
  threadId: string,
  start: (signal: AbortSignal, emit: (event: AIChatEvent) => void) => Promise<void>,
  { optimisticId }: { optimisticId?: string } = {},
) {
  streams.get(threadId)?.abort(); // this thread only
  const controller = new AbortController();
  streams.set(threadId, controller);
  // Events of one network chunk are parsed together: once this stream is aborted or replaced,
  // whatever it still delivers is dropped.
  const emit = (event: AIChatEvent) => {
    if (!controller.signal.aborted && streams.get(threadId) === controller) handleEvent(threadId, event);
  };
  update(threadId, (t) => ({ ...t, busy: true, error: null }));
  onActivity?.();
  try {
    await start(controller.signal, emit);
    if (controller.signal.aborted) return;
    if (pendingStops.delete(threadId)) return; // ended before its run started: nothing to stop
    // The stream ended without the run finishing (connection dropped): pick it up again.
    const t = get(threadId);
    if (t?.busy && t.runId) {
      const attempt = (reconnects.get(threadId) ?? 0) + 1;
      if (attempt <= MAX_RECONNECTS) {
        reconnects.set(threadId, attempt);
        const runId = t.runId;
        const after = t.lastSeq;
        setTimeout(() => {
          const now = get(threadId);
          if (now?.busy && now.runId === runId && streams.get(threadId) === undefined) attach(threadId, runId, after);
        }, 500 * attempt);
        return;
      }
      update(threadId, (s) => ({ ...s, busy: false, live: null, error: "Lost the connection to Notely." }));
    }
  } catch (error) {
    if (controller.signal.aborted) return;
    if (pendingStops.delete(threadId)) return;
    if (error instanceof ApiError && error.code === "RUN_IN_PROGRESS") {
      // Already working (another tab, or a double send): show that run instead of failing.
      update(threadId, (t) => ({ ...t, messages: t.messages.filter((m) => m.id !== optimisticId), busy: false }));
      streams.delete(threadId);
      void load(threadId, { force: true });
      return;
    }
    update(threadId, (t) => ({ ...t, busy: false, live: null, error: error instanceof ApiError ? error.message : "Lost the connection to Notely." }));
  } finally {
    if (streams.get(threadId) === controller) streams.delete(threadId);
    onActivity?.();
  }
}

/** Apply one event to the thread that opened the stream, after checking it belongs there. */
export function handleEvent(threadId: string, event: AIChatEvent) {
  if (event.type === "ping") return;
  const t = get(threadId);
  if (!t) return;
  if (pendingStops.has(threadId)) {
    if (event.type === "run") {
      pendingStops.delete(threadId);
      streams.get(threadId)?.abort();
      streams.delete(threadId);
      void cancelRun(event.run_id).then(() => onActivity?.());
    }
    return; // the user already stopped this request: nothing more is shown
  }
  if (event.thread_id && event.thread_id !== threadId) return; // never cross conversations
  if (event.type !== "run" && event.run_id && t.runId && event.run_id !== t.runId) return; // stale run
  if (event.seq !== undefined && event.run_id === t.runId && event.seq <= t.lastSeq) return; // replayed
  if (event.type === "message" && t.messages.some((m) => m.id === event.message_id)) return;

  // Cues live here, outside the state updater, so they fire exactly once per event.
  if (event.type === "done" && event.status === "completed") playSfx("ai-done");
  else if (event.type === "error") playSfx("error");
  else if (event.type === "approval_required") playSfx("notification");
  if (event.type === "done") reconnects.delete(threadId);

  touch(threadId);
  update(threadId, (s) => {
    const next = apply(s, event);
    return event.seq !== undefined && event.run_id === next.runId ? { ...next, lastSeq: Math.max(next.lastSeq, event.seq) } : next;
  });
}

function apply(s: ThreadChat, event: AIChatEvent): ThreadChat {
  switch (event.type) {
    case "run": {
      const newRun = event.run_id !== s.runId;
      // Swap the optimistic user message for its persisted id, so a reload never duplicates it.
      const messages = event.user_message_id
        ? s.messages.map((m, i) => (i === s.messages.length - 1 && m.id.startsWith("local-") ? { ...m, id: event.user_message_id!, run_id: null } : m))
        : s.messages;
      return { ...s, messages, runId: event.run_id, runStatus: event.status, busy: true, live: s.live ?? emptyLive(), lastSeq: newRun ? -1 : s.lastSeq };
    }
    case "token":
      return { ...s, live: { ...(s.live ?? emptyLive()), notice: null, text: (s.live?.text ?? "") + event.text } };
    case "notice":
      return { ...s, live: { ...(s.live ?? emptyLive()), notice: event.message } };
    case "step": {
      const live = s.live ?? emptyLive();
      const existing = live.steps.findIndex((st) => st.call_id === event.call_id);
      const step: StepState = { ...(existing >= 0 ? live.steps[existing] : {}), call_id: event.call_id, tool: event.tool, label: event.label, status: event.status, result_preview: event.result_preview };
      const steps = existing >= 0 ? live.steps.map((st, i) => (i === existing ? step : st)) : [...live.steps, step];
      return { ...s, live: { ...live, steps, plan: advancePlan(live.plan, event.tool, event.status === "running" ? "active" : event.status === "completed" ? "done" : null) } };
    }
    case "plan":
      return { ...s, live: { ...(s.live ?? emptyLive()), plan: { goal: event.goal, steps: event.steps } } };
    case "verification": {
      const live = s.live ?? emptyLive();
      const steps = live.steps.map((st) => (st.call_id === event.call_id ? { ...st, verification: { status: event.status, detail: event.detail } } : st));
      return { ...s, live: { ...live, steps, plan: markPlanKind(live.plan, "verify", "done") } };
    }
    case "approval_required":
      return {
        ...s,
        approval: { approval_id: event.approval_id, run_id: event.run_id, proposals: event.proposals },
        runStatus: "waiting_for_approval",
        live: { ...(s.live ?? emptyLive()), plan: markPlanKind(s.live?.plan ?? null, "propose", "waiting") },
      };
    case "message": {
      const message: AIMessage = {
        id: event.message_id,
        role: "assistant",
        content: event.content,
        sources: event.sources.length ? event.sources : null,
        run_id: s.runId,
        created_at: new Date().toISOString(),
        steps: s.live?.steps.length ? s.live.steps : undefined,
        plan: s.live?.plan ? closePlan(s.live.plan) : null,
        duration_ms: s.live ? Date.now() - s.live.startedAt : undefined,
      };
      return { ...s, messages: [...s.messages, message], live: null };
    }
    case "done":
      return {
        ...s,
        runStatus: event.status,
        busy: false,
        live: event.status === "waiting_for_approval" ? s.live : null,
        stopped: event.status === "cancelled" && s.messages.at(-1)?.role === "user",
      };
    case "error":
      return { ...s, error: event.message, busy: false, live: null };
    default:
      return s;
  }
}

// --- helpers ---------------------------------------------------------------------------------

function mergeMessages(persisted: AIMessage[], local: AIMessage[]): AIMessage[] {
  const known = new Set(persisted.map((m) => m.id));
  return [...persisted, ...local.filter((m) => !known.has(m.id))];
}

function proposalsOf(run: AIRun, callIds: string[]): AIProposal[] {
  return run.tool_calls
    .filter((tc) => callIds.includes(tc.call_id))
    .map((tc) => ({ call_id: tc.call_id, tool_name: tc.tool_name, provider: tc.provider, risk: tc.risk_level, summary: summarizeToolCall(tc.tool_name, tc.arguments), arguments: tc.arguments }));
}

function liveFromRun(run: AIRun): LiveAssistant {
  return {
    text: "",
    steps: run.steps
      .filter((st) => st.call_id)
      .map((st) => ({ call_id: st.call_id!, tool: st.tool ?? "", label: st.label ?? "", status: (st.status as StepState["status"]) ?? "completed", verification: st.verification })),
    sources: run.sources ?? [],
    plan: run.plan ?? null,
    startedAt: Date.parse(run.created_at ?? "") || Date.now(),
  };
}

function failureText(error: string | null): string {
  return error === "interrupted" ? "The assistant was interrupted before it finished." : "The assistant ran into a problem.";
}

/** Mirrors the server's plan bookkeeping so the checklist moves as steps stream in. */
function advancePlan(plan: AIPlan | null, tool: string, status: "active" | "done" | null): AIPlan | null {
  if (!plan || !status) return plan;
  return markPlan(plan, (step) => step.tools.includes(tool), status);
}

function markPlanKind(plan: AIPlan | null, kind: PlanStep["kind"], status: PlanStep["status"]): AIPlan | null {
  if (!plan) return plan;
  return markPlan(plan, (step) => step.kind === kind, status);
}

function markPlan(plan: AIPlan, matches: (step: PlanStep) => boolean, status: PlanStep["status"]): AIPlan {
  const steps = plan.steps.map((s) => ({ ...s }));
  const index = steps.findIndex((s) => s.status !== "done" && s.status !== "skipped" && matches(s));
  if (index < 0) return plan;
  steps[index]!.status = status;
  for (let i = 0; i < index; i++) if (steps[i]!.status !== "done" && steps[i]!.status !== "skipped") steps[i]!.status = "done";
  return { ...plan, steps };
}

function closePlan(plan: AIPlan): AIPlan {
  return { ...plan, steps: plan.steps.map((s) => (s.status === "done" ? s : { ...s, status: s.kind === "answer" ? "done" : "skipped" })) };
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
    case "search_everything":
      return `Search everything for “${String(args.query ?? "")}”`;
    case "plan_steps":
      return `Plan: ${String(args.goal ?? "")}`;
    default:
      return tool.replace(/_/g, " ");
  }
}

/** Test-only: reset every conversation and stream. */
export function resetChatStore() {
  for (const controller of streams.values()) controller.abort();
  streams.clear();
  loading.clear();
  reconnects.clear();
  revisions.clear();
  pendingStops.clear();
  useChatStore.setState({ threads: {} });
}
