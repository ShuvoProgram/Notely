import { ApiError } from "@/lib/api/client";
import { streamPost } from "@/lib/api/sse";

function sseResponse(frames: string[], status = 200) {
  const encoder = new TextEncoder();
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const f of frames) controller.enqueue(encoder.encode(f));
      controller.close();
    },
  });
  return new Response(stream, { status, headers: { "Content-Type": "text/event-stream" } });
}

describe("streamPost", () => {
  it("parses frames even when chunks split mid-frame", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      sseResponse(['event: run\ndata: {"type":"run","run_id":"r1"}\n\nevent: tok', 'en\ndata: {"type":"token","text":"Hel"}\n\ndata: {"type":"token",', '"text":"lo"}\n\n']),
    );
    const events: { type: string }[] = [];
    await streamPost<{ type: string }>("/ai/chat", { body: { message: "x" }, onEvent: (e) => events.push(e) });
    expect(events).toEqual([
      { type: "run", run_id: "r1" },
      { type: "token", text: "Hel" },
      { type: "token", text: "lo" },
    ]);
  });

  it("throws a typed ApiError for non-2xx responses", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ error: { code: "RATE_LIMITED", message: "slow down", details: {} } }), { status: 429, headers: { "Content-Type": "application/json" } }),
    );
    const err = await streamPost("/ai/chat", { body: {}, onEvent: () => {} }).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).code).toBe("RATE_LIMITED");
  });

  it("skips malformed frames without aborting the stream", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(sseResponse(["data: {not json}\n\n", 'data: {"type":"done"}\n\n']));
    const events: { type: string }[] = [];
    await streamPost<{ type: string }>("/x", { body: {}, onEvent: (e) => events.push(e) });
    expect(events).toEqual([{ type: "done" }]);
  });
});
