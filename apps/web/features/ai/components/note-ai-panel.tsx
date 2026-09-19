"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { Editor } from "@tiptap/react";
import { Check, Copy, ListChecks, Loader2, Replace, Sparkles, TextQuote, WandSparkles, X } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Textarea } from "@/components/ui/textarea";
import { aiApi } from "@/features/ai/api";
import { Markdown } from "@/features/ai/components/chat-panel";
import { messageFor } from "@/features/auth/components/auth-form-error";
import { tasksApi } from "@/features/tasks/api";
import { ApiError } from "@/lib/api/client";
import type { ExtractedTask, NoteAIAction } from "@/lib/api/types";
import { cn } from "@/lib/utils";

const ACTIONS: { id: NoteAIAction; label: string; icon: React.ElementType; description: string }[] = [
  { id: "summarize", label: "Summarize", icon: TextQuote, description: "A short summary of this note" },
  { id: "improve", label: "Improve writing", icon: WandSparkles, description: "Clearer, tighter, same meaning" },
  { id: "key_points", label: "Key points", icon: ListChecks, description: "The essentials as bullets" },
  { id: "extract_tasks", label: "Extract tasks", icon: Check, description: "Action items you can add to Tasks" },
];

interface PanelState {
  action: NoteAIAction;
  status: "streaming" | "done" | "error";
  text: string;
  tasks: ExtractedTask[] | null;
  error: string | null;
}

export function NoteAIMenu({ onPick, disabled }: { onPick: (action: NoteAIAction) => void; disabled?: boolean }) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="sm" disabled={disabled} className="gap-1.5 border-ai/40 text-ai hover:bg-ai-soft hover:text-ai">
          <Sparkles className="size-3.5" aria-hidden /> Ask AI
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-64">
        {ACTIONS.map((a) => (
          <DropdownMenuItem key={a.id} onSelect={() => onPick(a.id)}>
            <a.icon aria-hidden />
            <div className="flex flex-col">
              <span>{a.label}</span>
              <span className="text-xs text-muted-foreground">{a.description}</span>
            </div>
          </DropdownMenuItem>
        ))}
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => onPick("custom")}>
          <Sparkles aria-hidden /> Ask AI…
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

/**
 * Suggestion panel: streams the model's output as a *preview*. The note only changes when the
 * user clicks Insert or Replace; AI never silently rewrites user-authored content.
 */
export function NoteAIPanel({ noteId, action, editor, onClose }: { noteId: string; action: NoteAIAction; editor: Editor | null; onClose: () => void }) {
  const [instruction, setInstruction] = React.useState("");
  const [panel, setPanel] = React.useState<PanelState | null>(null);
  const abortRef = React.useRef<AbortController | null>(null);
  const queryClient = useQueryClient();

  const run = React.useCallback(
    async (act: NoteAIAction, instr?: string) => {
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      const selection = editor && !editor.state.selection.empty ? editor.state.doc.textBetween(editor.state.selection.from, editor.state.selection.to, "\n") : undefined;
      setPanel({ action: act, status: "streaming", text: "", tasks: null, error: null });
      try {
        await aiApi.noteAction(
          { note_id: noteId, action: act, instruction: instr, selection },
          (event) => {
            setPanel((p) => {
              if (!p) return p;
              switch (event.type) {
                case "token":
                  return { ...p, text: p.text + event.text };
                case "tasks":
                  return { ...p, tasks: event.tasks };
                case "done":
                  return { ...p, status: "done", text: event.content };
                case "error":
                  return { ...p, status: "error", error: event.message };
                default:
                  return p;
              }
            });
          },
          controller.signal,
        );
      } catch (error) {
        if (!controller.signal.aborted) setPanel((p) => (p ? { ...p, status: "error", error: error instanceof ApiError ? error.message : messageFor(error) } : p));
      }
    },
    [editor, noteId],
  );

  React.useEffect(() => {
    if (action !== "custom") void run(action);
    return () => abortRef.current?.abort();
  }, [action, run]);

  const addTasks = useMutation({
    mutationFn: (tasks: ExtractedTask[]) => tasksApi.createMany(tasks.map((t) => ({ ...t, note_id: noteId, source: "ai" as const }))),
    onSuccess: (created) => {
      queryClient.invalidateQueries({ queryKey: ["tasks"] });
      toast.success(`Added ${created.length} task${created.length === 1 ? "" : "s"}`);
      onClose();
    },
    onError: (e) => toast.error(messageFor(e)),
  });

  const [selectedTasks, setSelectedTasks] = React.useState<Set<number> | null>(null);
  const tasks = panel?.tasks ?? [];
  const selected = selectedTasks ?? new Set(tasks.map((_, i) => i));

  const insertAtEnd = () => {
    if (!editor || !panel) return;
    editor.chain().focus("end").insertContent(`\n${panel.text}`).run();
    toast.success("Inserted at the end of the note");
    onClose();
  };
  const replaceAll = () => {
    if (!editor || !panel) return;
    if (!editor.state.selection.empty) {
      editor.chain().focus().deleteSelection().insertContent(panel.text).run();
      toast.success("Replaced the selection");
    } else {
      editor.chain().focus().selectAll().deleteSelection().insertContent(panel.text).run();
      toast.success("Replaced the note body");
    }
    onClose();
  };
  const copy = async () => {
    if (!panel) return;
    await navigator.clipboard.writeText(panel.text);
    toast.success("Copied");
  };

  const label = ACTIONS.find((a) => a.id === (panel?.action ?? action))?.label ?? "Ask AI";

  return (
    <aside aria-label="AI suggestion" className="mb-6 rounded-xl border border-ai/40 bg-card shadow-sm">
      <header className="flex items-center justify-between border-b px-4 py-2.5">
        <h3 className="flex items-center gap-2 text-sm font-semibold">
          <Sparkles className="size-4 text-ai" aria-hidden /> {label}
          {panel?.status === "streaming" ? <Loader2 className="size-3.5 animate-spin text-muted-foreground" aria-hidden /> : null}
        </h3>
        <Button variant="ghost" size="icon-sm" aria-label="Close suggestion" onClick={onClose}>
          <X aria-hidden />
        </Button>
      </header>

      {action === "custom" && !panel ? (
        <form
          className="space-y-3 p-4"
          onSubmit={(e) => {
            e.preventDefault();
            if (instruction.trim()) void run("custom", instruction.trim());
          }}
        >
          <Textarea aria-label="What should the AI do with this note?" placeholder="e.g. Turn this into a friendly email to the team" value={instruction} onChange={(e) => setInstruction(e.target.value)} rows={2} autoFocus />
          <div className="flex justify-end">
            <Button type="submit" size="sm" disabled={!instruction.trim()}>
              Run
            </Button>
          </div>
        </form>
      ) : null}

      {panel ? (
        <div className="p-4">
          {panel.status === "error" ? (
            <p role="alert" className="text-sm text-destructive">
              {panel.error}
            </p>
          ) : panel.action === "extract_tasks" ? (
            panel.status === "streaming" ? (
              <p className="text-sm text-muted-foreground">Looking for action items…</p>
            ) : tasks.length ? (
              <ul className="space-y-1.5">
                {tasks.map((t, i) => (
                  <li key={`${t.title}-${i}`} className="flex items-start gap-2 rounded-md bg-secondary/60 px-3 py-2 text-sm">
                    <input
                      id={`xt-${i}`}
                      type="checkbox"
                      className="mt-0.5 size-4 accent-[var(--ai)]"
                      checked={selected.has(i)}
                      onChange={(e) =>
                        setSelectedTasks(() => {
                          const next = new Set(selected);
                          if (e.target.checked) next.add(i);
                          else next.delete(i);
                          return next;
                        })
                      }
                    />
                    <label htmlFor={`xt-${i}`} className="flex-1">
                      {t.title}
                      <span className="ml-2 text-xs text-muted-foreground">
                        {t.due_date ? `due ${t.due_date}` : ""}
                        {t.priority !== "none" ? ` · ${t.priority}` : ""}
                      </span>
                    </label>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-muted-foreground">No action items found in this note.</p>
            )
          ) : (
            <div className={cn("max-h-72 overflow-y-auto", panel.status === "streaming" && "after:animate-pulse after:content-['▍']")}>
              {panel.text ? <Markdown text={panel.text} /> : <p className="text-sm text-muted-foreground">Thinking…</p>}
            </div>
          )}

          {panel.status === "done" ? (
            <div className="mt-4 flex flex-wrap justify-end gap-2">
              {panel.action === "extract_tasks" ? (
                tasks.length ? (
                  <Button size="sm" disabled={selected.size === 0 || addTasks.isPending} onClick={() => addTasks.mutate(tasks.filter((_, i) => selected.has(i)))}>
                    <Check aria-hidden /> Add {selected.size} task{selected.size === 1 ? "" : "s"}
                  </Button>
                ) : null
              ) : (
                <>
                  <Button variant="outline" size="sm" onClick={() => void copy()}>
                    <Copy aria-hidden /> Copy
                  </Button>
                  <Button variant="outline" size="sm" onClick={insertAtEnd} disabled={!editor}>
                    Insert below
                  </Button>
                  <Button size="sm" onClick={replaceAll} disabled={!editor}>
                    <Replace aria-hidden /> Replace
                  </Button>
                </>
              )}
            </div>
          ) : null}
        </div>
      ) : null}
    </aside>
  );
}
