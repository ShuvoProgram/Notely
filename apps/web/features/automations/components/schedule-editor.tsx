"use client";

import { DatePicker } from "@/components/ui/date-picker";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { TimePicker } from "@/components/ui/time-picker";
import { cn } from "@/lib/utils";

import type { Schedule } from "../types";

type Mode = "daily" | "weekdays" | "weekly" | "monthly" | "interval" | "custom" | "once" | "manual";

const MODES: { value: Mode; label: string }[] = [
  { value: "daily", label: "Every day" },
  { value: "weekdays", label: "Every weekday (Mon–Fri)" },
  { value: "weekly", label: "On certain days" },
  { value: "monthly", label: "Once a month" },
  { value: "interval", label: "Every few minutes or hours" },
  { value: "custom", label: "Every few days" },
  { value: "once", label: "Just once" },
  { value: "manual", label: "Only when I run it" },
];
const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const INTERVALS = [15, 30, 60, 120, 240, 360, 720];

function modeOf(s: Schedule): Mode {
  if (s.schedule_kind === "weekly" && [...(s.schedule_config.days ?? [])].sort().join() === "0,1,2,3,4") return "weekdays";
  return s.schedule_kind as Mode;
}

function toLocalInput(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** Local "YYYY-MM-DD" + "HH:MM" → ISO instant; null until a date is picked. */
function combine(date: string, time: string): string | null {
  if (!date) return null;
  const d = new Date(`${date}T${time}`);
  return Number.isNaN(d.getTime()) ? null : d.toISOString();
}

export function ScheduleEditor({ value, onChange }: { value: Schedule; onChange: (next: Schedule) => void }) {
  const mode = modeOf(value);
  const cfg = value.schedule_config ?? {};
  const time = cfg.time ?? "09:00";
  const setMode = (next: Mode) => {
    const base = { ...value, starts_at: next === "once" ? value.starts_at : null };
    if (next === "weekdays") return onChange({ ...base, schedule_kind: "weekly", schedule_config: { time, days: [0, 1, 2, 3, 4] } });
    if (next === "weekly") return onChange({ ...base, schedule_kind: "weekly", schedule_config: { time, days: cfg.days?.length ? cfg.days : [0] } });
    if (next === "monthly") return onChange({ ...base, schedule_kind: "monthly", schedule_config: { time, day: cfg.day ?? 1 } });
    if (next === "interval") return onChange({ ...base, schedule_kind: "interval", schedule_config: { every_minutes: cfg.every_minutes ?? 60 } });
    if (next === "custom") return onChange({ ...base, schedule_kind: "custom", schedule_config: { time, interval_days: cfg.interval_days ?? 2 } });
    if (next === "once") return onChange({ ...base, schedule_kind: "once", schedule_config: {}, starts_at: value.starts_at ?? new Date(Date.now() + 3_600_000).toISOString() });
    if (next === "manual") return onChange({ ...base, schedule_kind: "manual", schedule_config: {} });
    return onChange({ ...base, schedule_kind: "daily", schedule_config: { time } });
  };
  const setConfig = (patch: Schedule["schedule_config"]) => onChange({ ...value, schedule_config: { ...cfg, ...patch } });
  const needsTime = !["interval", "once", "manual"].includes(mode);

  return (
    <div className="grid gap-3 sm:grid-cols-2">
      <div className="space-y-1.5">
        <Label htmlFor="schedule-mode">How often</Label>
        <Select value={mode} onValueChange={(v) => setMode(v as Mode)}>
          <SelectTrigger id="schedule-mode" className="w-full" aria-label="How often">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {MODES.map((m) => (
              <SelectItem key={m.value} value={m.value}>
                {m.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      {needsTime ? (
        <div className="space-y-1.5">
          <Label htmlFor="schedule-time">At</Label>
          <TimePicker id="schedule-time" value={time} onChange={(v) => setConfig({ time: v || "09:00" })} />
        </div>
      ) : null}
      {mode === "interval" ? (
        <div className="space-y-1.5">
          <Label htmlFor="schedule-every">Every</Label>
          <Select value={String(cfg.every_minutes ?? 60)} onValueChange={(v) => setConfig({ every_minutes: Number(v) })}>
            <SelectTrigger id="schedule-every" className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {INTERVALS.map((m) => (
                <SelectItem key={m} value={String(m)}>
                  {m < 60 ? `${m} minutes` : m === 60 ? "hour" : `${m / 60} hours`}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      ) : null}
      {mode === "once" ? (
        <div className="space-y-1.5">
          <Label htmlFor="schedule-once">On</Label>
          <div className="grid gap-2 sm:grid-cols-2">
            <DatePicker
              id="schedule-once"
              value={toLocalInput(value.starts_at).slice(0, 10)}
              fromDate={new Date(new Date().setHours(0, 0, 0, 0))}
              onChange={(date) => onChange({ ...value, starts_at: combine(date, toLocalInput(value.starts_at).slice(11) || "09:00") })}
            />
            <TimePicker
              aria-label="Time"
              value={toLocalInput(value.starts_at).slice(11)}
              onChange={(time) => onChange({ ...value, starts_at: combine(toLocalInput(value.starts_at).slice(0, 10), time || "09:00") })}
            />
          </div>
        </div>
      ) : null}
      {mode === "monthly" ? (
        <div className="space-y-1.5">
          <Label htmlFor="schedule-day">Day of the month</Label>
          <Input id="schedule-day" type="number" min={1} max={31} value={cfg.day ?? 1} onChange={(e) => setConfig({ day: Math.min(31, Math.max(1, Number(e.target.value) || 1)) })} />
        </div>
      ) : null}
      {mode === "custom" ? (
        <div className="space-y-1.5">
          <Label htmlFor="schedule-days-apart">Every how many days</Label>
          <Input id="schedule-days-apart" type="number" min={1} value={cfg.interval_days ?? 2} onChange={(e) => setConfig({ interval_days: Math.max(1, Number(e.target.value) || 1) })} />
        </div>
      ) : null}
      {mode === "weekly" ? (
        <fieldset className="sm:col-span-2">
          <legend className="mb-1.5 text-sm font-medium">On</legend>
          <div className="flex flex-wrap gap-1.5">
            {DAYS.map((day, index) => {
              const on = cfg.days?.includes(index) ?? false;
              return (
                <button
                  key={day}
                  type="button"
                  aria-pressed={on}
                  onClick={() => {
                    const days = on ? (cfg.days ?? []).filter((d) => d !== index) : [...(cfg.days ?? []), index];
                    if (days.length) setConfig({ days: days.sort() });
                  }}
                  className={cn(
                    "h-8 min-w-11 rounded-full border px-3 text-sm transition-colors",
                    on ? "border-ai/50 bg-ai-soft text-ai" : "border-glass-border text-muted-foreground hover:text-foreground",
                  )}
                >
                  {day}
                </button>
              );
            })}
          </div>
        </fieldset>
      ) : null}
      {mode !== "manual" ? (
        <p className="text-xs text-muted-foreground sm:col-span-2">Times are in {value.timezone.replaceAll("_", " ")}.</p>
      ) : null}
    </div>
  );
}
