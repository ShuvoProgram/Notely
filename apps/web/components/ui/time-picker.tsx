"use client";

import * as React from "react";

import { Clock, X } from "@/components/icons";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/utils";

/*
 * The app's one time picker: an analog clock. Value is "HH:MM" (24-hour) or "" for none, the same
 * shape the API stores for task due times, reminders and automation schedules.
 *
 *   ┌──────────────────────────┐
 *   │   [ 9 ] : [ 35 ]  AM|PM  │  readout: which hand you're setting, and the half of the day
 *   │         ╭──────╮         │
 *   │       ╱   12    ╲        │  a real face: 60 ticks, 12 numerals, an hour hand that
 *   │      │ 9   ●──  3│       │  creeps with the minutes, a minute hand, a centre pin
 *   │       ╲    6    ╱        │
 *   │  [Type a time        ]   │  "9:35pm", "21:35", "935"
 *   │  Now        Clear  [Set] │
 *   └──────────────────────────┘
 *
 * Drag either hand (minute precision), or tap (hours snap to the numeral, minutes to 5). The face
 * is a slider for keyboards: ←/→ ±1, PgUp/PgDn ±5 minutes (±3 hours), Home/End.
 */

type Mode = "hour" | "minute";
interface HM {
  h: number; // 0–23
  m: number; // 0–59
}

const pad = (n: number) => String(n).padStart(2, "0");

function split(value: string): HM | null {
  const match = /^(\d{1,2}):(\d{2})/.exec(value);
  if (!match) return null;
  const h = Number(match[1]);
  const m = Number(match[2]);
  return h <= 23 && m <= 59 ? { h, m } : null;
}

const join = ({ h, m }: HM) => `${pad(h)}:${pad(m)}`;

/** "HH:MM" (24h) → "9:30 AM"; "" → "". */
export function formatTime12(value: string): string {
  const t = split(value);
  return t ? `${t.h % 12 || 12}:${pad(t.m)} ${t.h >= 12 ? "PM" : "AM"}` : "";
}

/**
 * Typed times in most shapes people write them: "9", "9:30", "9.30pm", "21:05", "12 am", "930".
 * Returns "HH:MM" or null when it can't be read.
 */
export function parseTypedTime(text: string): string | null {
  const t = text.trim().toLowerCase().replace(/\s+/g, "");
  let match = /^(\d{1,2})(?:[:.h](\d{1,2}))?(am|pm|a|p)?$/.exec(t);
  if (!match) {
    const compact = /^(\d{1,2})(\d{2})(am|pm|a|p)?$/.exec(t); // "930", "2145"
    if (!compact) return null;
    match = compact;
  }
  let h = Number(match[1]);
  const m = match[2] ? Number(match[2]) : 0;
  const period = match[3];
  if (m > 59) return null;
  if (period) {
    if (h < 1 || h > 12) return null;
    if (period.startsWith("p") && h !== 12) h += 12;
    if (period.startsWith("a") && h === 12) h = 0;
  } else if (h > 23) return null;
  return join({ h, m });
}

// --- geometry (SVG viewBox 0 0 240 240) ----------------------------------------------------------

const C = 120;
const polar = (deg: number, r: number) => {
  const a = ((deg - 90) * Math.PI) / 180;
  return { x: C + r * Math.cos(a), y: C + r * Math.sin(a) };
};
const hourAngle = ({ h, m }: HM) => ((h % 12) + m / 60) * 30;
const minuteAngle = ({ m }: HM) => m * 6;

export function TimePicker({
  id,
  value,
  onChange,
  disabled,
  placeholder = "Pick a time",
  className,
  "aria-label": ariaLabel,
  "aria-invalid": ariaInvalid,
}: {
  id?: string;
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
  placeholder?: string;
  className?: string;
  "aria-label"?: string;
  "aria-invalid"?: boolean;
}) {
  const [open, setOpen] = React.useState(false);
  const current = split(value);

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <div className={cn("relative flex w-full", className)}>
        <PopoverTrigger asChild>
          <Button
            id={id}
            type="button"
            variant="outline"
            disabled={disabled}
            aria-label={ariaLabel}
            aria-invalid={ariaInvalid}
            className={cn("w-full justify-start gap-2 bg-field px-3 font-normal", !current && "text-muted-foreground", current && !disabled && "pr-9")}
          >
            <Clock className="size-4 text-muted-foreground" aria-hidden />
            <span className="min-w-0 flex-1 truncate text-left tabular-nums">{current ? formatTime12(value) : placeholder}</span>
          </Button>
        </PopoverTrigger>
        {current && !disabled ? (
          <Button type="button" variant="ghost" size="icon-xs" aria-label="Clear time" onClick={() => onChange("")} className="absolute right-1.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground">
            <X aria-hidden />
          </Button>
        ) : null}
      </div>
      <PopoverContent align="start" className="w-[min(18rem,calc(100vw-1.5rem))] p-3">
        {/* Remounted on every open, so the draft always starts from the saved value. */}
        {open ? (
          <ClockPanel
            initial={current}
            onCommit={(next) => {
              onChange(next);
              setOpen(false);
            }}
          />
        ) : null}
      </PopoverContent>
    </Popover>
  );
}

function ClockPanel({ initial, onCommit }: { initial: HM | null; onCommit: (value: string) => void }) {
  const [draft, setDraft] = React.useState<HM>(initial ?? { h: 9, m: 0 });
  const [mode, setMode] = React.useState<Mode>("hour");
  const [typed, setTyped] = React.useState("");
  const [typedError, setTypedError] = React.useState(false);
  const pm = draft.h >= 12;

  const setHour12 = (h12: number) => setDraft((d) => ({ ...d, h: (h12 % 12) + (d.h >= 12 ? 12 : 0) }));
  const setMinute = (m: number) => setDraft((d) => ({ ...d, m: ((m % 60) + 60) % 60 }));
  const setPeriod = (toPm: boolean) => setDraft((d) => ({ ...d, h: (d.h % 12) + (toPm ? 12 : 0) }));

  const commitTyped = () => {
    const parsed = parseTypedTime(typed);
    if (!parsed) {
      setTypedError(true);
      return;
    }
    onCommit(parsed);
  };

  return (
    <div className="flex flex-col gap-2.5">
      {/* Readout: tap a part to set it with the clock. */}
      <div className="flex items-center justify-center gap-3">
        <div className="flex items-baseline gap-0.5 text-2xl font-bold tabular-nums tracking-tight">
          <ReadoutPart active={mode === "hour"} onClick={() => setMode("hour")} label={`Hour, ${draft.h % 12 || 12}`}>
            {draft.h % 12 || 12}
          </ReadoutPart>
          <span aria-hidden className="text-muted-foreground">
            :
          </span>
          <ReadoutPart active={mode === "minute"} onClick={() => setMode("minute")} label={`Minutes, ${pad(draft.m)}`}>
            {pad(draft.m)}
          </ReadoutPart>
        </div>
        <div role="radiogroup" aria-label="AM or PM" className="flex flex-col gap-0.5 rounded-lg bg-field p-0.5 ring-1 ring-glass-border">
          {(["AM", "PM"] as const).map((p) => {
            const on = (p === "PM") === pm;
            return (
              <button
                key={p}
                type="button"
                role="radio"
                aria-checked={on}
                onClick={() => setPeriod(p === "PM")}
                className={cn(
                  "cursor-pointer rounded-md px-2 py-0.5 text-xs font-bold transition-colors outline-none focus-visible:ring-2 focus-visible:ring-ring",
                  on ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-accent hover:text-foreground",
                )}
              >
                {p}
              </button>
            );
          })}
        </div>
      </div>

      <ClockFace
        time={draft}
        mode={mode}
        onHour={(h12, final) => {
          setHour12(h12);
          if (final) setMode("minute");
        }}
        onMinute={setMinute}
      />

      <div className="grid gap-1">
        <label htmlFor="time-typed" className="sr-only">
          Type a time
        </label>
        <Input
          id="time-typed"
          aria-label="Type a time"
          aria-invalid={typedError || undefined}
          aria-describedby={typedError ? "time-typed-error" : undefined}
          value={typed}
          inputMode="text"
          autoComplete="off"
          placeholder="Or type it, e.g. 9:35 pm"
          onChange={(e) => {
            setTyped(e.target.value);
            setTypedError(false);
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              commitTyped();
            }
          }}
          className="h-9"
        />
        {typedError ? (
          <p id="time-typed-error" role="alert" className="text-xs text-destructive">
            Try a time like 9:35 pm or 21:35.
          </p>
        ) : null}
      </div>

      <div className="flex items-center gap-2 border-t border-glass-border pt-2.5">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => {
            const now = new Date();
            setDraft({ h: now.getHours(), m: now.getMinutes() });
            setMode("minute");
          }}
        >
          Now
        </Button>
        <Button type="button" variant="ghost" size="sm" className="ml-auto text-muted-foreground" onClick={() => onCommit("")}>
          Clear
        </Button>
        <Button type="button" size="sm" onClick={() => (typed.trim() ? commitTyped() : onCommit(join(draft)))}>
          Set time
        </Button>
      </div>
    </div>
  );
}

function ReadoutPart({ active, onClick, label, children }: { active: boolean; onClick: () => void; label: string; children: React.ReactNode }) {
  return (
    <button
      type="button"
      aria-pressed={active}
      aria-label={label}
      onClick={onClick}
      className={cn(
        "min-w-[2ch] cursor-pointer rounded-lg px-1.5 py-0.5 text-center transition-colors outline-none focus-visible:ring-2 focus-visible:ring-ring",
        active ? "bg-ai-soft text-foreground ring-1 ring-ai/40" : "text-muted-foreground hover:bg-accent hover:text-foreground",
      )}
    >
      {children}
    </button>
  );
}

function ClockFace({
  time,
  mode,
  onHour,
  onMinute,
}: {
  time: HM;
  mode: Mode;
  onHour: (h12: number, final: boolean) => void;
  onMinute: (m: number) => void;
}) {
  const svgRef = React.useRef<SVGSVGElement>(null);
  const drag = React.useRef<{ moved: boolean; x: number; y: number } | null>(null);
  const h12 = time.h % 12 || 12;

  /** Angle (0 = 12 o'clock, clockwise) of a pointer event relative to the face centre. */
  const angleOf = (e: React.PointerEvent) => {
    const rect = svgRef.current!.getBoundingClientRect();
    const dx = e.clientX - (rect.left + rect.width / 2);
    const dy = e.clientY - (rect.top + rect.height / 2);
    return (Math.atan2(dy, dx) * 180) / Math.PI + 90 + 360;
  };

  const apply = (e: React.PointerEvent, final: boolean) => {
    const deg = angleOf(e) % 360;
    if (mode === "hour") {
      onHour(Math.round(deg / 30) % 12 || 12, final);
    } else {
      // Dragging is minute-precise; a tap snaps to the nearest five, which is easier on touch.
      const m = drag.current?.moved ? Math.round(deg / 6) % 60 : (Math.round(deg / 30) * 5) % 60;
      onMinute(m);
    }
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    const step = { ArrowRight: 1, ArrowUp: 1, ArrowLeft: -1, ArrowDown: -1, PageUp: mode === "hour" ? 3 : 5, PageDown: mode === "hour" ? -3 : -5 }[e.key];
    if (step !== undefined) {
      e.preventDefault();
      if (mode === "hour") onHour((((h12 - 1 + step) % 12) + 12) % 12 + 1, false);
      else onMinute(time.m + step);
    } else if (e.key === "Home" || e.key === "End") {
      e.preventDefault();
      if (mode === "hour") onHour(e.key === "Home" ? 12 : 11, false);
      else onMinute(e.key === "Home" ? 0 : 59);
    } else if (e.key === "Enter" && mode === "hour") {
      e.preventDefault();
      onHour(h12, true);
    }
  };

  const hourTip = polar(hourAngle(time), 50);
  const minuteTip = polar(minuteAngle(time), 80);
  const minuteKnob = polar(minuteAngle(time), 96);
  const valueText = mode === "hour" ? `${h12} ${time.h >= 12 ? "PM" : "AM"}` : `${pad(time.m)} minutes`;

  return (
    <svg
      ref={svgRef}
      viewBox="0 0 240 240"
      role="slider"
      tabIndex={0}
      aria-label={mode === "hour" ? "Hour" : "Minutes"}
      aria-valuemin={mode === "hour" ? 1 : 0}
      aria-valuemax={mode === "hour" ? 12 : 59}
      aria-valuenow={mode === "hour" ? h12 : time.m}
      aria-valuetext={valueText}
      onKeyDown={onKeyDown}
      onPointerDown={(e) => {
        e.currentTarget.setPointerCapture(e.pointerId);
        drag.current = { moved: false, x: e.clientX, y: e.clientY };
        apply(e, false);
      }}
      onPointerMove={(e) => {
        if (!drag.current) return;
        if (Math.hypot(e.clientX - drag.current.x, e.clientY - drag.current.y) > 4) drag.current.moved = true;
        if (drag.current.moved) apply(e, false);
      }}
      onPointerUp={(e) => {
        if (drag.current) apply(e, true);
        drag.current = null;
      }}
      onPointerCancel={() => (drag.current = null)}
      className="mx-auto aspect-square w-full max-w-[clamp(9rem,calc(var(--radix-popover-content-available-height,40rem)-12rem),13rem)] cursor-pointer touch-none select-none rounded-full outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-transparent"
    >
      {/* face */}
      <circle cx={C} cy={C} r={116} fill="var(--field)" stroke="var(--glass-border-strong)" strokeWidth={1} />
      {/* minute ticks: every minute, longer and stronger every five */}
      {Array.from({ length: 60 }, (_, i) => {
        const major = i % 5 === 0;
        const a = polar(i * 6, 110);
        const b = polar(i * 6, major ? 100 : 105);
        const selected = mode === "minute" && i === time.m;
        return (
          <line
            key={i}
            x1={a.x}
            y1={a.y}
            x2={b.x}
            y2={b.y}
            stroke={selected ? "var(--ai)" : major ? "var(--foreground)" : "var(--foreground-muted)"}
            strokeWidth={selected ? 2.5 : major ? 2 : 1}
            strokeLinecap="round"
            opacity={major || selected ? 1 : 0.7}
          />
        );
      })}
      {/* numerals */}
      {Array.from({ length: 12 }, (_, i) => {
        const n = i + 1;
        const p = polar(n * 30, 82);
        const selected = mode === "hour" && n === h12;
        return (
          <g key={n}>
            {selected ? <circle cx={p.x} cy={p.y} r={15} fill="var(--ai)" /> : null}
            <text
              x={p.x}
              y={p.y}
              textAnchor="middle"
              dominantBaseline="central"
              fontSize={n % 3 === 0 ? 17 : 15}
              fontWeight={700}
              fill={selected ? "var(--primary-foreground)" : "var(--foreground)"}
              opacity={mode === "minute" ? 0.55 : 1}
            >
              {n}
            </text>
          </g>
        );
      })}
      {/* minute labels, only while setting minutes */}
      {mode === "minute"
        ? Array.from({ length: 12 }, (_, i) => {
            const p = polar(i * 30, 62);
            return (
              <text key={i} x={p.x} y={p.y} textAnchor="middle" dominantBaseline="central" fontSize={10} fontWeight={500} fill="var(--foreground-muted)">
                {pad(i * 5)}
              </text>
            );
          })
        : null}
      {/* hands: the one being set is green with a knob at its tip */}
      <g className="motion-safe:[&>line]:transition-[x2,y2] motion-safe:[&>line]:duration-200">
        <line x1={C} y1={C} x2={hourTip.x} y2={hourTip.y} stroke={mode === "hour" ? "var(--ai)" : "var(--foreground)"} strokeWidth={6} strokeLinecap="round" />
        <line x1={C} y1={C} x2={minuteTip.x} y2={minuteTip.y} stroke={mode === "minute" ? "var(--ai)" : "var(--foreground-secondary)"} strokeWidth={3.5} strokeLinecap="round" />
      </g>
      {mode === "minute" ? <circle cx={minuteKnob.x} cy={minuteKnob.y} r={6} fill="var(--ai)" stroke="var(--background)" strokeWidth={2} /> : null}
      {/* centre pin */}
      <circle cx={C} cy={C} r={7} fill="var(--ai)" />
      <circle cx={C} cy={C} r={2.5} fill="var(--background)" />
    </svg>
  );
}
