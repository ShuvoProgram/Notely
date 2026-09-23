"use client";

import * as React from "react";

import { X, type IconComponent } from "@/components/icons";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

export interface SelectionAction {
  id: string;
  label: string;
  icon: IconComponent;
  onRun: () => void;
  /** "destructive" reads red and sits last; "primary" is the emphasised action. */
  tone?: "primary" | "default" | "destructive";
  pending?: boolean;
  /** Ask first. Use for anything that can't be undone (delete forever, leave, delete tasks). */
  confirm?: { title: string; description: React.ReactNode; label: string };
}

/**
 * The list header while selecting: one fixed-height row, the same height as the header it
 * replaces, so nothing below moves when selection starts.
 *
 *   [☑ 3 selected]                       [Restore] [Delete forever]  [×]
 *
 * Labels show when the panel is wide enough and collapse to icon buttons (with tooltips and
 * accessible names) when it isn't, so the row never wraps. Actions that need a confirmation get
 * it here, so every list confirms the same way.
 */
export function SelectionBar({
  allState,
  count,
  total,
  noun,
  onSelectAll,
  onCancel,
  actions,
  className,
}: {
  allState: boolean | "indeterminate";
  count: number;
  total: number;
  noun: string;
  onSelectAll: (all: boolean) => void;
  onCancel: () => void;
  actions: SelectionAction[];
  className?: string;
}) {
  const [confirming, setConfirming] = React.useState<SelectionAction | null>(null);
  const all = allState === true;
  const one = noun.replace(/s$/, "");
  const label = count === 0 ? `Select ${noun}` : all && total > 1 ? `All ${total} selected` : `${count} selected`;
  const ordered = [...actions].sort((a, b) => rank(a) - rank(b));

  const run = (action: SelectionAction) => (action.confirm ? setConfirming(action) : action.onRun());

  return (
    <>
      <div
        role="toolbar"
        aria-label={`${one[0]?.toUpperCase()}${one.slice(1)} selection`}
        className={cn(
          "@container/selection flex h-10 min-w-0 items-center gap-1 rounded-xl bg-field pl-2.5 pr-1 ring-1 ring-glass-border motion-safe:animate-[notely-pop-in_180ms_var(--ease-liquid)_both]",
          className,
        )}
      >
        <label className="flex min-w-0 cursor-pointer items-center gap-2.5 py-1 pr-1">
          <Checkbox checked={allState} onCheckedChange={(v) => onSelectAll(v === true)} aria-label={all ? `Deselect all ${noun}` : `Select all ${noun}`} />
          <span className="truncate text-sm font-medium tabular-nums" aria-live="polite">
            {label}
          </span>
        </label>
        <div className="ml-auto flex shrink-0 items-center gap-0.5">
          {ordered.map((action) => (
            <ActionButton key={action.id} action={action} disabled={count === 0 || action.pending} onClick={() => run(action)} />
          ))}
          <span aria-hidden className="mx-0.5 h-5 w-px bg-glass-border" />
          <Tooltip>
            <TooltipTrigger asChild>
              <Button variant="ghost" size="icon-sm" onClick={onCancel} aria-label="Cancel selection" className="rounded-lg">
                <X aria-hidden />
              </Button>
            </TooltipTrigger>
            <TooltipContent>Cancel · Esc</TooltipContent>
          </Tooltip>
        </div>
      </div>
      {confirming?.confirm ? (
        <ConfirmDialog
          open
          onOpenChange={(open) => !open && setConfirming(null)}
          title={confirming.confirm.title}
          description={confirming.confirm.description}
          confirmLabel={confirming.confirm.label}
          destructive={confirming.tone === "destructive"}
          pending={confirming.pending}
          onConfirm={() => {
            confirming.onRun();
            setConfirming(null);
          }}
        />
      ) : null}
    </>
  );
}

const rank = (a: SelectionAction) => (a.tone === "primary" ? 0 : a.tone === "destructive" ? 2 : 1);

function ActionButton({ action, disabled, onClick }: { action: SelectionAction; disabled?: boolean; onClick: () => void }) {
  const destructive = action.tone === "destructive";
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          variant="ghost"
          size="sm"
          disabled={disabled}
          onClick={onClick}
          aria-label={action.label}
          className={cn(
            "rounded-lg px-2",
            destructive && "text-destructive hover:bg-destructive/10 hover:text-destructive",
            action.tone === "primary" && "text-foreground",
          )}
        >
          <action.icon aria-hidden />
          {/* Labels appear once the toolbar has room; below that the icon + tooltip carry it. */}
          <span className="hidden @[22rem]/selection:inline">{action.label}</span>
        </Button>
      </TooltipTrigger>
      <TooltipContent>{action.label}</TooltipContent>
    </Tooltip>
  );
}
