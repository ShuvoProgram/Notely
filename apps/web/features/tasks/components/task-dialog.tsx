"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarCheck, CalendarPlus, ExternalLink, Loader2, Trash2 } from "@/components/icons";
import Link from "next/link";
import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { DatePicker } from "@/components/ui/date-picker";
import { Input } from "@/components/ui/input";
import { TimePicker } from "@/components/ui/time-picker";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { messageFor } from "@/features/auth/components/auth-form-error";
import { tasksApi } from "@/features/tasks/api";
import { PRIORITIES, localTimeZone, toTimeInput } from "@/features/tasks/lib";
import { ApiError } from "@/lib/api/client";
import { playSfx } from "@/lib/sfx/player";
import type { Task, TaskPriority } from "@/lib/api/types";
import { cn } from "@/lib/utils";

interface Draft {
  title: string;
  description: string;
  due_date: string;
  due_time: string;
  priority: TaskPriority;
  calendar: boolean;
}

function draftFrom(task: Task | null): Draft {
  return {
    title: task?.title ?? "",
    description: task?.description ?? "",
    due_date: task?.due_date ?? "",
    due_time: toTimeInput(task?.due_time ?? null),
    priority: task?.priority ?? "none",
    calendar: Boolean(task?.calendar_event_id),
  };
}

/**
 * Create / edit a task. Saving writes the task, then reconciles the Google Calendar link:
 * on → create or refresh the event, off → remove it. The calendar switch explains itself when
 * the connection or the "create events" permission is missing.
 */
export function TaskDialog({ task, open, onOpenChange }: { task: Task | null; open: boolean; onOpenChange: (o: boolean) => void }) {
  const queryClient = useQueryClient();
  // The parent remounts this dialog (key) for every open, so state initialises from the task.
  const [draft, setDraft] = React.useState<Draft>(() => draftFrom(task));
  const [errors, setErrors] = React.useState<Record<string, string>>({});

  const calendar = useQuery({ queryKey: ["tasks", "calendar", "status"], queryFn: tasksApi.calendarStatus, enabled: open, staleTime: 30_000 });
  const canSync = Boolean(calendar.data?.connected && calendar.data.can_write);
  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["tasks"] });
    queryClient.invalidateQueries({ queryKey: ["notifications"] });
  };

  const save = useMutation({
    mutationFn: async () => {
      const title = draft.title.trim();
      if (!title) throw new ApiError(422, { code: "VALIDATION_ERROR", message: "Give the task a title.", details: { fields: { title: ["Required"] } } });
      const base = {
        title,
        description: draft.description.trim() || null,
        priority: draft.priority,
        due_date: draft.due_date || null,
        due_time: draft.due_date && draft.due_time ? `${draft.due_time}:00` : null,
        timezone: localTimeZone(),
      };
      let saved: Task;
      if (task) {
        saved = await tasksApi.update(task.id, {
          ...base,
          clear_due_date: !draft.due_date,
          clear_due_time: Boolean(draft.due_date) && !draft.due_time,
        });
      } else {
        saved = await tasksApi.create(base);
      }
      // Reconcile the calendar link after the task itself is safe.
      if (draft.calendar && !saved.calendar_event_id) saved = await tasksApi.addToCalendar(saved.id);
      else if (!draft.calendar && saved.calendar_event_id) saved = await tasksApi.removeFromCalendar(saved.id);
      return saved;
    },
    onSuccess: (saved) => {
      playSfx(task ? "success" : "create");
      invalidate();
      onOpenChange(false);
      toast.success(task ? "Task updated" : "Task added", {
        description: saved.calendar_event_id ? "It’s on your Google Calendar." : undefined,
      });
    },
    onError: (error) => {
      if (error instanceof ApiError && Object.keys(error.fieldErrors).length) {
        setErrors(Object.fromEntries(Object.entries(error.fieldErrors).map(([k, v]) => [k, v[0] ?? "Invalid"])));
        return;
      }
      invalidate(); // the task may have saved even if the calendar step failed
      playSfx("error");
      toast.error(messageFor(error));
    },
  });
  const remove = useMutation({
    mutationFn: () => tasksApi.remove(task!.id),
    onSuccess: () => {
      playSfx("delete");
      invalidate();
      onOpenChange(false);
      toast.success("Task deleted");
    },
    onError: (e) => toast.error(messageFor(e)),
  });

  const set = <K extends keyof Draft>(key: K, value: Draft[K]) => setDraft((d) => ({ ...d, [key]: value }));

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <form
          className="space-y-5"
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate();
          }}
        >
          <DialogHeader>
            <DialogTitle>{task ? "Edit task" : "New task"}</DialogTitle>
            <DialogDescription>{task ? "Changes save to the task and, if linked, to its calendar event." : "Add what needs doing, when, and how urgent it is."}</DialogDescription>
          </DialogHeader>

          <div className="space-y-2">
            <Label htmlFor="task-title">Title</Label>
            <Input id="task-title" value={draft.title} onChange={(e) => set("title", e.target.value)} placeholder="e.g. Send the pricing proposal" autoFocus aria-invalid={errors.title ? true : undefined} />
            {errors.title ? (
              <p role="alert" className="text-xs text-destructive">
                {errors.title}
              </p>
            ) : null}
          </div>

          <div className="space-y-2">
            <Label htmlFor="task-desc">Details</Label>
            <Textarea id="task-desc" value={draft.description} onChange={(e) => set("description", e.target.value)} placeholder="Optional notes, links, context…" rows={3} />
          </div>

          <div className="grid gap-4 sm:grid-cols-3">
            <div className="space-y-2">
              <Label htmlFor="task-date">Due date</Label>
              <DatePicker id="task-date" value={draft.due_date} onChange={(v) => set("due_date", v)} aria-invalid={errors.due_date ? true : undefined} placeholder="No date" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="task-time">Time</Label>
              <TimePicker id="task-time" value={draft.due_time} disabled={!draft.due_date} onChange={(v) => set("due_time", v)} placeholder="All day" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="task-priority">Priority</Label>
              <Select value={draft.priority} onValueChange={(v) => set("priority", v as TaskPriority)}>
                <SelectTrigger id="task-priority" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {PRIORITIES.map((p) => (
                    <SelectItem key={p.value} value={p.value}>
                      <span className={cn("mr-2 inline-block size-2 rounded-full", p.dot)} aria-hidden />
                      {p.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className={cn("flex items-start justify-between gap-4 rounded-xl p-3 ring-1", draft.calendar ? "bg-ai-soft/40 ring-ai/30" : "bg-muted/30 ring-glass-border")}>
            <div className="min-w-0">
              <Label htmlFor="task-calendar" className="flex items-center gap-2 text-sm font-medium">
                {task?.calendar_event_id ? <CalendarCheck className="size-4 text-ai" aria-hidden /> : <CalendarPlus className="size-4 text-ai" aria-hidden />}
                Add to Google Calendar
              </Label>
              <p className="mt-1 text-xs text-muted-foreground">
                {calendar.isPending ? (
                  "Checking your calendar connection…"
                ) : !calendar.data?.connected ? (
                  <>
                    Not connected yet.{" "}
                    <Link href="/app/settings/connections/google_calendar" className="text-foreground underline-offset-2 hover:underline">
                      Connect Google Calendar
                    </Link>{" "}
                    to schedule tasks as events.
                  </>
                ) : !calendar.data.can_write ? (
                  <>
                    Notely can read your calendar but not create events.{" "}
                    <Link href="/app/settings/connections/google_calendar" className="text-foreground underline-offset-2 hover:underline">
                      Reconnect
                    </Link>{" "}
                    and allow “Create and update events”.
                  </>
                ) : !draft.due_date ? (
                  "Set a due date to put this on your calendar."
                ) : task?.calendar_event_id ? (
                  <>
                    Linked to an event on {calendar.data.account}. Edits sync automatically.{" "}
                    {task.calendar_event_url ? (
                      <a href={task.calendar_event_url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-foreground underline-offset-2 hover:underline">
                        Open <ExternalLink className="size-3" aria-hidden />
                      </a>
                    ) : null}
                  </>
                ) : (
                  <>Creates a {draft.due_time ? "1-hour" : "all-day"} event on {calendar.data.account}. Never duplicated.</>
                )}
              </p>
              {task?.calendar_error ? (
                <p role="alert" className="mt-1 text-xs text-destructive">
                  Last sync failed: {task.calendar_error}
                </p>
              ) : null}
            </div>
            <Switch id="task-calendar" checked={draft.calendar} disabled={!canSync || !draft.due_date} onCheckedChange={(v) => set("calendar", v)} />
          </div>

          <DialogFooter className="sm:justify-between">
            {task ? (
              <Button type="button" variant="ghost" onClick={() => remove.mutate()} disabled={remove.isPending} className="text-muted-foreground hover:text-destructive">
                {remove.isPending ? <Loader2 className="animate-spin" aria-hidden /> : <Trash2 aria-hidden />} Delete
              </Button>
            ) : (
              <span />
            )}
            <div className="flex gap-2">
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={save.isPending}>
                {save.isPending ? <Loader2 className="animate-spin" aria-hidden /> : null}
                {task ? "Save changes" : "Add task"}
              </Button>
            </div>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
