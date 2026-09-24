"use client";

import { Archive, ArchiveRestore, Loader2, MoreHorizontal, Pencil, Trash2 } from "@/components/icons";
import * as React from "react";
import { useShallow } from "zustand/react/shallow";

import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { useChatStore } from "@/features/ai/chat-store";
import type { AIThread } from "@/lib/api/types";
import { cn } from "@/lib/utils";

/** What a conversation is doing right now, for its row in the list. */
export type ThreadActivity = "generating" | "waiting" | "failed" | null;

/**
 * Activity per thread: this tab's live state wins; threads not opened here fall back to the
 * server's view (a run started in another tab, or before a reload). Only re-renders when some
 * thread's activity actually changes, not on every streamed token.
 */
export function useThreadActivity(threads: AIThread[] | undefined): Record<string, ThreadActivity> {
  const local = useChatStore(
    useShallow((s) => {
      const out: Record<string, ThreadActivity> = {};
      for (const [id, t] of Object.entries(s.threads)) {
        out[id] = t.busy ? "generating" : t.approval ? "waiting" : t.error && t.messages.at(-1)?.role === "user" ? "failed" : null;
      }
      return out;
    }),
  );
  return React.useMemo(() => {
    const out: Record<string, ThreadActivity> = {};
    for (const t of threads ?? []) {
      out[t.id] =
        t.id in local
          ? local[t.id]!
          : t.active_run_status === "running" || t.active_run_status === "queued"
            ? "generating"
            : t.active_run_status === "waiting_for_approval"
              ? "waiting"
              : null;
    }
    return out;
  }, [threads, local]);
}

const DAY = 86_400_000;
export function groupOf(iso: string, startOfToday: number): string {
  const t = new Date(iso).getTime();
  if (t >= startOfToday) return "Today";
  if (t >= startOfToday - DAY) return "Yesterday";
  if (t >= startOfToday - 7 * DAY) return "Previous 7 days";
  if (t >= startOfToday - 30 * DAY) return "Previous 30 days";
  return "Older";
}

/** "now", "5m", "3h", "Tue", "Mar 4": short enough for a list row. */
export function shortTime(iso: string, now: number = Date.now()): string {
  const t = new Date(iso).getTime();
  const diff = Math.max(0, now - t);
  if (diff < 60_000) return "now";
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m`;
  if (diff < DAY) return `${Math.floor(diff / 3_600_000)}h`;
  if (diff < 7 * DAY) return new Intl.DateTimeFormat(undefined, { weekday: "short" }).format(t);
  return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" }).format(t);
}

export interface ThreadActions {
  onSelect: (id: string) => void;
  onRename: (thread: AIThread, title: string) => void;
  onArchive: (thread: AIThread, archived: boolean) => void;
  onDelete: (thread: AIThread) => void;
}

export function ConversationRow({
  thread,
  active,
  activity,
  now,
  actions,
}: {
  thread: AIThread;
  active: boolean;
  activity: ThreadActivity;
  now: number;
  actions: ThreadActions;
}) {
  const [renaming, setRenaming] = React.useState(false);
  const [draft, setDraft] = React.useState(thread.title);
  const inputRef = React.useRef<HTMLInputElement>(null);
  const archived = Boolean(thread.archived_at);

  React.useEffect(() => {
    if (renaming) {
      inputRef.current?.focus();
      inputRef.current?.select();
    }
  }, [renaming]);

  const commit = () => {
    const title = draft.trim();
    setRenaming(false);
    if (title && title !== thread.title) actions.onRename(thread, title);
    else setDraft(thread.title);
  };

  const preview =
    activity === "generating"
      ? "Generating a reply…"
      : activity === "waiting"
        ? "Waiting for your approval"
        : activity === "failed"
          ? "Couldn't answer. Open to retry"
          : thread.last_message
            ? `${thread.last_message_role === "user" ? "You: " : ""}${thread.last_message}`
            : "No messages yet";

  return (
    <li
      data-row
      data-thread-id={thread.id}
      data-activity={activity ?? undefined}
      className={cn("group/row relative z-10 mx-2 flex items-center rounded-lg transition-colors duration-150", active && "bg-accent/80 group-hover/glide:bg-transparent")}
    >
      {renaming ? (
        <form
          className="flex min-w-0 flex-1 px-1.5 py-1.5"
          onSubmit={(e) => {
            e.preventDefault();
            commit();
          }}
        >
          <input
            ref={inputRef}
            value={draft}
            maxLength={200}
            aria-label="Conversation title"
            onChange={(e) => setDraft(e.target.value)}
            onBlur={commit}
            onKeyDown={(e) => {
              if (e.key === "Escape") {
                setDraft(thread.title);
                setRenaming(false);
              }
            }}
            className="h-7 min-w-0 flex-1 rounded-md bg-background px-2 text-sm outline-none ring-1 ring-ring"
          />
        </form>
      ) : (
        <button
          type="button"
          title={thread.title}
          onClick={() => actions.onSelect(thread.id)}
          aria-current={active ? "page" : undefined}
          className={cn(
            "flex min-w-0 flex-1 flex-col gap-0.5 rounded-lg px-2 py-1.5 text-left outline-none focus-visible:ring-2 focus-visible:ring-ring active:scale-[0.99]",
            active ? "text-foreground" : "text-muted-foreground hover:text-foreground",
          )}
        >
          <span className="flex min-w-0 items-center gap-1.5">
            <ActivityMark activity={activity} />
            <span className={cn("min-w-0 flex-1 truncate text-sm", active && "font-medium")}>{thread.title}</span>
            <time dateTime={thread.last_activity_at} className="shrink-0 text-[11px] tabular-nums text-tertiary group-hover/row:opacity-0 group-focus-within/row:opacity-0">
              {shortTime(thread.last_activity_at, now)}
            </time>
          </span>
          <span className={cn("truncate text-xs", activity === "failed" ? "text-destructive" : activity ? "text-ai" : "text-tertiary")}>{preview}</span>
        </button>
      )}
      {renaming ? null : (
        <DropdownMenu>
          <DropdownMenuTrigger
            aria-label={`Actions for ${thread.title}`}
            className="absolute right-1.5 top-1.5 grid size-6 place-items-center rounded-md text-muted-foreground opacity-0 transition-opacity hover:bg-accent hover:text-foreground focus-visible:opacity-100 group-hover/row:opacity-100 data-[state=open]:opacity-100"
          >
            <MoreHorizontal className="size-4" aria-hidden />
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-40">
            <DropdownMenuItem
              onSelect={() => {
                setDraft(thread.title);
                // Let the menu close (and return focus) before the field takes it.
                setTimeout(() => setRenaming(true), 0);
              }}
            >
              <Pencil aria-hidden /> Rename
            </DropdownMenuItem>
            <DropdownMenuItem onSelect={() => actions.onArchive(thread, !archived)}>
              {archived ? <ArchiveRestore aria-hidden /> : <Archive aria-hidden />} {archived ? "Restore" : "Archive"}
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem variant="destructive" onSelect={() => actions.onDelete(thread)}>
              <Trash2 aria-hidden /> Delete
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      )}
    </li>
  );
}

function ActivityMark({ activity }: { activity: ThreadActivity }) {
  if (activity === "generating") return <Loader2 className="size-3.5 shrink-0 animate-spin text-ai" aria-label="Generating" />;
  if (activity === "waiting") return <span className="size-2 shrink-0 rounded-full bg-amber-500" aria-label="Waiting for approval" />;
  if (activity === "failed") return <span className="size-2 shrink-0 rounded-full bg-destructive" aria-label="Failed" />;
  return null;
}
