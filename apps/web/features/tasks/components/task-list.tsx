"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarCheck, CalendarDays, Check, CheckSquare, FileText, ListChecks, Loader2, Pencil, Plus, Sparkles, Trash2 } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { EmptyState } from "@/components/layout/empty-state";
import { PageHeader } from "@/components/layout/page-header";
import { SelectionBar } from "@/components/layout/selection-bar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { messageFor } from "@/features/auth/components/auth-form-error";
import { tasksApi } from "@/features/tasks/api";
import { TaskDialog } from "@/features/tasks/components/task-dialog";
import { dueAt, dueState, formatDue, localTimeZone, priorityMeta, type DueState } from "@/features/tasks/lib";
import { useSelection } from "@/hooks/use-selection";
import { playSfx } from "@/lib/sfx/player";
import type { Task, TaskStatus } from "@/lib/api/types";
import { cn } from "@/lib/utils";

const DUE_TONE: Record<DueState, string> = {
  none: "text-muted-foreground",
  overdue: "text-destructive",
  today: "text-warning",
  tomorrow: "text-foreground",
  week: "text-muted-foreground",
  later: "text-muted-foreground",
};

type Section = { key: string; label: string; tasks: Task[] };

function groupOpen(tasks: Task[]): Section[] {
  const buckets: Record<string, Task[]> = { overdue: [], today: [], tomorrow: [], week: [], later: [], none: [] };
  for (const t of tasks) buckets[dueState(t)]!.push(t);
  const byDue = (a: Task, b: Task) => (dueAt(a)?.getTime() ?? 0) - (dueAt(b)?.getTime() ?? 0);
  return (
    [
      { key: "overdue", label: "Overdue", tasks: buckets.overdue!.sort(byDue) },
      { key: "today", label: "Today", tasks: buckets.today!.sort(byDue) },
      { key: "tomorrow", label: "Tomorrow", tasks: buckets.tomorrow!.sort(byDue) },
      { key: "week", label: "This week", tasks: buckets.week!.sort(byDue) },
      { key: "later", label: "Later", tasks: buckets.later!.sort(byDue) },
      { key: "none", label: "No date", tasks: buckets.none! },
    ] as Section[]
  ).filter((s) => s.tasks.length);
}

/**
 * Tasks workspace: quick add, sections by urgency, one-click complete, and a dialog for
 * everything else (details, date & time, priority, Google Calendar).
 */
export function TaskList() {
  const router = useRouter();
  const params = useSearchParams();
  const view: TaskStatus = params.get("view") === "done" ? "done" : "open";
  const setView = (v: string) => router.replace(v === "done" ? "/app/tasks?view=done" : "/app/tasks");
  const [title, setTitle] = React.useState("");
  const [editing, setEditing] = React.useState<{ task: Task | null; open: boolean }>({ task: null, open: false });
  const queryClient = useQueryClient();
  const tasks = useQuery({ queryKey: ["tasks", view], queryFn: () => tasksApi.list({ status: view }) });
  const calendar = useQuery({ queryKey: ["tasks", "calendar", "status"], queryFn: tasksApi.calendarStatus, staleTime: 60_000 });
  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["tasks"] });
    queryClient.invalidateQueries({ queryKey: ["notifications"] });
  };
  const create = useMutation({
    mutationFn: tasksApi.create,
    onSuccess: () => {
      playSfx("create");
      invalidate();
      setTitle("");
    },
    onError: (e) => {
      playSfx("error");
      toast.error(messageFor(e));
    },
  });
  const toggle = useMutation({
    mutationFn: (t: Task) => tasksApi.update(t.id, { status: t.status === "open" ? "done" : "open" }),
    onMutate: async (t) => {
      await queryClient.cancelQueries({ queryKey: ["tasks", view] });
      const prev = queryClient.getQueryData<Task[]>(["tasks", view]);
      queryClient.setQueryData<Task[]>(["tasks", view], (old) => old?.filter((x) => x.id !== t.id));
      return { prev };
    },
    onError: (e, _t, ctx) => {
      queryClient.setQueryData(["tasks", view], ctx?.prev);
      toast.error(messageFor(e));
    },
    onSuccess: (saved, t) => {
      playSfx(t.status === "open" ? "task-complete" : "restore");
      invalidate();
      if (t.status === "open") {
        toast.success("Task completed", {
          action: { label: "Undo", onClick: () => toggle.mutate(saved) },
        });
      }
    },
  });
  const remove = useMutation({
    mutationFn: tasksApi.remove,
    onSuccess: () => {
      playSfx("delete");
      invalidate();
    },
    onError: (e) => toast.error(messageFor(e)),
  });
  // Selection mode: pick several tasks (shift-click for a range), delete them together.
  const list = tasks.data ?? [];
  const visibleIds = React.useMemo(() => (tasks.data ?? []).map((t) => t.id), [tasks.data]);
  const selection = useSelection(visibleIds);
  const [confirmBulk, setConfirmBulk] = React.useState(false);
  const removeMany = useMutation({
    mutationFn: tasksApi.removeMany,
    onSuccess: ({ deleted }) => {
      playSfx("delete");
      toast.success(`Deleted ${deleted} ${deleted === 1 ? "task" : "tasks"}`);
      setConfirmBulk(false);
      selection.exit();
      invalidate();
    },
    onError: (e) => toast.error(messageFor(e)),
  });

  const sections = view === "open" ? groupOpen(list) : [{ key: "done", label: "Completed", tasks: list }];
  const openCount = view === "open" ? list.length : undefined;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Tasks"
        description="Everything you need to do, with dates, priorities and a line to your calendar."
        actions={
          <>
            {calendar.data?.connected ? (
              <Badge variant="secondary" className="gap-1 font-normal text-muted-foreground">
                <CalendarCheck className="text-ai" aria-hidden /> Google Calendar
              </Badge>
            ) : (
              <Button variant="outline" size="sm" asChild className="rounded-full">
                <Link href="/app/settings/connections/google_calendar">
                  <CalendarDays aria-hidden /> Connect calendar
                </Link>
              </Button>
            )}
            <Button size="sm" onClick={() => setEditing({ task: null, open: true })} className="rounded-full">
              <Plus aria-hidden /> New task
            </Button>
          </>
        }
      />

      <form
        className="glass-2 flex items-center gap-2 rounded-full py-1.5 pl-4 pr-1.5 transition-shadow focus-within:glow-ai"
        onSubmit={(e) => {
          e.preventDefault();
          const t = title.trim();
          if (!t) return;
          create.mutate({ title: t, timezone: localTimeZone() });
        }}
      >
        <Plus className="size-4 shrink-0 text-muted-foreground" aria-hidden />
        <Input aria-label="New task" placeholder="Add a task and press Enter…" value={title} onChange={(e) => setTitle(e.target.value)} className="h-8 border-0 bg-transparent px-0 shadow-none focus-visible:ring-0 dark:bg-transparent" />
        <Button type="submit" size="sm" disabled={!title.trim() || create.isPending} className="rounded-full">
          {create.isPending ? <Loader2 className="animate-spin" aria-hidden /> : null} Add
        </Button>
      </form>

      <div className="flex items-center justify-between gap-3">
        <Tabs value={view} onValueChange={(v) => { selection.exit(); setView(v); }}>
          <TabsList className="rounded-full">
            <TabsTrigger value="open" className="rounded-full">
              Open{openCount !== undefined ? <span className="ml-1.5 text-xs text-muted-foreground">{openCount}</span> : null}
            </TabsTrigger>
            <TabsTrigger value="done" className="rounded-full">
              Done
            </TabsTrigger>
          </TabsList>
        </Tabs>
        {list.length && !selection.selecting ? (
          <Button variant="ghost" size="sm" aria-label="Select tasks" onClick={selection.enter} className="rounded-full text-muted-foreground">
            <ListChecks aria-hidden /> Select
          </Button>
        ) : null}
      </div>
      {selection.selecting ? (
        <SelectionBar
          className="rounded-xl border border-glass-border bg-muted/30 px-3 py-1"
          allState={selection.allState}
          count={selection.count}
          total={selection.visibleTotal}
          noun="tasks"
          onSelectAll={selection.selectAll}
          onCancel={selection.exit}
          action={{ label: "Delete", icon: Trash2, onClick: () => setConfirmBulk(true) }}
        />
      ) : null}

      {tasks.isPending ? (
        <div className="space-y-2" aria-busy>
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-14 w-full rounded-xl" />
          ))}
        </div>
      ) : tasks.error ? (
        <p role="alert" className="text-sm text-destructive">
          {messageFor(tasks.error)}
        </p>
      ) : !list.length ? (
        <div className="glass rounded-2xl">
          <EmptyState
            icon={CheckSquare}
            title={view === "open" ? "Nothing to do" : "No completed tasks yet"}
            description={view === "open" ? "Add a task above, or ask AI to extract tasks from a note." : "Tasks you finish show up here."}
            action={
              view === "open" ? (
                <Button size="sm" variant="outline" onClick={() => setEditing({ task: null, open: true })}>
                  <Plus aria-hidden /> New task
                </Button>
              ) : undefined
            }
          />
        </div>
      ) : (
        <div className="space-y-6">
          {sections.map((section) => (
            <section key={section.key} aria-labelledby={`tasks-${section.key}`}>
              <h2 id={`tasks-${section.key}`} className={cn("mb-2 flex items-center gap-2 text-xs font-medium uppercase tracking-[0.1em]", section.key === "overdue" ? "text-destructive" : "text-muted-foreground")}>
                {section.label}
                <span className="text-muted-foreground/60 normal-case tracking-normal">{section.tasks.length}</span>
              </h2>
              <ul className="glass divide-y divide-glass-border rounded-2xl">
                {section.tasks.map((t) => (
                  <TaskRow key={t.id} task={t} onToggle={() => toggle.mutate(t)} onEdit={() => setEditing({ task: t, open: true })} onDelete={() => remove.mutate(t.id)} selectable={selection.selecting} selected={selection.has(t.id)} onSelect={(checked, shift) => selection.toggle(t.id, checked, { shift })} />
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}

      <TaskDialog key={`${editing.task?.id ?? "new"}:${editing.open}`} task={editing.task} open={editing.open} onOpenChange={(open) => setEditing((s) => ({ ...s, open }))} />
      <ConfirmDialog
        open={confirmBulk}
        onOpenChange={setConfirmBulk}
        title={`Delete ${selection.count} ${selection.count === 1 ? "task" : "tasks"}?`}
        description="This can't be undone. Tasks linked to Google Calendar are removed from the calendar too."
        confirmLabel="Delete"
        pending={removeMany.isPending}
        onConfirm={() => removeMany.mutate([...selection.ids])}
      />
    </div>
  );
}

function TaskRow({ task, onToggle, onEdit, onDelete, selectable, selected, onSelect }: { task: Task; onToggle: () => void; onEdit: () => void; onDelete: () => void; selectable?: boolean; selected?: boolean; onSelect?: (checked: boolean, shift: boolean) => void }) {
  const done = task.status === "done";
  const state = dueState(task);
  const due = formatDue(task);
  const prio = priorityMeta(task.priority);
  return (
    <li className={cn("group flex items-start gap-3 px-3 py-2.5 transition-[background-color,box-shadow] first:rounded-t-2xl last:rounded-b-2xl hover:bg-muted/30 sm:items-center", done && "opacity-80", selectable && selected && "bg-primary/10 ring-1 ring-inset ring-primary/40 hover:bg-primary/15")}>
      {selectable ? (
        <Checkbox
          checked={Boolean(selected)}
          aria-label={`Select ${task.title}`}
          className="mt-1 size-[18px] sm:mt-0"
          onClick={(e) => {
            e.preventDefault();
            onSelect?.(!selected, e.shiftKey);
          }}
        />
      ) : (
        <Checkbox
          checked={done}
          onCheckedChange={onToggle}
          aria-label={done ? `Mark ${task.title} as open` : `Mark ${task.title} as done`}
          className="mt-1 size-[18px] rounded-full sm:mt-0"
        />
      )}
      <button type="button" onClick={selectable ? (e) => onSelect?.(!selected, e.shiftKey) : onEdit} aria-pressed={selectable ? selected : undefined} className="min-w-0 flex-1 rounded-md text-left outline-none focus-visible:ring-2 focus-visible:ring-ring">
        <span className={cn("block truncate text-sm", done && "text-muted-foreground line-through")}>{task.title}</span>
        <span className="mt-0.5 flex flex-wrap items-center gap-x-2.5 gap-y-1 text-xs">
          {due ? (
            <span className={cn("inline-flex items-center gap-1", DUE_TONE[state])}>
              <CalendarDays className="size-3" aria-hidden />
              {state === "overdue" ? `Overdue · ${due}` : due}
            </span>
          ) : null}
          {task.priority !== "none" ? (
            <span className={cn("inline-flex items-center gap-1", prio.tone)}>
              <span className={cn("size-1.5 rounded-full", prio.dot)} aria-hidden />
              {prio.label}
            </span>
          ) : null}
          {task.description ? <span className="hidden max-w-[28ch] truncate text-muted-foreground sm:inline">{task.description}</span> : null}
        </span>
      </button>
      <span className="flex shrink-0 items-center gap-1">
        {task.calendar_event_id ? (
          <Tooltip>
            <TooltipTrigger asChild>
              {task.calendar_event_url ? (
                <a href={task.calendar_event_url} target="_blank" rel="noopener noreferrer" aria-label="Open in Google Calendar" className={cn("grid size-7 place-items-center rounded-lg", task.calendar_error ? "bg-destructive/10 text-destructive" : "bg-ai-soft text-ai")}>
                  <CalendarCheck className="size-3.5" aria-hidden />
                </a>
              ) : (
                <span className="grid size-7 place-items-center rounded-lg bg-ai-soft text-ai">
                  <CalendarCheck className="size-3.5" aria-hidden />
                </span>
              )}
            </TooltipTrigger>
            <TooltipContent>{task.calendar_error ? `Calendar sync failed: ${task.calendar_error}` : "On your Google Calendar"}</TooltipContent>
          </Tooltip>
        ) : null}
        {task.source === "ai" ? (
          <Badge variant="outline" className="hidden gap-1 border-glass-border font-normal text-muted-foreground sm:inline-flex">
            <Sparkles className="size-3 text-ai" aria-hidden /> AI
          </Badge>
        ) : null}
        {task.note_id ? (
          <Tooltip>
            <TooltipTrigger asChild>
              <Link href={`/app/notes/${task.note_id}`} aria-label="Open source note" className="grid size-7 place-items-center rounded-lg text-muted-foreground hover:bg-muted hover:text-foreground">
                <FileText className="size-3.5" aria-hidden />
              </Link>
            </TooltipTrigger>
            <TooltipContent>From a note</TooltipContent>
          </Tooltip>
        ) : null}
        <Button variant="ghost" size="icon-sm" aria-label={`Edit ${task.title}`} onClick={onEdit} className="opacity-60 group-hover:opacity-100 focus-visible:opacity-100 sm:opacity-0">
          <Pencil aria-hidden />
        </Button>
        <Button variant="ghost" size="icon-sm" aria-label={`Delete task ${task.title}`} onClick={onDelete} className="opacity-60 hover:text-destructive group-hover:opacity-100 focus-visible:opacity-100 sm:opacity-0">
          <Trash2 aria-hidden />
        </Button>
        {done ? <Check className="hidden size-4 text-success sm:block" aria-hidden /> : null}
      </span>
    </li>
  );
}
