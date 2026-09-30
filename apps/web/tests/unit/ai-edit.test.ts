import { describe, expect, it } from "vitest";

import { textToContent } from "@/features/notes/components/ai-edit-toolbar";
import { changeStats, diffWords } from "@/lib/text-diff";

describe("diffWords", () => {
  it("marks only the words that changed", () => {
    const parts = diffWords("we ships on friday", "We ship on Friday.");
    expect(parts).toEqual([
      { type: "del", text: "we ships" },
      { type: "add", text: "We ship" },
      { type: "same", text: " on " },
      { type: "del", text: "friday" },
      { type: "add", text: "Friday." },
    ]);
    expect(changeStats(parts)).toEqual({ added: 3, removed: 3 });
  });

  it("reports identical text as unchanged", () => {
    expect(diffWords("Same text.", "Same text.")).toEqual([{ type: "same", text: "Same text." }]);
  });

  it("falls back to replace-all for huge inputs", () => {
    const big = "word ".repeat(3000);
    const parts = diffWords(big, big + "extra");
    expect(parts.map((p) => p.type)).toEqual(["del", "add"]);
  });

  it("reconstructs both sides exactly", () => {
    const a = "The quick brown fox, jumps over the lazy dog.";
    const b = "A quick red fox jumps over the dog!";
    const parts = diffWords(a, b);
    expect(parts.filter((p) => p.type !== "add").map((p) => p.text).join("")).toBe(a);
    expect(parts.filter((p) => p.type !== "del").map((p) => p.text).join("")).toBe(b);
  });
});

describe("textToContent", () => {
  it("keeps a one-line suggestion inline", () => {
    expect(textToContent("  Hello there. ", true)).toEqual([{ type: "text", text: "Hello there." }]);
  });

  it("turns paragraphs and lists into blocks", () => {
    const content = textToContent("Intro line\nsecond line\n\n- one\n- two\n\n1. first\n2. second", true);
    expect(content.map((c) => c.type)).toEqual(["paragraph", "bulletList", "orderedList"]);
    expect(content[0]!.content!.map((c) => c.type)).toEqual(["text", "hardBreak", "text"]);
    expect(content[1]!.content![1]!.content![0]!.content![0]!.text).toBe("two");
    expect(content[2]!.content![0]!.content![0]!.content![0]!.text).toBe("first");
  });

  it("returns nothing for blank text", () => {
    expect(textToContent("  \n ", false)).toEqual([]);
  });
});
