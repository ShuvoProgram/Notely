"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Circle, Plus, Sparkles, Trash2 } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { messageFor } from "@/features/auth/components/auth-form-error";
import { tasksApi } from "@/features/tasks/api";
import type { Task, TaskStatus } from "@/lib/api/types";
import { cn } from "@/lib/utils";

const PRIORITY_TONE: Record<Task["priority"], string> = {
  none: "",
  low: "text-muted-foreground",
  medium: "text-warning",
  high: "text-destructive",
};

export function TaskList() {
  const [view, setView] = React.useState<TaskStatus>("open");
  const [title, setTitle] = React.useState("");
  const queryClient = useQueryClient();
  const tasks = useQuery({ queryKey: ["tasks", view], queryFn: () => tasksApi.list({ status: view }) });
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["tasks"] });
  const create = useMutation({ mutationFn: tasksApi.create, onSuccess: invalidate, onError: (e) => toast.error(messageFor(e)) });
  const toggle = useMutation({
    mutationFn: (t: Task) => tasksApi.update(t.id, { status: t.status === "open" ? "done" : "open" }),
    onSuccess: invalidate,
    onError: (e) => toast.error(messageFor(e)),
  });
  const remove = useMutation({ mutationFn: tasksApi.remove, onSuccess: invalidate, onError: (e) => toast.error(messageFor(e)) });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Tasks</h1>
        <p className="mt-1 text-sm text-muted-foreground">Your own tasks plus the ones AI extracted from notes with your approval.</p>
      </div>
      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          const t = title.trim();
          if (!t) return;
          create.mutate({ title: t }, { onSuccess: () => setTitle("") });
        }}
      >
        <Input aria-label="New task" placeholder="Add a task…" value={title} onChange={(e) => setTitle(e.target.value)} />
        <Button type="submit" disabled={!title.trim() || create.isPending}>
          <Plus aria-hidden /> Add
        </Button>
      </form>
      <Tabs value={view} onValueChange={(v) => setView(v as TaskStatus)}>
        <TabsList>
          <TabsTrigger value="open">Open</TabsTrigger>
          <TabsTrigger value="done">Done</TabsTrigger>
        </TabsList>
      </Tabs>
      {tasks.isPending ? (
        <div className="space-y-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-12 w-full" />
          ))}
        </div>
      ) : tasks.error ? (
        <p role="alert" className="text-sm text-destructive">
          {messageFor(tasks.error)}
        </p>
      ) : tasks.data?.length ? (
        <ul className="divide-y rounded-xl border bg-card">
          {tasks.data.map((t) => (
            <li key={t.id} className="group flex items-center gap-3 px-3 py-2.5">
              <button
                type="button"
                aria-label={t.status === "done" ? `Mark ${t.title} as open` : `Mark ${t.title} as done`}
                aria-pressed={t.status === "done"}
                onClick={() => toggle.mutate(t)}
                className="grid size-6 place-items-center rounded-full text-muted-foreground hover:text-ai"
              >
                {t.status === "done" ? <Check className="size-5 text-ai" aria-hidden /> : <Circle className="size-5" aria-hidden />}
              </button>
              <div className="min-w-0 flex-1">
                <p className={cn("text-sm", t.status === "done" && "text-muted-foreground line-through")}>{t.title}</p>
                <p className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                  {t.due_date ? <span>Due {t.due_date}</span> : null}
                  {t.priority !== "none" ? <span className={PRIORITY_TONE[t.priority]}>{t.priority} priority</span> : null}
                  {t.source === "ai" ? (
                    <Badge variant="outline" className="gap-1 font-normal">
                      <Sparkles className="size-3" aria-hidden /> AI
                    </Badge>
                  ) : null}
                  {t.note_id ? (
                    <Link href={`/app/notes/${t.note_id}`} className="underline-offset-2 hover:underline">
                      From note
                    </Link>
                  ) : null}
                </p>
              </div>
              <Button variant="ghost" size="icon-sm" aria-label={`Delete task ${t.title}`} className="opacity-0 focus-visible:opacity-100 group-hover:opacity-100" onClick={() => remove.mutate(t.id)}>
                <Trash2 aria-hidden />
              </Button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="rounded-xl border bg-card p-6 text-center text-sm text-muted-foreground">
          {view === "open" ? "Nothing to do. Add a task, or ask AI to extract tasks from a note." : "No completed tasks yet."}
        </p>
      )}
    </div>
  );
}
