"use client";

import { Clock, X } from "lucide-react";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/utils";

const HOURS = Array.from({ length: 12 }, (_, i) => i + 1);
const MINUTES = [0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55];

/** "HH:MM" (24h) → "10:30 AM"; "" → "". */
export function formatTime12(value: string): string {
  const parts = split(value);
  if (!parts) return "";
  const { h, m } = parts;
  const period = h >= 12 ? "PM" : "AM";
  const h12 = h % 12 === 0 ? 12 : h % 12;
  return `${h12}:${String(m).padStart(2, "0")} ${period}`;
}

function split(value: string): { h: number; m: number } | null {
  const match = /^(\d{1,2}):(\d{2})/.exec(value);
  if (!match) return null;
  const h = Number(match[1]);
  const m = Number(match[2]);
  if (h > 23 || m > 59) return null;
  return { h, m };
}

function join(h: number, m: number): string {
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}

/**
 * Typed times in most shapes people write them: "9", "9:30", "9.30pm", "21:05", "12 am".
 * Returns "HH:MM" or null when it cannot be read.
 */
export function parseTypedTime(text: string): string | null {
  const t = text.trim().toLowerCase().replace(/\s+/g, "");
  const match = /^(\d{1,2})(?:[:.h](\d{1,2}))?(am|pm|a|p)?$/.exec(t);
  if (!match) return null;
  let h = Number(match[1]);
  const m = match[2] ? Number(match[2]) : 0;
  const period = match[3];
  if (m > 59) return null;
  if (period) {
    if (h < 1 || h > 12) return null;
    if (period.startsWith("p") && h !== 12) h += 12;
    if (period.startsWith("a") && h === 12) h = 0;
  } else if (h > 23) return null;
  return join(h, m);
}

/**
 * Compact time field: hour / minute / AM–PM columns for the mouse, a text box for the keyboard
 * ("9:30pm" works), plus Now and Clear. Value is "HH:MM" in 24-hour form, or "" for none.
 */
export function TimePicker({
  id,
  value,
  onChange,
  disabled,
  placeholder = "Pick a time",
  className,
  "aria-label": ariaLabel,
}: {
  id?: string;
  value: string;
  onChange: (hhmm: string) => void;
  disabled?: boolean;
  placeholder?: string;
  className?: string;
  "aria-label"?: string;
}) {
  const [open, setOpen] = React.useState(false);
  const [typed, setTyped] = React.useState("");
  const [typedInvalid, setTypedInvalid] = React.useState(false);
  const parts = split(value);
  const h12 = parts ? (parts.h % 12 === 0 ? 12 : parts.h % 12) : null;
  const period: "AM" | "PM" = parts && parts.h >= 12 ? "PM" : "AM";

  const set = (next: { h12?: number; m?: number; period?: "AM" | "PM" }) => {
    const hh = next.h12 ?? h12 ?? 9;
    const mm = next.m ?? parts?.m ?? 0;
    const pp = next.period ?? (parts ? period : "AM");
    const h24 = pp === "PM" ? (hh % 12) + 12 : hh % 12;
    onChange(join(h24, mm));
  };

  const commitTyped = () => {
    if (!typed.trim()) return;
    const parsed = parseTypedTime(typed);
    if (!parsed) {
      setTypedInvalid(true);
      return;
    }
    onChange(parsed);
    setTyped("");
    setTypedInvalid(false);
    setOpen(false);
  };

  return (
    <Popover
      open={open}
      onOpenChange={(o) => {
        setOpen(o);
        if (o) {
          setTyped("");
          setTypedInvalid(false);
        }
      }}
    >
      <div className={cn("relative flex w-full", className)}>
        <PopoverTrigger asChild>
          <Button
            id={id}
            type="button"
            variant="outline"
            disabled={disabled}
            aria-label={ariaLabel}
            className={cn("w-full justify-start gap-2 bg-background/60 px-3 font-normal tabular-nums", !parts && "text-muted-foreground", parts && !disabled && "pr-9")}
          >
            <Clock className="size-4 text-muted-foreground" aria-hidden />
            <span className="min-w-0 flex-1 truncate text-left">{parts ? formatTime12(value) : placeholder}</span>
          </Button>
        </PopoverTrigger>
        {parts && !disabled ? (
          <Button type="button" variant="ghost" size="icon-xs" aria-label="Clear time" onClick={() => onChange("")} className="absolute right-1.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground">
            <X aria-hidden />
          </Button>
        ) : null}
      </div>
      <PopoverContent align="start" className="w-64 p-2">
        <Input
          aria-label="Type a time"
          placeholder="Type a time, e.g. 9:30 pm"
          value={typed}
          aria-invalid={typedInvalid || undefined}
          onChange={(e) => {
            setTyped(e.target.value);
            setTypedInvalid(false);
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              commitTyped();
            }
          }}
          onBlur={commitTyped}
          className="mb-2 h-8 text-sm"
        />
        <div className="grid grid-cols-[1fr_1fr_auto] gap-1.5" role="group" aria-label="Choose a time">
          <ul className="scrollbar-thin max-h-44 overflow-y-auto rounded-md border border-glass-border" aria-label="Hour">
            {HOURS.map((h) => (
              <li key={h}>
                <button
                  type="button"
                  aria-pressed={h12 === h}
                  onClick={() => set({ h12: h })}
                  className={cn("w-full px-2 py-1 text-center text-sm tabular-nums hover:bg-accent", h12 === h && "bg-primary text-primary-foreground hover:bg-primary")}
                >
                  {h}
                </button>
              </li>
            ))}
          </ul>
          <ul className="scrollbar-thin max-h-44 overflow-y-auto rounded-md border border-glass-border" aria-label="Minute">
            {MINUTES.map((m) => (
              <li key={m}>
                <button
                  type="button"
                  aria-pressed={parts?.m === m}
                  onClick={() => set({ m })}
                  className={cn("w-full px-2 py-1 text-center text-sm tabular-nums hover:bg-accent", parts?.m === m && "bg-primary text-primary-foreground hover:bg-primary")}
                >
                  {String(m).padStart(2, "0")}
                </button>
              </li>
            ))}
          </ul>
          <div className="flex flex-col gap-1" role="group" aria-label="AM or PM">
            {(["AM", "PM"] as const).map((p) => (
              <button
                key={p}
                type="button"
                aria-pressed={Boolean(parts) && period === p}
                onClick={() => set({ period: p })}
                className={cn("rounded-md border border-glass-border px-2.5 py-1 text-sm hover:bg-accent", parts && period === p && "bg-primary text-primary-foreground hover:bg-primary")}
              >
                {p}
              </button>
            ))}
          </div>
        </div>
        <div className="mt-2 flex items-center justify-between gap-2 border-t border-glass-border pt-2">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => {
              const now = new Date();
              onChange(join(now.getHours(), Math.ceil(now.getMinutes() / 5) * 5 === 60 ? 55 : Math.ceil(now.getMinutes() / 5) * 5));
              setOpen(false);
            }}
          >
            Now
          </Button>
          <div className="flex gap-1">
            <Button type="button" variant="ghost" size="sm" disabled={!parts} className="text-muted-foreground" onClick={() => onChange("")}>
              Clear
            </Button>
            <Button type="button" size="sm" disabled={!parts} onClick={() => setOpen(false)}>
              Done
            </Button>
          </div>
        </div>
      </PopoverContent>
    </Popover>
  );
}
