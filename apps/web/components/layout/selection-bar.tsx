"use client";

import { Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { cn } from "@/lib/utils";

/**
 * The bar shown while a list is in selection mode: select-all, the count, one destructive
 * action and Cancel. Shared by Notes and Tasks so bulk actions feel identical.
 */
export function SelectionBar({
  selected,
  total,
  noun,
  onSelectAll,
  onClear,
  onDelete,
  deleteLabel = "Delete",
  className,
}: {
  selected: number;
  total: number;
  noun: string;
  onSelectAll: (all: boolean) => void;
  onClear: () => void;
  onDelete: () => void;
  deleteLabel?: string;
  className?: string;
}) {
  const all = total > 0 && selected === total;
  return (
    <div role="toolbar" aria-label="Selection" className={cn("flex flex-wrap items-center gap-x-3 gap-y-2 rounded-xl border border-glass-border bg-muted/40 px-3 py-2 text-sm", className)}>
      <label className="flex cursor-pointer items-center gap-2">
        <Checkbox checked={all ? true : selected > 0 ? "indeterminate" : false} onCheckedChange={(v) => onSelectAll(v === true)} aria-label="Select all" />
        <span className="text-muted-foreground">Select all</span>
      </label>
      <span className="tabular-nums" aria-live="polite">
        {selected} selected
      </span>
      <div className="ml-auto flex items-center gap-1.5">
        <Button variant="destructive" size="sm" disabled={selected === 0} onClick={onDelete}>
          <Trash2 aria-hidden /> {deleteLabel}
        </Button>
        <Button variant="ghost" size="sm" onClick={onClear}>
          Cancel
        </Button>
      </div>
      <span className="sr-only">{noun}</span>
    </div>
  );
}
