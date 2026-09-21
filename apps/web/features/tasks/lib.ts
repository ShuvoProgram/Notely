import type { Task, TaskPriority } from "@/lib/api/types";

export const PRIORITIES: { value: TaskPriority; label: string; tone: string; dot: string }[] = [
  { value: "none", label: "No priority", tone: "text-muted-foreground", dot: "bg-muted-foreground/40" },
  { value: "low", label: "Low", tone: "text-info", dot: "bg-info" },
  { value: "medium", label: "Medium", tone: "text-warning", dot: "bg-warning" },
  { value: "high", label: "High", tone: "text-destructive", dot: "bg-destructive" },
];

export function priorityMeta(p: TaskPriority) {
  return PRIORITIES.find((x) => x.value === p) ?? PRIORITIES[0]!;
}

/** The browser's IANA zone, sent with due times so the server (and Calendar) know what "10:00" means. */
export function localTimeZone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch {
    return "UTC";
  }
}

/** Local Date for a task's due moment (end of day when no time). */
export function dueAt(task: Pick<Task, "due_date" | "due_time">): Date | null {
  if (!task.due_date) return null;
  const [y, m, d] = task.due_date.split("-").map(Number);
  if (!y || !m || !d) return null;
  if (task.due_time) {
    const [hh, mm] = task.due_time.split(":").map(Number);
    return new Date(y, m - 1, d, hh ?? 0, mm ?? 0);
  }
  return new Date(y, m - 1, d, 23, 59, 59);
}

export type DueState = "none" | "overdue" | "today" | "tomorrow" | "week" | "later";

export function dueState(task: Pick<Task, "due_date" | "due_time" | "status">): DueState {
  const at = dueAt(task);
  if (!at) return "none";
  if (task.status === "done") return "later";
  const now = new Date();
  if (at.getTime() < now.getTime()) return "overdue";
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const days = Math.floor((at.getTime() - startOfToday.getTime()) / 86_400_000);
  if (days === 0) return "today";
  if (days === 1) return "tomorrow";
  if (days < 7) return "week";
  return "later";
}

export function formatDue(task: Pick<Task, "due_date" | "due_time" | "status">): string {
  const at = dueAt(task);
  if (!at) return "";
  const state = dueState(task);
  const time = task.due_time ? at.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" }) : null;
  const day =
    state === "today"
      ? "Today"
      : state === "tomorrow"
        ? "Tomorrow"
        : at.toLocaleDateString(undefined, { month: "short", day: "numeric", year: at.getFullYear() === new Date().getFullYear() ? undefined : "numeric" });
  return time ? `${day} · ${time}` : day;
}

/** "HH:MM" for <input type="time"> from the API's "HH:MM:SS". */
export function toTimeInput(t: string | null): string {
  return t ? t.slice(0, 5) : "";
}
