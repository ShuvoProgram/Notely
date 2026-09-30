"use client";

import type { JSONContent } from "@tiptap/react";
import type { Editor } from "@tiptap/react";
import * as React from "react";
import { toast } from "sonner";

import { Check, ChevronDown, Copy, Loader2, RotateCcw, Sparkles, Square, WandSparkles, X } from "@/components/icons";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Kbd } from "@/components/ui/kbd";
import { messageFor } from "@/features/auth/components/auth-form-error";
import { aiEditTargetKey, getAIEditTarget } from "@/features/notes/extensions/ai-edit-target";
import { streamPost } from "@/lib/api/sse";
import { playSfx } from "@/lib/sfx/player";
import { changeStats, diffWords } from "@/lib/text-diff";
import { cn } from "@/lib/utils";

type Operation =
  | "improve"
  | "fix_grammar"
  | "rewrite"
  | "concise"
  | "expand"
  | "tone"
  | "summarize"
  | "translate"
  | "explain"
  | "continue"
  | "custom";
type Mode = "replace" | "insert_after" | "explain";

interface Options {
  tone?: string;
  language?: string;
  instruction?: string;
}

const LABEL: Record<Operation, string> = {
  improve: "Improve writing",
  fix_grammar: "Fix grammar",
  rewrite: "Rewrite",
  concise: "Make concise",
  expand: "Expand",
  tone: "Change tone",
  summarize: "Summarize",
  translate: "Translate",
  explain: "Explain",
  continue: "Continue writing",
  custom: "Custom edit",
};
const TONES = ["Professional", "Friendly", "Confident", "Casual", "Formal", "Empathetic"];
const LANGUAGES = ["English", "Spanish", "French", "German", "Portuguese", "Italian", "Hindi", "Bengali", "Chinese", "Japanese", "Arabic"];
const CONTEXT_CHARS = 1500;

interface Job {
  id: number;
  op: Operation;
  opts: Options;
  mode: Mode;
  original: string;
  text: string;
  status: "streaming" | "done" | "error";
  error?: string;
}

type Anchor = { top: number; left: number; below: boolean; width: number };

const isTouch = () => typeof window !== "undefined" && window.matchMedia("(pointer: coarse)").matches;

function selectionText(editor: Editor, from: number, to: number): string {
  return editor.state.doc.textBetween(from, to, "\n\n", "\n");
}

/** Plain model text → editor content. Blank lines separate blocks; "- " / "1. " lines become lists. */
export function textToContent(text: string, inline: boolean): JSONContent[] {
  const clean = text.replace(/\r\n/g, "\n").trim();
  if (!clean) return [];
  if (inline && !clean.includes("\n")) return [{ type: "text", text: clean }];
  const blocks = clean.split(/\n{2,}/);
  return blocks.map((block): JSONContent => {
    const lines = block.split("\n");
    const bullet = /^\s*[-*•]\s+/;
    const numbered = /^\s*\d+[.)]\s+/;
    if (lines.every((l) => bullet.test(l)) || lines.every((l) => numbered.test(l))) {
      const ordered = numbered.test(lines[0] ?? "");
      return {
        type: ordered ? "orderedList" : "bulletList",
        content: lines.map((l) => ({
          type: "listItem",
          content: [{ type: "paragraph", content: [{ type: "text", text: l.replace(ordered ? numbered : bullet, "") || " " }] }],
        })),
      };
    }
    const content: JSONContent[] = [];
    lines.forEach((l, i) => {
      if (i) content.push({ type: "hardBreak" });
      if (l) content.push({ type: "text", text: l });
    });
    return { type: "paragraph", content };
  });
}

/**
 * Contextual AI editing. Select text and a small toolbar appears next to it: quick actions, a
 * "More" menu (tone, translate, explain, continue…) and a field for your own instruction
 * (Ctrl/⌘+J). The suggestion streams into a panel under the selection as a word-level diff; the
 * note is not touched until you Accept (Tab or ⌘/Ctrl+Enter), which is one undoable change.
 * Reject (Esc) leaves the original exactly as it was. The target range is tracked through other
 * edits (ai-edit-target extension), and Accept refuses if that text changed in the meantime.
 */
export function AIEditToolbar({
  editor,
  containerRef,
  noteId,
  canEdit,
}: {
  editor: Editor;
  containerRef: React.RefObject<HTMLDivElement | null>;
  noteId: string;
  canEdit: boolean;
}) {
  const [anchor, setAnchor] = React.useState<Anchor | null>(null);
  const [menuOpen, setMenuOpen] = React.useState(false);
  const [instruction, setInstruction] = React.useState("");
  const [job, setJob] = React.useState<Job | null>(null);
  const [view, setView] = React.useState<"diff" | "result">("diff");
  const toolbarRef = React.useRef<HTMLDivElement | null>(null);
  const panelRef = React.useRef<HTMLDivElement | null>(null);
  const inputRef = React.useRef<HTMLInputElement | null>(null);
  const abortRef = React.useRef<AbortController | null>(null);
  const jobSeq = React.useRef(0);
  const menuOpenRef = React.useRef(false);
  menuOpenRef.current = menuOpen;
  const jobRef = React.useRef<Job | null>(null);
  jobRef.current = job;
  // Measured so the toolbar can be kept fully inside the note on narrow screens.
  const [toolbarWidth, setToolbarWidth] = React.useState(0);
  React.useLayoutEffect(() => {
    const el = toolbarRef.current;
    if (!el) return;
    const measure = () => setToolbarWidth(el.offsetWidth);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, [anchor, job]);

  const place = React.useCallback(
    (from: number, to: number, preferBelow: boolean): Anchor | null => {
      const container = containerRef.current;
      if (!container) return null;
      const start = editor.view.coordsAtPos(from);
      const end = editor.view.coordsAtPos(to);
      const box = container.getBoundingClientRect();
      // Above the selection unless that would hit the sticky toolbar, or on touch screens, where
      // the system's own copy/paste bubble sits above the selection.
      const below = preferBelow || start.top - box.top < 64;
      const centre = (Math.min(start.left, end.left) + Math.max(start.right, end.right)) / 2 - box.left;
      return { top: below ? end.bottom - box.top + 8 : start.top - box.top - 8, left: centre, below, width: box.width };
    },
    [editor, containerRef],
  );

  // Toolbar follows the live selection.
  React.useEffect(() => {
    let raf = 0;
    const update = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        if (jobRef.current) return;
        const { from, to, empty } = editor.state.selection;
        const inToolbar = toolbarRef.current?.contains(document.activeElement) ?? false;
        if (empty || to - from < 2 || (!editor.isFocused && !inToolbar && !menuOpenRef.current)) {
          setAnchor(null);
          return;
        }
        setAnchor(place(from, to, isTouch()));
      });
    };
    editor.on("selectionUpdate", update);
    editor.on("focus", update);
    editor.on("blur", update);
    window.addEventListener("resize", update);
    return () => {
      editor.off("selectionUpdate", update);
      editor.off("focus", update);
      editor.off("blur", update);
      window.removeEventListener("resize", update);
      cancelAnimationFrame(raf);
    };
  }, [editor, place]);

  // Ctrl/⌘+J: jump to the instruction field for the current selection.
  React.useEffect(() => {
    const dom = editor.view.dom as HTMLElement;
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "j" && !editor.state.selection.empty && canEdit) {
        e.preventDefault();
        setAnchor(place(editor.state.selection.from, editor.state.selection.to, isTouch()));
        requestAnimationFrame(() => inputRef.current?.focus());
      }
    };
    dom.addEventListener("keydown", onKey);
    return () => dom.removeEventListener("keydown", onKey);
  }, [editor, place, canEdit]);

  const setTarget = React.useCallback(
    (value: { from: number; to: number; phase: "working" | "preview" } | null) => {
      editor.view.dispatch(editor.state.tr.setMeta(aiEditTargetKey, value).setMeta("addToHistory", false));
    },
    [editor],
  );

  const start = React.useCallback(
    async (op: Operation, opts: Options = {}, range?: { from: number; to: number; original: string }) => {
      const sel = range ?? { from: editor.state.selection.from, to: editor.state.selection.to, original: "" };
      const original = range?.original || selectionText(editor, sel.from, sel.to);
      if (!original.trim()) return;
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      const id = ++jobSeq.current;
      const doc = editor.state.doc;
      setTarget({ from: sel.from, to: sel.to, phase: "working" });
      setAnchor(place(sel.from, sel.to, true));
      setMenuOpen(false);
      setView("diff");
      setJob({ id, op, opts, mode: op === "explain" ? "explain" : op === "continue" ? "insert_after" : "replace", original, text: "", status: "streaming" });
      try {
        await streamPost<{ type: string; text?: string; mode?: Mode }>("/ai/edit", {
          body: {
            note_id: noteId,
            operation: op,
            selection: original,
            before: doc.textBetween(Math.max(0, sel.from - CONTEXT_CHARS), sel.from, "\n\n", "\n"),
            after: doc.textBetween(sel.to, Math.min(doc.content.size, sel.to + CONTEXT_CHARS), "\n\n", "\n"),
            ...opts,
          },
          signal: controller.signal,
          onEvent: (event) => {
            setJob((j) => {
              if (!j || j.id !== id) return j;
              if (event.type === "token") return { ...j, text: j.text + (event.text ?? "") };
              if (event.type === "done") return { ...j, text: event.text ?? j.text, mode: event.mode ?? j.mode, status: "done" };
              return j;
            });
          },
        });
        setJob((j) => (j && j.id === id && j.status === "streaming" ? { ...j, status: "done" } : j));
        const t = getAIEditTarget(editor.state);
        if (t) setTarget({ ...t, phase: "preview" });
      } catch (error) {
        if (controller.signal.aborted) return;
        setJob((j) => (j && j.id === id ? { ...j, status: "error", error: messageFor(error) } : j));
      }
    },
    [editor, noteId, place, setTarget],
  );

  const close = React.useCallback(
    (restoreSelection: boolean) => {
      abortRef.current?.abort();
      const t = getAIEditTarget(editor.state);
      setTarget(null);
      setJob(null);
      setInstruction("");
      if (restoreSelection && t) editor.chain().focus().setTextSelection({ from: t.from, to: t.to }).run();
    },
    [editor, setTarget],
  );

  const accept = React.useCallback(
    (mode: Mode = jobRef.current?.mode ?? "replace") => {
      const j = jobRef.current;
      const t = getAIEditTarget(editor.state);
      if (!j || j.status !== "done" || !j.text.trim()) return;
      if (!t || selectionText(editor, t.from, t.to) !== j.original) {
        toast.error("The selected text changed while the suggestion was being written", { description: "Nothing was replaced. Select it again to get a fresh suggestion." });
        playSfx("error");
        return;
      }
      const $from = editor.state.doc.resolve(t.from);
      const $to = editor.state.doc.resolve(t.to);
      const inline = $from.sameParent($to) && $from.parent.isTextblock;
      const chain = editor.chain().focus();
      if (mode === "replace") {
        chain.insertContentAt({ from: t.from, to: t.to }, textToContent(j.text, inline), { updateSelection: true });
      } else if (mode === "insert_after" && inline && !j.text.includes("\n")) {
        chain.insertContentAt(t.to, [{ type: "text", text: (/\s$/.test(j.original) ? "" : " ") + j.text.trim() }]);
      } else {
        // Continue / explanation as new blocks after the selection's block.
        const blockEnd = $to.depth > 0 ? $to.after($to.depth) : t.to;
        chain.insertContentAt(blockEnd, textToContent(j.text, false));
      }
      chain.command(({ tr }) => {
        tr.setMeta(aiEditTargetKey, null);
        return true;
      });
      if (!chain.run()) {
        toast.error("Couldn't apply the suggestion here.");
        return;
      }
      setJob(null);
      setInstruction("");
      playSfx("success");
      toast.success(mode === "replace" ? "Applied AI edit" : "Added to your note", {
        action: { label: "Undo", onClick: () => editor.chain().focus().undo().run() },
      });
    },
    [editor],
  );

  // Keyboard while a suggestion is showing: Tab / ⌘+Enter accept, Esc rejects (or stops).
  React.useEffect(() => {
    if (!job) return;
    const onKey = (e: KeyboardEvent) => {
      const typing = (e.target as HTMLElement | null)?.closest("input, textarea");
      if (e.key === "Escape") {
        e.preventDefault();
        e.stopPropagation();
        close(true);
      } else if (!typing && job.status === "done" && job.mode !== "explain" && canEdit && (e.key === "Tab" || (e.key === "Enter" && (e.metaKey || e.ctrlKey)))) {
        e.preventDefault();
        e.stopPropagation();
        accept();
      }
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [job, accept, close, canEdit]);

  // Keep the panel next to its text while the page scrolls or the note reflows.
  React.useEffect(() => {
    if (!job) return;
    const update = () => {
      const t = getAIEditTarget(editor.state);
      if (t) setAnchor(place(t.from, t.to, true));
    };
    editor.on("update", update);
    window.addEventListener("resize", update);
    return () => {
      editor.off("update", update);
      window.removeEventListener("resize", update);
    };
  }, [job, editor, place]);

  React.useEffect(() => () => abortRef.current?.abort(), []);

  if (!anchor) return null;
  const hint = (
    <span className="hidden items-center gap-1 text-[11px] text-muted-foreground sm:inline-flex">
      <Kbd>Tab</Kbd> accept · <Kbd>Esc</Kbd> reject
    </span>
  );

  if (job) {
    const parts = job.mode === "replace" && job.status === "done" ? diffWords(job.original, job.text) : null;
    const stats = parts ? changeStats(parts) : null;
    const unchanged = parts !== null && parts.every((p) => p.type === "same");
    const panelWidth = Math.min(560, anchor.width - 8);
    const left = Math.max(panelWidth / 2 + 4, Math.min(anchor.left, anchor.width - panelWidth / 2 - 4));
    return (
      <div
        ref={panelRef}
        role="dialog"
        aria-label={`AI suggestion: ${LABEL[job.op]}`}
        className="glass-3 animate-fade-up absolute z-30 -translate-x-1/2 rounded-2xl p-3 shadow-xl ring-1 ring-glass-border-strong"
        style={{ top: anchor.top, left, width: panelWidth }}
        onMouseDown={(e) => {
          if (!(e.target as HTMLElement).closest("input,textarea")) e.preventDefault(); // keep the editor's selection
        }}
      >
        <div className="mb-2 flex items-center gap-2 text-xs">
          <Sparkles className="size-3.5 text-ai" aria-hidden />
          <span className="font-medium">{job.op === "tone" ? `${job.opts.tone} tone` : job.op === "translate" ? `Translate to ${job.opts.language}` : job.op === "custom" ? job.opts.instruction : LABEL[job.op]}</span>
          <span className="ml-auto text-muted-foreground" aria-live="polite">
            {job.status === "streaming" ? "Writing…" : job.status === "error" ? "Failed" : stats ? (unchanged ? "No changes needed" : `+${stats.added} −${stats.removed} words`) : null}
          </span>
        </div>

        <div className="scrollbar-thin max-h-72 overflow-y-auto whitespace-pre-wrap rounded-xl bg-field/60 px-3 py-2 text-sm leading-relaxed">
          {job.status === "error" ? (
            <p role="alert" className="text-destructive">
              {job.error}
            </p>
          ) : job.status === "streaming" ? (
            <p>
              {job.text || <span className="text-muted-foreground">Thinking…</span>}
              <span className="ml-0.5 inline-block h-4 w-1.5 animate-pulse rounded-sm bg-ai align-text-bottom" aria-hidden />
            </p>
          ) : parts && view === "diff" ? (
            <p>
              {parts.map((p, i) =>
                p.type === "same" ? (
                  <span key={i}>{p.text}</span>
                ) : p.type === "del" ? (
                  <del key={i} className="rounded-sm bg-destructive/15 text-destructive decoration-destructive/60">
                    {p.text}
                  </del>
                ) : (
                  <ins key={i} className="rounded-sm bg-success/15 text-success no-underline">
                    {p.text}
                  </ins>
                ),
              )}
            </p>
          ) : job.mode === "insert_after" ? (
            <p>
              <span className="text-muted-foreground">…{job.original.slice(-80)}</span>{" "}
              <ins className="rounded-sm bg-success/15 text-success no-underline">{job.text}</ins>
            </p>
          ) : (
            <p>{job.text}</p>
          )}
        </div>

        <div className="mt-2.5 flex flex-wrap items-center gap-2">
          {job.status === "streaming" ? (
            <Button size="sm" variant="outline" onClick={() => close(true)}>
              <Square aria-hidden /> Stop
            </Button>
          ) : job.status === "error" ? (
            <>
              <Button size="sm" onClick={() => void start(job.op, job.opts, { ...(getAIEditTarget(editor.state) ?? { from: 0, to: 0 }), original: job.original })}>
                <RotateCcw aria-hidden /> Try again
              </Button>
              <Button size="sm" variant="ghost" onClick={() => close(true)}>
                Close
              </Button>
            </>
          ) : job.mode === "explain" ? (
            <>
              {canEdit ? (
                <Button size="sm" variant="outline" onClick={() => accept("explain")}>
                  Insert below
                </Button>
              ) : null}
              <Button
                size="sm"
                variant="ghost"
                onClick={() => {
                  void navigator.clipboard?.writeText(job.text);
                  toast.success("Copied");
                }}
              >
                <Copy aria-hidden /> Copy
              </Button>
              <Button size="sm" variant="ghost" onClick={() => close(true)}>
                Close
              </Button>
            </>
          ) : (
            <>
              <Button size="sm" onClick={() => accept()} disabled={unchanged || !canEdit}>
                <Check aria-hidden /> Accept
              </Button>
              <Button size="sm" variant="outline" onClick={() => close(true)}>
                <X aria-hidden /> Reject
              </Button>
              <Button size="sm" variant="ghost" onClick={() => void start(job.op, job.opts, { ...(getAIEditTarget(editor.state) ?? { from: 0, to: 0 }), original: job.original })}>
                <RotateCcw aria-hidden /> Regenerate
              </Button>
              {parts && !unchanged ? (
                <Button size="sm" variant="ghost" className="text-muted-foreground" aria-pressed={view === "result"} onClick={() => setView(view === "diff" ? "result" : "diff")}>
                  {view === "diff" ? "Show result" : "Show changes"}
                </Button>
              ) : null}
              <span className="ml-auto">{hint}</span>
            </>
          )}
        </div>
      </div>
    );
  }

  return (
    <div
      ref={toolbarRef}
      role="toolbar"
      aria-label="AI edits for the selected text"
      className={cn(
        "glass-3 animate-fade-up scrollbar-none absolute z-30 flex max-w-[calc(100%-8px)] -translate-x-1/2 items-center gap-0.5 overflow-x-auto rounded-xl p-1 shadow-lg ring-1 ring-glass-border-strong",
        !anchor.below && "-translate-y-full",
      )}
      style={{
        top: anchor.top,
        left: Math.max(toolbarWidth / 2 + 4, Math.min(anchor.left, anchor.width - toolbarWidth / 2 - 4)),
      }}
      onMouseDown={(e) => {
        if (!(e.target as HTMLElement).closest("input")) e.preventDefault(); // keep the editor selection
      }}
      onKeyDown={(e) => {
        if (e.key === "Escape") {
          setAnchor(null);
          editor.commands.focus();
        }
      }}
    >
      {canEdit ? (
        <>
          <Button size="sm" variant="ghost" onClick={() => void start("improve")} className="shrink-0 text-ai" aria-label="Improve writing">
            <WandSparkles aria-hidden /> <span className="max-sm:hidden">Improve</span>
          </Button>
          <Button size="sm" variant="ghost" onClick={() => void start("fix_grammar")} className="shrink-0">
            Fix grammar
          </Button>
          <DropdownMenu open={menuOpen} onOpenChange={setMenuOpen}>
            <DropdownMenuTrigger asChild>
              <Button size="sm" variant="ghost" className="shrink-0">
                More <ChevronDown aria-hidden />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start" className="w-52" onCloseAutoFocus={(e) => e.preventDefault()}>
              {(["rewrite", "concise", "expand", "summarize"] as const).map((op) => (
                <DropdownMenuItem key={op} onSelect={() => void start(op)}>
                  {LABEL[op]}
                </DropdownMenuItem>
              ))}
              <DropdownMenuSub>
                <DropdownMenuSubTrigger>Change tone</DropdownMenuSubTrigger>
                <DropdownMenuSubContent className="w-44">
                  {TONES.map((tone) => (
                    <DropdownMenuItem key={tone} onSelect={() => void start("tone", { tone: tone.toLowerCase() })}>
                      {tone}
                    </DropdownMenuItem>
                  ))}
                </DropdownMenuSubContent>
              </DropdownMenuSub>
              <DropdownMenuSub>
                <DropdownMenuSubTrigger>Translate</DropdownMenuSubTrigger>
                <DropdownMenuSubContent className="max-h-72 w-44">
                  {LANGUAGES.map((language) => (
                    <DropdownMenuItem key={language} onSelect={() => void start("translate", { language })}>
                      {language}
                    </DropdownMenuItem>
                  ))}
                </DropdownMenuSubContent>
              </DropdownMenuSub>
              <DropdownMenuSeparator />
              <DropdownMenuItem onSelect={() => void start("explain")}>Explain</DropdownMenuItem>
              <DropdownMenuItem onSelect={() => void start("continue")}>Continue writing</DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
          <form
            className="flex items-center"
            onSubmit={(e) => {
              e.preventDefault();
              const value = instruction.trim();
              if (value) void start("custom", { instruction: value });
            }}
          >
            <input
              ref={inputRef}
              value={instruction}
              onChange={(e) => setInstruction(e.target.value)}
              maxLength={1000}
              placeholder="Ask AI to edit…"
              aria-label="Tell AI how to edit the selection"
              className="h-7 w-28 shrink-0 rounded-md bg-transparent px-2 text-sm outline-none placeholder:text-muted-foreground focus:bg-field sm:w-40 sm:focus:w-52 [transition:width_.15s]"
            />
            {instruction.trim() ? (
              <Button type="submit" size="icon-sm" aria-label="Apply instruction">
                {job ? <Loader2 className="animate-spin" aria-hidden /> : <Sparkles aria-hidden />}
              </Button>
            ) : (
              <Kbd className="mr-1 hidden sm:inline-flex">⌘J</Kbd>
            )}
          </form>
        </>
      ) : (
        <Button size="sm" variant="ghost" onClick={() => void start("explain")} className="text-ai">
          <Sparkles aria-hidden /> Explain
        </Button>
      )}
    </div>
  );
}
