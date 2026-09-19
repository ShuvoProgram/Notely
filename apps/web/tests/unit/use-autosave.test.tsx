import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";

import { useAutosave } from "@/features/notes/use-autosave";
import type { Note, TipTapDoc } from "@/lib/api/types";

const doc = (text: string): TipTapDoc => ({ type: "doc", content: [{ type: "paragraph", content: [{ type: "text", text }] }] });

const note: Note = {
  id: "n1",
  title: "Hello",
  excerpt: "",
  folder_id: null,
  tags: [],
  is_favorite: false,
  archived_at: null,
  deleted_at: null,
  version: 1,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  content_json: doc("body"),
  plain_text: "body",
  summary: null,
  metadata: {},
};

function json(status: number, body: unknown) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function wrapper({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe("useAutosave", () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    window.localStorage.clear();
  });
  afterEach(() => vi.useRealTimers());

  it("debounces, sends expected_version, and bumps the version on success", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(json(200, { data: { ...note, version: 2 }, meta: {} }));
    const { result } = renderHook(() => useAutosave(note), { wrapper });

    act(() => result.current.queue({ title: "A" }));
    act(() => result.current.queue({ title: "AB" }));
    expect(result.current.status).toBe("dirty");
    expect(fetchSpy).not.toHaveBeenCalled();
    // The draft mirror is written immediately.
    expect(JSON.parse(window.localStorage.getItem("notely:draft:n1") ?? "{}").title).toBe("AB");

    await act(async () => {
      vi.advanceTimersByTime(1000);
    });
    await waitFor(() => expect(result.current.status).toBe("saved"));
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const body = JSON.parse(fetchSpy.mock.calls[0]![1]!.body as string);
    expect(body).toEqual({ title: "AB", expected_version: 1 });
    expect(result.current.version).toBe(2);
    expect(window.localStorage.getItem("notely:draft:n1")).toBeNull();
  });

  it("surfaces a version conflict and keeps the local change", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      json(409, { error: { code: "NOTE_VERSION_CONFLICT", message: "changed", details: { current_version: 5 } } }),
    );
    const { result } = renderHook(() => useAutosave(note), { wrapper });
    act(() => result.current.queue({ content_json: doc("mine") }));
    await act(async () => {
      vi.advanceTimersByTime(1000);
    });
    await waitFor(() => expect(result.current.status).toBe("conflict"));
    expect(result.current.conflictVersion).toBe(5);
    expect(JSON.parse(window.localStorage.getItem("notely:draft:n1") ?? "{}").content_json).toEqual(doc("mine"));
  });

  it("goes offline on network failure and saves an empty title", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockRejectedValueOnce(new TypeError("network")).mockResolvedValue(json(200, { data: { ...note, title: "", version: 2 }, meta: {} }));
    const { result } = renderHook(() => useAutosave(note), { wrapper });
    act(() => result.current.queue({ title: "" }));
    await act(async () => {
      vi.advanceTimersByTime(1000);
    });
    await waitFor(() => expect(result.current.status).toBe("offline"));
    // Retry: an empty title is still a real change and must be sent.
    await act(async () => {
      await result.current.flush();
    });
    await waitFor(() => expect(result.current.status).toBe("saved"));
    expect(JSON.parse(fetchSpy.mock.calls[1]![1]!.body as string).title).toBe("");
  });
});
