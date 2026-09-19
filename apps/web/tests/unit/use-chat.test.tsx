import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";

import { useChat } from "@/features/ai/use-chat";
import type { AIChatEvent } from "@/lib/api/types";

function sse(events: AIChatEvent[]) {
  const body = events.map((e) => `event: ${e.type}\ndata: ${JSON.stringify(e)}\n\n`).join("");
  return new Response(body, { status: 200, headers: { "Content-Type": "text/event-stream" } });
}

function wrapper({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe("useChat", () => {
  it("streams tokens, steps and a final message into state", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      sse([
        { type: "run", run_id: "r1", thread_id: "t1", status: "running" },
        { type: "step", call_id: "c1", tool: "search_notes", label: "Search notes for “x”", status: "running" },
        { type: "step", call_id: "c1", tool: "search_notes", label: "Search notes for “x”", status: "completed", result_preview: "2 result(s)" },
        { type: "token", text: "Here " },
        { type: "token", text: "you go." },
        { type: "message", message_id: "m1", content: "Here you go.", sources: [{ provider: "notely", object_id: "n1", title: "N", url: "/app/notes/n1" }] },
        { type: "done", run_id: "r1", status: "completed", usage: {} },
      ]),
    );
    const { result } = renderHook(() => useChat(null), { wrapper });
    act(() => result.current.send("find x"));
    await waitFor(() => expect(result.current.state.busy).toBe(false));
    const s = result.current.state;
    expect(s.threadId).toBe("t1");
    expect(s.messages.map((m) => [m.role, m.content])).toEqual([
      ["user", "find x"],
      ["assistant", "Here you go."],
    ]);
    expect(s.messages[1]?.sources?.[0]?.title).toBe("N");
    expect(s.live).toBeNull();
    expect(s.approval).toBeNull();
  });

  it("pauses on approval_required and resumes through /ai/approve with the chosen ids", async () => {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(
        sse([
          { type: "run", run_id: "r1", thread_id: "t1", status: "running" },
          { type: "approval_required", approval_id: "a1", run_id: "r1", proposals: [{ call_id: "c1", tool_name: "create_task", provider: "notely", risk: "write", summary: "Create task “A”", arguments: { title: "A" } }] },
          { type: "done", run_id: "r1", status: "waiting_for_approval", usage: {} },
        ]),
      )
      .mockResolvedValueOnce(
        sse([
          { type: "run", run_id: "r1", thread_id: "t1", status: "running" },
          { type: "step", call_id: "c1", tool: "create_task", label: "Create task “A”", status: "completed" },
          { type: "message", message_id: "m2", content: "Created.", sources: [] },
          { type: "done", run_id: "r1", status: "completed", usage: {} },
        ]),
      );
    const { result } = renderHook(() => useChat(null), { wrapper });
    act(() => result.current.send("make a task"));
    await waitFor(() => expect(result.current.state.approval?.approval_id).toBe("a1"));
    expect(result.current.state.runStatus).toBe("waiting_for_approval");
    expect(result.current.state.busy).toBe(false);

    act(() => result.current.decide(["c1"]));
    await waitFor(() => expect(result.current.state.runStatus).toBe("completed"));
    const approveCall = fetchSpy.mock.calls[1]!;
    expect(String(approveCall[0])).toBe("/api/v1/ai/approve");
    expect(JSON.parse(approveCall[1]!.body as string)).toEqual({ run_id: "r1", approval_id: "a1", approved_call_ids: ["c1"], reject_all: false });
    expect(result.current.state.messages.at(-1)?.content).toBe("Created.");
  });

  it("surfaces stream errors without leaving the UI busy", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(sse([{ type: "error", code: "AI_RUN_FAILED", message: "The assistant ran into a problem." }]));
    const { result } = renderHook(() => useChat(null), { wrapper });
    act(() => result.current.send("hi"));
    await waitFor(() => expect(result.current.state.error).toMatch(/ran into a problem/));
    expect(result.current.state.busy).toBe(false);
  });
});
