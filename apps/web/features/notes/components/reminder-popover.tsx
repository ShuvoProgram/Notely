"use client";

import { Bell, BellOff } from "lucide-react";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { joinLocal, reminderLabel, splitLocal } from "@/features/notes/lib";
import { cn } from "@/lib/utils";

/**
 * "Remind me": one small card with a date and a time. Saving writes the reminder; a passed
 * reminder can be cleared or moved. The trigger doubles as the status chip.
 */
export function ReminderPopover({
  value,
  onChange,
  disabled,
  trigger,
  open: controlledOpen,
  onOpenChange,
}: {
  value: string | null;
  onChange: (iso: string | null) => void;
  disabled?: boolean;
  trigger?: React.ReactNode;
  /** Optional controlled open state, so a menu item elsewhere can open the card. */
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
}) {
  const [innerOpen, setInnerOpen] = React.useState(false);
  const open = controlledOpen ?? innerOpen;
  const setOpen = (o: boolean) => {
    setInnerOpen(o);
    onOpenChange?.(o);
  };
  const initial = splitLocal(value);
  const [date, setDate] = React.useState(initial.date);
  const [time, setTime] = React.useState(initial.time || "09:00");
  const label = value ? reminderLabel(value) : null;

  const quick = (days: number, hour: number) => {
    const d = new Date();
    d.setDate(d.getDate() + days);
    const pad = (n: number) => String(n).padStart(2, "0");
    setDate(`${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`);
    setTime(`${pad(hour)}:00`);
  };

  return (
    <Popover
      open={open}
      onOpenChange={(o) => {
        setOpen(o);
        if (o) {
          const next = splitLocal(value);
          setDate(next.date);
          setTime(next.time || "09:00");
        }
      }}
    >
      <PopoverTrigger asChild>
        {trigger ?? (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            disabled={disabled}
            className={cn("h-7 gap-1.5 rounded-md px-2 text-xs font-normal", label ? (label.passed ? "text-muted-foreground" : "text-ai") : "text-muted-foreground")}
          >
            <Bell className="size-3.5" aria-hidden />
            {label ? label.text : "Remind me"}
          </Button>
        )}
      </PopoverTrigger>
      <PopoverContent align="start" className="w-72 p-3">
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            const iso = joinLocal(date, time);
            if (iso) onChange(iso);
            setOpen(false);
          }}
        >
          <p className="text-sm font-medium">Remind me</p>
          <div className="flex flex-wrap gap-1.5">
            {[
              ["Later today", 0, 18],
              ["Tomorrow", 1, 9],
              ["Next week", 7, 9],
            ].map(([l, d, h]) => (
              <Button key={String(l)} type="button" variant="outline" size="xs" className="rounded-full font-normal" onClick={() => quick(Number(d), Number(h))}>
                {l}
              </Button>
            ))}
          </div>
          <div className="grid grid-cols-[1fr_auto] gap-2">
            <div className="space-y-1">
              <Label htmlFor="reminder-date" className="text-xs text-muted-foreground">
                Date
              </Label>
              <Input id="reminder-date" type="date" value={date} onChange={(e) => setDate(e.target.value)} required />
            </div>
            <div className="space-y-1">
              <Label htmlFor="reminder-time" className="text-xs text-muted-foreground">
                Time
              </Label>
              <Input id="reminder-time" type="time" value={time} onChange={(e) => setTime(e.target.value)} className="w-28" />
            </div>
          </div>
          <div className="flex items-center justify-between gap-2 pt-1">
            {value ? (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="text-muted-foreground hover:text-destructive"
                onClick={() => {
                  onChange(null);
                  setOpen(false);
                }}
              >
                <BellOff aria-hidden /> Remove
              </Button>
            ) : (
              <span />
            )}
            <Button type="submit" size="sm" disabled={!date}>
              {value ? "Update" : "Set reminder"}
            </Button>
          </div>
        </form>
      </PopoverContent>
    </Popover>
  );
}
