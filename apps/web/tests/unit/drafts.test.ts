import { clearDraft, readDraft, shouldRestoreDraft, writeDraft } from "@/features/notes/drafts";
import type { TipTapDoc } from "@/lib/api/types";

const doc = (text: string): TipTapDoc => ({
  type: "doc",
  content: [{ type: "paragraph", content: [{ type: "text", text }] }],
});

describe("drafts", () => {
  beforeEach(() => window.localStorage.clear());

  it("round-trips through localStorage and clears", () => {
    writeDraft("n1", { title: "T", content_json: doc("a"), base_version: 3 });
    const draft = readDraft("n1");
    expect(draft?.title).toBe("T");
    expect(draft?.base_version).toBe(3);
    expect(typeof draft?.saved_at).toBe("number");
    clearDraft("n1");
    expect(readDraft("n1")).toBeNull();
  });

  it("ignores corrupt entries", () => {
    window.localStorage.setItem("notely:draft:n2", "{not json");
    expect(readDraft("n2")).toBeNull();
  });

  it("restores only when based on the current server version and different", () => {
    const server = doc("server");
    expect(shouldRestoreDraft(null, 1, server, "x")).toBe(false);
    const same = { title: "x", content_json: server, base_version: 1, saved_at: 0 };
    expect(shouldRestoreDraft(same, 1, server, "x")).toBe(false);
    const changed = { ...same, content_json: doc("local") };
    expect(shouldRestoreDraft(changed, 1, server, "x")).toBe(true);
    // Stale draft (server moved on) is never auto-restored over newer content.
    expect(shouldRestoreDraft(changed, 2, server, "x")).toBe(false);
  });
});
