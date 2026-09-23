"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { Editor } from "@tiptap/react";
import { ArrowUp, Check, Copy, ListChecks, Loader2, MessageSquareText, RefreshCw, Replace, Sparkles, TextQuote, WandSparkles, X } from "@/components/icons";
import * as React from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
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
import { playSfx } from "@/lib/sfx/player";
import type { ExtractedTask, NoteAIAction } from "@/lib/api/types";
import { cn } from "@/lib/utils";

export const NOTE_AI_ACTIONS: { id: NoteAIAction; label: string; icon: React.ElementType; description: string }[] = [
  { id: "summarize", label: "Summarize this note", icon: TextQuote, description: "A short summary you can paste anywhere" },
  { id: "extract_tasks", label: "Extract action items", icon: Check, description: "Tasks with dates, ready to add" },
  { id: "improve", label: "Improve writing", icon: WandSparkles, description: "Clearer and tighter, same meaning" },
  { id: "key_points", label: "Turn into key points", icon: ListChecks, description: "The essentials as bullets" },
];

const LABELS: Record<NoteAIAction, string> = {
  summarize: "Summary",
  improve: "Improve writing",
  key_points: "Key points",
  extract_tasks: "Tasks extracted",
  custom: "Ask AI",
};

interface PanelState {
  action: NoteAIAction;
  instruction?: string;
  /** The text the action ran on (selection or whole note); shown as "Original" for rewrites. */
  original: string | null;
  status: "streaming" | "done" | "error";
  text: string;
  tasks: ExtractedTask[] | null;
  error: string | null;
}

export function NoteAIMenu({ onPick, disabled, label }: { onPick: (action: NoteAIAction) => void; disabled?: boolean; label?: string }) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="sm" disabled={disabled} aria-label={label} className="glass-2 gap-1.5 rounded-lg border-ai/40 bg-ai-soft text-ai hover:bg-ai/20 hover:text-ai">
          <Sparkles className="size-3.5" aria-hidden /> Ask AI
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-64">
        {NOTE_AI_ACTIONS.map((a) => (
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
          <MessageSquareText aria-hidden /> Ask a custom question…
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

/**
 * Suggestion card: streams the model's output as a *preview* beside the original text. The
 * note only changes when the user clicks Insert or Replace; AI never silently rewrites
 * user-authored content. Rendered above the editor on small screens and in the assistant rail
 * on wide ones.
 */
export function NoteAIPanel({ noteId, action, editor, onClose, className }: { noteId: string; action: NoteAIAction; editor: Editor | null; onClose: () => void; className?: string }) {
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
      const original = selection ?? (act === "improve" ? (editor?.getText() ?? null) : null);
      setPanel({ action: act, instruction: instr, original, status: "streaming", text: "", tasks: null, error: null });
      playSfx("ai-start");
      try {
        await aiApi.noteAction(
          { note_id: noteId, action: act, instruction: instr, selection },
          (event) => {
            if (event.type === "done") playSfx("ai-done");
            else if (event.type === "error") playSfx("error");
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
        if (!controller.signal.aborted) {
          playSfx("error");
          setPanel((p) => (p ? { ...p, status: "error", error: error instanceof ApiError ? error.message : messageFor(error) } : p));
        }
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
      playSfx("task-complete");
      queryClient.invalidateQueries({ queryKey: ["tasks"] });
      toast.success(`Added ${created.length} task${created.length === 1 ? "" : "s"}`);
      onClose();
    },
    onError: (e) => toast.error(messageFor(e)),
  });

  const [selectedTasks, setSelectedTasks] = React.useState<Set<number> | null>(null);
  const tasks = panel?.tasks ?? [];
  const selected = selectedTasks ?? new Set(tasks.map((_, i) => i));
  const hasSelection = Boolean(editor && !editor.state.selection.empty);

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

  const label = LABELS[panel?.action ?? action];
  const streaming = panel?.status === "streaming";

  return (
    <aside aria-label="AI suggestion" aria-busy={streaming} className={cn("glass-2 animate-fade-up overflow-hidden rounded-2xl", className)}>
      <header className="flex items-center gap-2 border-b border-glass-border px-4 py-3">
        <span className="grid size-7 place-items-center rounded-lg bg-ai-soft text-ai">
          <Sparkles className="size-4" aria-hidden />
        </span>
        <h3 className="text-sm font-semibold">{label}</h3>
        {streaming ? (
          <Badge variant="secondary" className="gap-1 font-normal text-muted-foreground">
            <Loader2 className="animate-spin" aria-hidden /> Working
          </Badge>
        ) : panel?.status === "done" ? (
          <Badge variant="secondary" className="font-normal text-success">
            Ready
          </Badge>
        ) : null}
        <Button variant="ghost" size="icon-sm" aria-label="Close suggestion" onClick={onClose} className="ml-auto">
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
          <p className="text-xs text-muted-foreground">{hasSelection ? "Applies to the selected text." : "Applies to the whole note."}</p>
          <div className="relative">
            <Textarea
              aria-label="What should the AI do with this note?"
              placeholder="e.g. Turn this into a friendly email to the team"
              value={instruction}
              onChange={(e) => setInstruction(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey && instruction.trim()) {
                  e.preventDefault();
                  void run("custom", instruction.trim());
                }
              }}
              rows={3}
              autoFocus
              className="pr-11"
            />
            <Button type="submit" size="icon-sm" aria-label="Run" disabled={!instruction.trim()} className="absolute bottom-2 right-2 rounded-full">
              <ArrowUp aria-hidden />
            </Button>
          </div>
        </form>
      ) : null}

      {panel ? (
        <div className="space-y-3 p-4">
          {panel.instruction ? <p className="text-xs text-muted-foreground">“{panel.instruction}”</p> : null}
          {panel.status === "error" ? (
            <p role="alert" className="rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {panel.error}
            </p>
          ) : panel.action === "extract_tasks" ? (
            streaming ? (
              <div className="space-y-2" aria-hidden>
                <div className="shimmer h-9 rounded-lg" />
                <div className="shimmer h-9 rounded-lg" />
              </div>
            ) : tasks.length ? (
              <>
                <p className="text-xs text-muted-foreground">
                  {tasks.length} task{tasks.length === 1 ? "" : "s"} found
                </p>
                <ul className="space-y-1.5">
                  {tasks.map((t, i) => (
                    <li key={`${t.title}-${i}`} className="flex items-start gap-3 rounded-lg bg-muted/50 px-3 py-2 text-sm ring-1 ring-glass-border">
                      <Checkbox
                        id={`xt-${i}`}
                        className="mt-0.5"
                        checked={selected.has(i)}
                        onCheckedChange={(checked) =>
                          setSelectedTasks(() => {
                            const next = new Set(selected);
                            if (checked) next.add(i);
                            else next.delete(i);
                            return next;
                          })
                        }
                      />
                      <label htmlFor={`xt-${i}`} className="flex min-w-0 flex-1 items-center gap-2">
                        <span className="truncate">{t.title}</span>
                        {t.due_date ? <span className="ml-auto shrink-0 text-xs text-muted-foreground">{t.due_date}</span> : null}
                        {t.priority !== "none" ? (
                          <Badge variant="outline" className="shrink-0 font-normal capitalize">
                            {t.priority}
                          </Badge>
                        ) : null}
                      </label>
                    </li>
                  ))}
                </ul>
              </>
            ) : (
              <p className="text-sm text-muted-foreground">No action items found in this note.</p>
            )
          ) : (
            <div className="space-y-3">
              {panel.original && panel.action === "improve" ? (
                <div className="rounded-lg bg-muted/40 p-3 ring-1 ring-glass-border">
                  <p className="mb-1 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Original</p>
                  <p className="line-clamp-4 text-sm text-muted-foreground">{panel.original}</p>
                </div>
              ) : null}
              <div className={cn("rounded-lg p-3 ring-1", panel.action === "improve" ? "bg-ai-soft/60 ring-ai/30" : "bg-muted/30 ring-glass-border")}>
                {panel.action === "improve" ? <p className="mb-1 text-[11px] font-medium uppercase tracking-wide text-ai">Suggested</p> : null}
                <div className={cn("max-h-80 overflow-y-auto text-sm", streaming && "after:animate-pulse after:text-ai after:content-['▍']")}>
                  {panel.text ? <Markdown text={panel.text} /> : <p className="text-muted-foreground">Thinking…</p>}
                </div>
              </div>
            </div>
          )}

          {panel.status !== "streaming" ? (
            <div className="flex flex-wrap items-center gap-2 pt-1">
              <Button variant="ghost" size="sm" onClick={() => void run(panel.action, panel.instruction)} aria-label="Regenerate">
                <RefreshCw aria-hidden /> Retry
              </Button>
              <div className="ml-auto flex flex-wrap gap-2">
                {panel.action === "extract_tasks" ? (
                  tasks.length ? (
                    <Button size="sm" disabled={selected.size === 0 || addTasks.isPending} onClick={() => addTasks.mutate(tasks.filter((_, i) => selected.has(i)))}>
                      {addTasks.isPending ? <Loader2 className="animate-spin" aria-hidden /> : <Check aria-hidden />} Add {selected.size} to tasks
                    </Button>
                  ) : null
                ) : panel.status === "done" ? (
                  <>
                    <Button variant="outline" size="sm" onClick={() => void copy()}>
                      <Copy aria-hidden /> Copy
                    </Button>
                    <Button variant="outline" size="sm" onClick={insertAtEnd} disabled={!editor}>
                      Insert
                    </Button>
                    <Button size="sm" onClick={replaceAll} disabled={!editor}>
                      <Replace aria-hidden /> {hasSelection ? "Replace selection" : "Replace"}
                    </Button>
                  </>
                ) : null}
              </div>
            </div>
          ) : null}
        </div>
      ) : null}
    </aside>
  );
}
