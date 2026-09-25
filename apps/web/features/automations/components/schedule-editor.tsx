"use client";

import Link from "next/link";
import * as React from "react";

import { DatePicker } from "@/components/ui/date-picker";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectGroup, SelectItem, SelectLabel, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { TimePicker } from "@/components/ui/time-picker";
import { cn } from "@/lib/utils";

import type { InputSpec, Schedule, TriggerSpec } from "../types";

type Mode = "event" | "daily" | "weekdays" | "weekly" | "monthly" | "interval" | "custom" | "once" | "manual";
const CHECK_EVERY = [5, 10, 15, 30, 60];

const MODES: { value: Mode; label: string }[] = [
  { value: "event", label: "When something happens in an app" },
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

export function ScheduleEditor({ value, onChange, triggers = [] }: { value: Schedule; onChange: (next: Schedule) => void; triggers?: TriggerSpec[] }) {
  const mode = modeOf(value);
  const modes = triggers.length ? MODES : MODES.filter((m) => m.value !== "event");
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
    if (next === "event") {
      const first = triggers.find((t) => t.available) ?? triggers[0];
      return onChange({ ...base, schedule_kind: "event", schedule_config: first ? eventConfig(first) : {} });
    }
    return onChange({ ...base, schedule_kind: "daily", schedule_config: { time } });
  };
  const setConfig = (patch: Schedule["schedule_config"]) => onChange({ ...value, schedule_config: { ...cfg, ...patch } });
  const needsTime = !["interval", "once", "manual", "event"].includes(mode);

  return (
    <div className="grid gap-3 sm:grid-cols-2">
      <div className="space-y-1.5">
        <Label htmlFor="schedule-mode">How often</Label>
        <Select value={mode} onValueChange={(v) => setMode(v as Mode)}>
          <SelectTrigger id="schedule-mode" className="w-full" aria-label="How often">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {modes.map((m) => (
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
      {mode === "event" ? <EventTrigger value={value} onChange={onChange} triggers={triggers} /> : null}
      {mode !== "manual" && mode !== "event" ? (
        <p className="text-xs text-muted-foreground sm:col-span-2">Times are in {value.timezone.replaceAll("_", " ")}.</p>
      ) : null}
    </div>
  );
}

function eventConfig(trigger: TriggerSpec, every = 5): Schedule["schedule_config"] {
  const params = Object.fromEntries(trigger.params.filter((p) => p.default !== undefined).map((p) => [p.key, p.default]));
  return { provider: trigger.app, trigger: trigger.name, params, every_minutes: every };
}

/** "When something happens in <app>": which trigger, its settings, and how often to check. */
function EventTrigger({ value, onChange, triggers }: { value: Schedule; onChange: (next: Schedule) => void; triggers: TriggerSpec[] }) {
  const cfg = value.schedule_config ?? {};
  const current = triggers.find((t) => t.app === cfg.provider && t.name === cfg.trigger);
  const every = cfg.every_minutes ?? 5;
  const params = cfg.params ?? {};
  const byApp = React.useMemo(() => {
    const groups = new Map<string, TriggerSpec[]>();
    for (const t of triggers) groups.set(t.app_name, [...(groups.get(t.app_name) ?? []), t]);
    return [...groups.entries()];
  }, [triggers]);
  const setParam = (key: string, v: unknown) => onChange({ ...value, schedule_config: { ...cfg, params: { ...params, [key]: v } } });

  return (
    <>
      <div className="space-y-1.5 sm:col-span-2">
        <Label htmlFor="trigger-pick">When</Label>
        <Select
          value={current ? current.id : ""}
          onValueChange={(id) => {
            const next = triggers.find((t) => t.id === id);
            if (next) onChange({ ...value, schedule_config: eventConfig(next, every) });
          }}
        >
          <SelectTrigger id="trigger-pick" className="w-full" aria-label="What starts this automation">
            <SelectValue placeholder="Choose what starts this automation" />
          </SelectTrigger>
          <SelectContent>
            {byApp.map(([app, items]) => (
              <SelectGroup key={app}>
                <SelectLabel>{app}</SelectLabel>
                {items.map((t) => (
                  <SelectItem key={t.id} value={t.id} disabled={!t.available}>
                    {t.label}
                    {t.available ? null : <span className="ml-1 text-xs text-muted-foreground">· connect {t.app_name} first</span>}
                  </SelectItem>
                ))}
              </SelectGroup>
            ))}
          </SelectContent>
        </Select>
        {current ? <p className="text-xs text-muted-foreground">{current.description}</p> : null}
        {current && !current.available ? (
          <p className="text-xs">
            <Link href={`/app/settings/connections/${current.app}`} className="font-medium text-ai underline-offset-2 hover:underline">
              Connect {current.app_name}
            </Link>{" "}
            <span className="text-muted-foreground">to switch this automation on.</span>
          </p>
        ) : null}
      </div>
      {current?.params.map((p) => (
        <TriggerParam key={p.key} spec={p} value={params[p.key]} onChange={(v) => setParam(p.key, v)} />
      ))}
      <div className="space-y-1.5">
        <Label htmlFor="trigger-every">Check every</Label>
        <Select value={String(every)} onValueChange={(v) => onChange({ ...value, schedule_config: { ...cfg, every_minutes: Number(v) } })}>
          <SelectTrigger id="trigger-every" className="w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {CHECK_EVERY.map((m) => (
              <SelectItem key={m} value={String(m)}>
                {m === 60 ? "hour" : `${m} minutes`}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <p className="text-xs text-muted-foreground sm:col-span-2">
        Notely checks {current?.app_name ?? "the app"} every {every === 60 ? "hour" : `${every} minutes`} and runs once for each new item. The first check only notes what is already there, so turning this on never replays old items.
      </p>
    </>
  );
}

/** One trigger setting (a folder, a channel, "only from this sender"…). */
function TriggerParam({ spec, value, onChange }: { spec: InputSpec; value: unknown; onChange: (v: unknown) => void }) {
  const id = `trigger-param-${spec.key}`;
  const label = (
    <Label htmlFor={id}>
      {spec.label}
      {spec.required ? null : <span className="ml-1 font-normal text-muted-foreground">(optional)</span>}
    </Label>
  );
  if (spec.type === "boolean") {
    return (
      <div className="flex items-center justify-between gap-3 sm:col-span-2">
        {label}
        <Switch id={id} checked={Boolean(value)} onCheckedChange={onChange} />
      </div>
    );
  }
  if (spec.options?.length) {
    return (
      <div className="space-y-1.5">
        {label}
        <Select value={String(value ?? spec.default ?? "")} onValueChange={onChange}>
          <SelectTrigger id={id} className="w-full">
            <SelectValue placeholder="Choose…" />
          </SelectTrigger>
          <SelectContent>
            {spec.options.map((o) => (
              <SelectItem key={o.value} value={o.value}>
                {o.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {spec.help ? <p className="text-xs text-muted-foreground">{spec.help}</p> : null}
      </div>
    );
  }
  return (
    <div className="space-y-1.5">
      {label}
      <Input
        id={id}
        type={spec.type === "number" ? "number" : spec.type === "email" ? "email" : "text"}
        value={value === undefined || value === null ? "" : String(value)}
        placeholder={spec.placeholder}
        onChange={(e) => onChange(e.target.value === "" ? undefined : spec.type === "number" ? Number(e.target.value) : e.target.value)}
      />
      {spec.help ? <p className="text-xs text-muted-foreground">{spec.help}</p> : null}
    </div>
  );
}
