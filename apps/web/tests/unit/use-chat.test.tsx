import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";

import * as chat from "@/features/ai/chat-store";
import { useChat } from "@/features/ai/use-chat";
import type { AIChatEvent, AIRun, AIThreadDetail } from "@/lib/api/types";

/* ── fetch double ─────────────────────────────────────────────────────────────
 * Every request is answered by a route; a stream route returns a `Pipe` the test writes
 * events into (and can end, or observe being aborted), so two conversations' streams can be
 * interleaved exactly as a scenario needs.                                                  */

class Pipe {
  private controller!: ReadableStreamDefaultController<Uint8Array>;
  aborted = false;
  readonly body = new ReadableStream<Uint8Array>({ start: (c) => void (this.controller = c) });
  push(...events: AIChatEvent[]) {
    for (const e of events) this.controller.enqueue(new TextEncoder().encode(`event: ${e.type}\ndata: ${JSON.stringify(e)}\n\n`));
  }
  end() {
    try {
      this.controller.close();
    } catch {
      // already closed or errored
    }
  }
}

type Handler = (init: RequestInit & { url: string; json: unknown }) => Response | Pipe | Promise<Response | Pipe>;
let routes: { method: string; match: RegExp; handle: Handler }[] = [];
const calls: { method: string; url: string; json: unknown }[] = [];

function route(method: string, match: RegExp, handle: Handler) {
  routes.unshift({ method, match, handle });
}
const json = (data: unknown, status = 200) => new Response(JSON.stringify(status < 400 ? { data } : data), { status, headers: { "Content-Type": "application/json" } });

beforeEach(() => {
  chat.resetChatStore();
  routes = [];
  calls.length = 0;
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init = {}) => {
    const url = String(input);
    const method = init.method ?? "GET";
    const body = typeof init.body === "string" ? JSON.parse(init.body) : undefined;
    calls.push({ method, url, json: body });
    const hit = routes.find((r) => r.method === method && r.match.test(url));
    if (!hit) throw new Error(`unrouted ${method} ${url}`);
    const out = await hit.handle({ ...init, url, json: body });
    if (!(out instanceof Pipe)) return out;
    init.signal?.addEventListener("abort", () => {
      out.aborted = true;
      out.end();
    });
    return new Response(out.body, { status: 200, headers: { "Content-Type": "text/event-stream" } });
  });
});

function wrapper({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

const thread = (id: string) => ({ id, title: "New conversation", note_id: null, created_at: "", updated_at: "", last_activity_at: "", archived_at: null });
const detail = (id: string, extra: Partial<AIThreadDetail> = {}): AIThreadDetail => ({ thread: thread(id), messages: [], active_run: null, last_run: null, ...extra });
const run = (id: string, threadId: string, status: AIRun["status"]): AIRun => ({
  id,
  thread_id: threadId,
  status,
  model: null,
  provider: null,
  token_usage: {},
  steps: [],
  plan: null,
  sources: [],
  error: null,
  created_at: new Date().toISOString(),
  started_at: null,
  completed_at: null,
  tool_calls: [],
  approvals: [],
});

/** Stamp events the way the server does: every event carries its thread, run and seq. */
function stamper(threadId: string, runId: string) {
  let seq = 0;
  return (e: Record<string, unknown> & { type: string }) => ({ ...e, thread_id: threadId, run_id: runId, seq: seq++ }) as AIChatEvent;
}

const chatPipes: Record<string, Pipe> = {};
function routeChats() {
  route("POST", /\/ai\/chat$/, ({ json: body }) => {
    const pipe = new Pipe();
    chatPipes[(body as { thread_id: string }).thread_id] = pipe;
    return pipe;
  });
}

const t = (id: string) => chat.useChatStore.getState().threads[id]!;

describe("chat store: independent conversations", () => {
  it("streams tokens, steps and a final message into its own thread", async () => {
    route("POST", /\/ai\/threads$/, () => json(thread("t1"), 201));
    routeChats();
    const created: string[] = [];
    const { result } = renderHook(() => useChat(null, { onThreadCreated: (id) => created.push(id) }), { wrapper });
    await act(() => result.current.send("find x"));
    expect(created).toEqual(["t1"]);
    const s = stamper("t1", "r1");
    act(() =>
      chatPipes.t1!.push(
        s({ type: "run", status: "running", user_message_id: "u1" }),
        s({ type: "step", call_id: "c1", tool: "search_notes", label: "Search notes", status: "running" }),
        s({ type: "step", call_id: "c1", tool: "search_notes", label: "Search notes", status: "completed", result_preview: "2 result(s)" }),
        s({ type: "token", text: "Here " }),
        s({ type: "token", text: "you go." }),
        s({ type: "message", message_id: "m1", content: "Here you go.", sources: [{ provider: "notely", object_id: "n1", title: "N", url: "/app/notes/n1" }] }),
        s({ type: "done", status: "completed", usage: {} }),
      ),
    );
    chatPipes.t1!.end();
    await waitFor(() => expect(t("t1").busy).toBe(false));
    expect(t("t1").messages.map((m) => [m.id, m.role, m.content])).toEqual([
      ["u1", "user", "find x"], // optimistic id swapped for the persisted one
      ["m1", "assistant", "Here you go."],
    ]);
    expect(t("t1").messages[1]?.steps?.[0]?.status).toBe("completed");
    expect(t("t1").live).toBeNull();
  });

  it("keeps a reply streaming into thread A while the user switches to B and chats there", async () => {
    routeChats();
    route("GET", /\/ai\/threads\/A$/, () => json(detail("A")));
    route("GET", /\/ai\/threads\/B$/, () => json(detail("B")));
    const { result, rerender } = renderHook(({ id }) => useChat(id), { wrapper, initialProps: { id: "A" } });
    await waitFor(() => expect(result.current.state.status).toBe("ready"));
    await act(() => result.current.send("question A"));
    const a = stamper("A", "rA");
    act(() => chatPipes.A!.push(a({ type: "run", status: "running" }), a({ type: "token", text: "Alpha " })));

    rerender({ id: "B" }); // switch while A is generating
    await waitFor(() => expect(result.current.state.threadId).toBe("B"));
    expect(result.current.state.busy).toBe(false); // B is not blocked by A
    await act(() => result.current.send("question B"));
    const b = stamper("B", "rB");
    act(() => {
      chatPipes.B!.push(b({ type: "run", status: "running" }), b({ type: "token", text: "Bravo " }));
      chatPipes.A!.push(a({ type: "token", text: "still going" }));
    });

    expect(chatPipes.A!.aborted).toBe(false);
    await waitFor(() => expect(t("A").live?.text).toBe("Alpha still going"));
    expect(t("B").live?.text).toBe("Bravo ");
    expect(result.current.state.live?.text).toBe("Bravo "); // the screen shows B only

    act(() => {
      chatPipes.A!.push(a({ type: "message", message_id: "mA", content: "Alpha still going", sources: [] }), a({ type: "done", status: "completed", usage: {} }));
      chatPipes.B!.push(b({ type: "message", message_id: "mB", content: "Bravo", sources: [] }), b({ type: "done", status: "completed", usage: {} }));
    });
    chatPipes.A!.end();
    chatPipes.B!.end();
    await waitFor(() => expect(t("A").busy || t("B").busy).toBe(false));
    expect(t("A").messages.map((m) => m.content)).toEqual(["question A", "Alpha still going"]);
    expect(t("B").messages.map((m) => m.content)).toEqual(["question B", "Bravo"]);
  });

  it("stops thread A without touching thread B", async () => {
    routeChats();
    route("POST", /\/ai\/runs\/rA\/cancel$/, () => json(run("rA", "A", "cancelled")));
    for (const id of ["A", "B"]) {
      route("GET", new RegExp(`/ai/threads/${id}$`), () => json(detail(id)));
      await chat.load(id);
    }
    await chat.send("A", "long one");
    await chat.send("B", "another");
    const a = stamper("A", "rA");
    const b = stamper("B", "rB");
    act(() => {
      chatPipes.A!.push(a({ type: "run", status: "running" }), a({ type: "token", text: "partial" }));
      chatPipes.B!.push(b({ type: "run", status: "running" }), b({ type: "token", text: "B keeps " }));
    });
    await waitFor(() => expect([t("A").runId, t("B").live?.text]).toEqual(["rA", "B keeps "]));

    await act(() => chat.stop("A"));
    expect(chatPipes.A!.aborted).toBe(true);
    expect(calls.some((c) => c.method === "POST" && c.url.endsWith("/ai/runs/rA/cancel"))).toBe(true);
    expect(t("A")).toMatchObject({ busy: false, live: null, stopped: true, runStatus: "cancelled" });

    expect(chatPipes.B!.aborted).toBe(false);
    act(() => chatPipes.B!.push(b({ type: "token", text: "going" })));
    await waitFor(() => expect(t("B").live?.text).toBe("B keeps going"));
    expect(t("B")).toMatchObject({ busy: true });
    expect(calls.filter((c) => c.url.includes("/cancel"))).toHaveLength(1);
  });

  it("a stop pressed before the run is known still cancels that run once it is", async () => {
    routeChats();
    route("POST", /\/ai\/runs\/rA\/cancel$/, () => json(run("rA", "A", "cancelled")));
    route("GET", /\/ai\/threads\/A$/, () => json(detail("A")));
    await chat.load("A");
    await chat.send("A", "never mind");
    await act(() => chat.stop("A")); // no event yet: the run id is unknown
    expect(t("A")).toMatchObject({ busy: false, stopped: true });
    expect(chatPipes.A!.aborted).toBe(false);

    const a = stamper("A", "rA");
    act(() => chatPipes.A!.push(a({ type: "run", status: "running" }), a({ type: "token", text: "should not show" })));
    await waitFor(() => expect(chatPipes.A!.aborted).toBe(true));
    await waitFor(() => expect(calls.some((c) => c.url.endsWith("/ai/runs/rA/cancel"))).toBe(true));
    expect(t("A").live).toBeNull();
  });

  it("shows the provider-busy notice while waiting, then clears it when text arrives", async () => {
    routeChats();
    route("GET", /\/ai\/threads\/A$/, () => json(detail("A")));
    await chat.load("A");
    await chat.send("A", "hi");
    const a = stamper("A", "rA");
    act(() => chatPipes.A!.push(a({ type: "run", status: "running" }), a({ type: "notice", message: "The model provider is busy. Retrying in 12s…" })));
    await waitFor(() => expect(t("A").live?.notice).toMatch(/busy/));
    act(() => chatPipes.A!.push(a({ type: "token", text: "Here" })));
    await waitFor(() => expect(t("A").live).toMatchObject({ text: "Here", notice: null }));
  });

  it("drops events that belong to another conversation, a stale run, or were already applied", async () => {
    routeChats();
    route("GET", /\/ai\/threads\/A$/, () => json(detail("A")));
    await chat.load("A");
    await chat.send("A", "hi");
    const a = stamper("A", "rA");
    const run0 = a({ type: "run", status: "running" });
    const tok1 = a({ type: "token", text: "one " });
    act(() => {
      chatPipes.A!.push(run0, tok1);
      chatPipes.A!.push({ type: "token", text: "LEAK ", thread_id: "B", run_id: "rB", seq: 9 }); // other thread
      chatPipes.A!.push({ type: "token", text: "STALE ", thread_id: "A", run_id: "old", seq: 9 }); // old run
      chatPipes.A!.push(tok1); // replayed after a reconnect
      chatPipes.A!.push(a({ type: "token", text: "two" }));
    });
    await waitFor(() => expect(t("A").live?.text).toBe("one two"));
  });

  it("restores a conversation after a reload and re-attaches to its run, replaying missed events", async () => {
    route("GET", /\/ai\/threads\/A$/, () =>
      json(detail("A", { messages: [{ id: "u1", role: "user", content: "earlier question", sources: null, run_id: null, created_at: "" }], active_run: run("rA", "A", "running") })),
    );
    const replay = new Pipe();
    route("GET", /\/ai\/runs\/rA\/stream\?after=-1$/, () => replay);
    const { result } = renderHook(() => useChat("A"), { wrapper });
    await waitFor(() => expect(result.current.state.busy).toBe(true));
    const a = stamper("A", "rA");
    act(() => replay.push(a({ type: "run", status: "running" }), a({ type: "token", text: "Replayed " }), a({ type: "token", text: "and live." })));
    await waitFor(() => expect(result.current.state.live?.text).toBe("Replayed and live."));
    act(() => replay.push(a({ type: "message", message_id: "m1", content: "Replayed and live.", sources: [] }), a({ type: "done", status: "completed", usage: {} })));
    replay.end();
    await waitFor(() => expect(result.current.state.busy).toBe(false));
    expect(result.current.state.messages.map((m) => m.content)).toEqual(["earlier question", "Replayed and live."]);
  });

  it("shows a stopped or failed last request after a reload, with retry", async () => {
    const u = { id: "u1", role: "user" as const, content: "q", sources: null, run_id: null, created_at: "" };
    route("GET", /\/ai\/threads\/F$/, () => json(detail("F", { messages: [u], last_run: { ...run("r", "F", "failed"), error: "interrupted" } })));
    route("GET", /\/ai\/threads\/S$/, () => json(detail("S", { messages: [u], last_run: run("r", "S", "cancelled") })));
    await chat.load("F");
    await chat.load("S");
    expect(t("F").error).toMatch(/interrupted/);
    expect(t("S")).toMatchObject({ stopped: true, error: null });
  });

  it("keeps a failure in its own thread and retries it without resending the message", async () => {
    routeChats();
    for (const id of ["A", "B"]) {
      route("GET", new RegExp(`/ai/threads/${id}$`), () => json(detail(id)));
      await chat.load(id);
    }
    await chat.send("A", "will fail");
    await chat.send("B", "will work");
    const a = stamper("A", "rA");
    const b = stamper("B", "rB");
    act(() => {
      chatPipes.A!.push(a({ type: "run", status: "running" }), a({ type: "error", code: "AI_RUN_FAILED", message: "The assistant ran into a problem." }), a({ type: "done", status: "failed", usage: {} }));
      chatPipes.B!.push(b({ type: "run", status: "running" }), b({ type: "token", text: "fine" }));
    });
    chatPipes.A!.end();
    await waitFor(() => expect(t("A").busy).toBe(false));
    expect(t("A").error).toMatch(/ran into a problem/);
    expect(t("B")).toMatchObject({ busy: true, error: null });
    expect(t("A").messages.map((m) => m.content)).toEqual(["will fail"]); // nothing lost

    act(() => chat.retry("A"));
    const retryCall = calls.filter((c) => c.url.endsWith("/ai/chat")).at(-1)!;
    expect(retryCall.json).toEqual({ thread_id: "A", retry: true });
    expect(t("A")).toMatchObject({ busy: true, error: null });
    expect(t("A").messages).toHaveLength(1);
  });

  it("follows the resumed stream after an approval (its events are numbered from 0 again)", async () => {
    routeChats();
    const resumed = new Pipe();
    route("POST", /\/ai\/approve$/, () => resumed);
    route("GET", /\/ai\/threads\/A$/, () => json(detail("A")));
    await chat.load("A");
    await chat.send("A", "make a task");
    const first = stamper("A", "rA");
    act(() =>
      chatPipes.A!.push(
        first({ type: "run", status: "running" }),
        first({ type: "token", text: "Proposing" }),
        first({ type: "approval_required", approval_id: "ap1", proposals: [{ call_id: "c1", tool_name: "create_task", provider: "notely", risk: "write", summary: "Create task", arguments: {} }] }),
        first({ type: "done", status: "waiting_for_approval", usage: {} }),
      ),
    );
    chatPipes.A!.end();
    await waitFor(() => expect(t("A").approval?.approval_id).toBe("ap1"));

    act(() => chat.decide("A", ["c1"]));
    const second = stamper("A", "rA"); // same run, a new stream: seq restarts
    act(() => resumed.push(second({ type: "run", status: "running" }), second({ type: "message", message_id: "m1", content: "Created.", sources: [] }), second({ type: "done", status: "completed", usage: {} })));
    resumed.end();
    await waitFor(() => expect(t("A").runStatus).toBe("completed"));
    expect(t("A").messages.at(-1)?.content).toBe("Created.");
  });

  it("when the server says the thread is already working, shows that run instead of failing", async () => {
    route("GET", /\/ai\/threads\/A$/, () => json(detail("A")));
    await chat.load("A");
    route("POST", /\/ai\/chat$/, () => json({ error: { code: "RUN_IN_PROGRESS", message: "Still working.", details: {} } }, 409));
    route("GET", /\/ai\/threads\/A$/, () => json(detail("A", { active_run: run("rX", "A", "running") })));
    const attached = new Pipe();
    route("GET", /\/ai\/runs\/rX\/stream/, () => attached);
    await chat.send("A", "double send");
    await waitFor(() => expect(t("A").runId).toBe("rX"));
    expect(t("A").messages.map((m) => m.content)).not.toContain("double send");
    expect(t("A")).toMatchObject({ busy: true, error: null });
  });
});
