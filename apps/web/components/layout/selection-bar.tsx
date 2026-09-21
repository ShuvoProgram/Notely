"use client";

import { X, type LucideIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { cn } from "@/lib/utils";

/**
 * Contextual toolbar shown in place of a list's header while selecting. One row where it fits:
 * the tri-state "select all" box with the count, the destructive action and Cancel. On narrow
 * panels the actions wrap under the count instead of squeezing.
 */
export function SelectionBar({
  allState,
  count,
  total,
  noun,
  onSelectAll,
  onCancel,
  action,
  className,
}: {
  allState: boolean | "indeterminate";
  count: number;
  total: number;
  noun: string;
  onSelectAll: (all: boolean) => void;
  onCancel: () => void;
  action: { label: string; icon: LucideIcon; onClick: () => void };
  className?: string;
}) {
  const all = allState === true;
  const one = noun.replace(/s$/, "");
  const label = count === 0 ? `Select ${noun}` : all ? (total === 1 ? `The only ${one} selected` : `All ${total} ${noun} selected`) : `${count} selected`;
  return (
    <div role="toolbar" aria-label="Selection" className={cn("flex flex-wrap items-center gap-x-2 gap-y-1.5", className)}>
      <label className="flex cursor-pointer items-center gap-2.5 py-1">
        <Checkbox checked={allState} onCheckedChange={(v) => onSelectAll(v === true)} aria-label={all ? "Deselect all" : "Select all"} />
        <span className="whitespace-nowrap text-sm font-medium tabular-nums" aria-live="polite">
          {label}
        </span>
      </label>
      {/* Actions sit on the same row when there is room, and drop under the count when not. */}
      <div className="ml-auto flex shrink-0 items-center gap-1">
        <Button variant="ghost" size="sm" disabled={count === 0} onClick={action.onClick} className="text-destructive hover:bg-destructive/10 hover:text-destructive">
          <action.icon aria-hidden /> {action.label}
        </Button>
        <Button variant="ghost" size="sm" onClick={onCancel} aria-label="Cancel selection" className="text-muted-foreground">
          <X aria-hidden /> Cancel
        </Button>
      </div>
    </div>
  );
}
