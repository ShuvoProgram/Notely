"use client";

import { format, isValid, parse } from "date-fns";
import { CalendarIcon, X } from "@/components/icons";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/utils";

const ISO = "yyyy-MM-dd";

export function parseIsoDate(value: string | null | undefined): Date | undefined {
  if (!value) return undefined;
  const d = parse(value, ISO, new Date());
  return isValid(d) ? d : undefined;
}

export function toIsoDate(d: Date): string {
  return format(d, ISO);
}

/**
 * Calendar-in-a-popover date field. Value is a local "YYYY-MM-DD" string (or "" for none) so
 * it slots into the same state the API uses for due dates and reminders.
 */
export function DatePicker({
  id,
  value,
  onChange,
  placeholder = "Pick a date",
  disabled,
  className,
  fromDate,
  "aria-label": ariaLabel,
  "aria-invalid": ariaInvalid,
}: {
  id?: string;
  value: string;
  onChange: (iso: string) => void;
  placeholder?: string;
  disabled?: boolean;
  className?: string;
  /** Earliest selectable day (e.g. today for reminders). */
  fromDate?: Date;
  "aria-label"?: string;
  "aria-invalid"?: boolean;
}) {
  const [open, setOpen] = React.useState(false);
  const selected = parseIsoDate(value);
  const [month, setMonth] = React.useState<Date>(selected ?? new Date());

  return (
    <Popover
      open={open}
      onOpenChange={(o) => {
        if (o) setMonth(selected ?? new Date());
        setOpen(o);
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
            aria-invalid={ariaInvalid}
            className={cn("w-full justify-start gap-2 bg-field px-3 font-normal", !selected && "text-muted-foreground", selected && !disabled && "pr-9")}
          >
            <CalendarIcon className="size-4 text-muted-foreground" aria-hidden />
            <span className="min-w-0 flex-1 truncate text-left">{selected ? format(selected, "EEE, MMM d, yyyy") : placeholder}</span>
          </Button>
        </PopoverTrigger>
        {selected && !disabled ? (
          <Button type="button" variant="ghost" size="icon-xs" aria-label="Clear date" onClick={() => onChange("")} className="absolute right-1.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground">
            <X aria-hidden />
          </Button>
        ) : null}
      </div>
      <PopoverContent align="start" className="w-auto p-0">
        <Calendar
          mode="single"
          selected={selected}
          month={month}
          onMonthChange={setMonth}
          disabled={fromDate ? { before: fromDate } : undefined}
          onSelect={(d) => {
            if (d) onChange(toIsoDate(d));
            setOpen(false);
          }}
          autoFocus
        />
        <div className="flex items-center justify-between gap-2 border-t border-glass-border px-2 py-1.5">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => {
              onChange(toIsoDate(new Date()));
              setOpen(false);
            }}
          >
            Today
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            disabled={!selected}
            className="text-muted-foreground"
            onClick={() => {
              onChange("");
              setOpen(false);
            }}
          >
            Clear
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  );
}
