import type { NoteColor } from "@/lib/api/types";

export const NOTE_COLORS: { value: NoteColor; label: string; swatch: string }[] = [
  { value: "default", label: "Default", swatch: "bg-muted ring-1 ring-glass-border-strong" },
  { value: "cream", label: "Cream", swatch: "bg-[oklch(0.86_0.09_85)]" },
  { value: "yellow", label: "Yellow", swatch: "bg-[oklch(0.88_0.14_95)]" },
  { value: "green", label: "Green", swatch: "bg-[oklch(0.8_0.14_150)]" },
  { value: "blue", label: "Blue", swatch: "bg-[oklch(0.8_0.14_240)]" },
  { value: "purple", label: "Purple", swatch: "bg-[oklch(0.78_0.14_300)]" },
  { value: "rose", label: "Rose", swatch: "bg-[oklch(0.8_0.14_10)]" },
];

/** "Edited 3m ago" style stamp for the list and the editor meta row. */
export function editedLabel(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.round(diff / 60_000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.round(h / 24);
  if (d < 7) return `${d}d ago`;
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

/** Reminder shown as "Tomorrow, 9:00 AM" / "Sep 30, 2:00 PM"; "Passed" once it has fired. */
export function reminderLabel(iso: string): { text: string; passed: boolean } {
  const at = new Date(iso);
  const now = new Date();
  const passed = at.getTime() < now.getTime();
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const days = Math.floor((at.getTime() - startOfToday.getTime()) / 86_400_000);
  const time = at.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
  const day = days === 0 ? "Today" : days === 1 ? "Tomorrow" : at.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  return { text: `${day}, ${time}`, passed };
}

/** Local "YYYY-MM-DD" and "HH:MM" for the reminder inputs. */
export function splitLocal(iso: string | null): { date: string; time: string } {
  if (!iso) return { date: "", time: "" };
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return {
    date: `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`,
    time: `${pad(d.getHours())}:${pad(d.getMinutes())}`,
  };
}

export function joinLocal(date: string, time: string): string | null {
  if (!date) return null;
  const [y, m, d] = date.split("-").map(Number);
  const [hh, mm] = (time || "09:00").split(":").map(Number);
  if (!y || !m || !d) return null;
  return new Date(y, m - 1, d, hh ?? 9, mm ?? 0).toISOString();
}
