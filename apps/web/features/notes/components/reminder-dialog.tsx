"use client";

import { BellOff } from "lucide-react";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { DatePicker, toIsoDate } from "@/components/ui/date-picker";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { TimePicker } from "@/components/ui/time-picker";
import { joinLocal, splitLocal } from "@/features/notes/lib";

/**
 * The one place a reminder is set, changed or removed. A real dialog (not a popover anchored to
 * a menu item) so opening it from the More menu is a clean hand-off: the menu closes, the
 * dialog owns focus until the user saves, removes or cancels.
 */
export function ReminderDialog({
  open,
  onOpenChange,
  value,
  onSave,
  onRemove,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Current reminder as an ISO timestamp, or null. */
  value: string | null;
  onSave: (iso: string) => void;
  onRemove: () => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-sm">
        {/* Mounted only while open, so the form seeds itself from the note each time. */}
        <ReminderForm value={value} onSave={onSave} onRemove={onRemove} onCancel={() => onOpenChange(false)} />
      </DialogContent>
    </Dialog>
  );
}

function ReminderForm({ value, onSave, onRemove, onCancel }: { value: string | null; onSave: (iso: string) => void; onRemove: () => void; onCancel: () => void }) {
  const [initial] = React.useState(() => ({ ...splitLocal(value), openedAt: Date.now() }));
  const [date, setDate] = React.useState(initial.date);
  const [time, setTime] = React.useState(initial.time || "09:00");

  const quick = (days: number, hour: number) => {
    const d = new Date();
    d.setDate(d.getDate() + days);
    setDate(toIsoDate(d));
    setTime(`${String(hour).padStart(2, "0")}:00`);
  };
  const iso = joinLocal(date, time);
  const inPast = iso ? new Date(iso).getTime() < initial.openedAt : false;

  return (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (iso) onSave(iso);
          }}
        >
          <DialogHeader>
            <DialogTitle>{value ? "Edit reminder" : "Remind me"}</DialogTitle>
            <DialogDescription>You’ll get a notification in Notely at this time.</DialogDescription>
          </DialogHeader>
          <div className="mt-4 space-y-4">
            <div className="flex flex-wrap gap-1.5">
              {(
                [
                  ["Later today", 0, 18],
                  ["Tomorrow", 1, 9],
                  ["Next week", 7, 9],
                ] as const
              ).map(([label, d, h]) => (
                <Button key={label} type="button" variant="outline" size="xs" className="rounded-full font-normal" onClick={() => quick(d, h)}>
                  {label}
                </Button>
              ))}
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="reminder-date">Date</Label>
              <DatePicker id="reminder-date" value={date} onChange={setDate} fromDate={new Date(new Date().setHours(0, 0, 0, 0))} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="reminder-time">Time</Label>
              <TimePicker id="reminder-time" value={time} onChange={setTime} />
            </div>
            {inPast ? <p className="text-xs text-warning">That time has already passed — the reminder will fire right away.</p> : null}
          </div>
          <DialogFooter className="mt-6 sm:justify-between">
            {value ? (
              <Button type="button" variant="ghost" className="text-muted-foreground hover:text-destructive" onClick={onRemove}>
                <BellOff aria-hidden /> Remove reminder
              </Button>
            ) : (
              <span />
            )}
            <div className="flex gap-2">
              <Button type="button" variant="outline" onClick={onCancel}>
                Cancel
              </Button>
              <Button type="submit" disabled={!iso}>
                {value ? "Save" : "Set reminder"}
              </Button>
            </div>
          </DialogFooter>
        </form>
  );
}
