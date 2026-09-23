"use client";

import { AlertTriangle, ChevronDown, ChevronUp, X } from "@/components/icons";
import * as React from "react";

import { Button } from "@/components/ui/button";
import type { PendingApproval } from "@/features/ai/use-chat";
import type { AIProposal, RiskLevel } from "@/lib/api/types";
import { providerLabel } from "@/lib/providers";
import { cn } from "@/lib/utils";

const RISK_LABELS: Record<RiskLevel, string> = {
  read: "Read",
  write: "Change",
  external_communication: "Sends externally",
  destructive: "Destructive",
};

const AUTO_ADVANCE_MS = 420;
const SLIDE = "duration-[360ms] ease-[cubic-bezier(0.22,1,0.36,1)]";

/**
 * "Ready to execute" card. The proposed changes are reviewed one at a time: each is its own step
 * with "Do this" / "Skip this one", the stack slides between steps and the counter rolls. Nothing
 * runs until the user presses Approve. Picking an answer moves to the next change, but never
 * approves on its own. External actions are never hidden behind a generic "Done".
 */
export function ApprovalCard({ approval, onDecide, disabled }: { approval: PendingApproval; onDecide: (approvedCallIds: string[]) => void; disabled?: boolean }) {
  const proposals = approval.proposals;
  const count = proposals.length;
  const [step, setStep] = React.useState(0);
  const [skipped, setSkipped] = React.useState<Set<string>>(() => new Set());
  const advanceTimer = React.useRef<ReturnType<typeof setTimeout> | null>(null);
  const itemRefs = React.useRef<(HTMLDivElement | null)[]>([]);
  const [height, setHeight] = React.useState<number | undefined>(undefined);

  const approved = proposals.filter((p) => !skipped.has(p.call_id));
  const last = step === count - 1;
  const hasRisky = proposals.some((p) => p.risk === "destructive" || p.risk === "external_communication");

  // The viewport follows the active change's height, so the card grows and shrinks as you step.
  React.useEffect(() => {
    const el = itemRefs.current[step];
    if (!el) return;
    const observer = new ResizeObserver(() => setHeight(el.offsetHeight));
    observer.observe(el);
    return () => observer.disconnect();
  }, [step]);

  React.useEffect(() => () => {
    if (advanceTimer.current) clearTimeout(advanceTimer.current);
  }, []);

  const goTo = (next: number) => {
    if (advanceTimer.current) clearTimeout(advanceTimer.current);
    setStep(Math.min(Math.max(next, 0), count - 1));
  };

  const choose = (proposal: AIProposal, run: boolean) => {
    setSkipped((current) => {
      const next = new Set(current);
      if (run) next.delete(proposal.call_id);
      else next.add(proposal.call_id);
      return next;
    });
    if (advanceTimer.current) clearTimeout(advanceTimer.current);
    if (!last) advanceTimer.current = setTimeout(() => setStep((s) => Math.min(count - 1, s + 1)), AUTO_ADVANCE_MS);
  };

  const approveLabel = approved.length === count ? (count === 1 ? "Approve" : "Approve all") : `Approve ${approved.length} of ${count}`;

  return (
    <section
      aria-labelledby="approval-title"
      className="w-full max-w-md overflow-hidden glass-2 rounded-2xl motion-safe:animate-[notely-fade-up_380ms_cubic-bezier(0.23,1,0.32,1)_both]"
    >
      <header className="flex items-center gap-2 px-4 pt-3.5">
        <span className="size-1.5 rounded-full bg-ai motion-safe:animate-pulse" aria-hidden />
        <h3 id="approval-title" className="text-xs font-medium text-muted-foreground">
          Ready to execute
        </h3>
        <span className="text-xs text-tertiary">
          · {count} {count === 1 ? "change" : "changes"}
        </span>
        <button
          type="button"
          aria-label="Dismiss and cancel"
          disabled={disabled}
          onClick={() => onDecide([])}
          className="ml-auto grid size-6 place-items-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground disabled:opacity-(--disabled-opacity)"
        >
          <X className="size-3.5" aria-hidden />
        </button>
      </header>

      <div className={cn("overflow-hidden px-4 pb-4 pt-2 transition-[height]", SLIDE)} style={{ height: height === undefined ? undefined : height + 24 }}>
        <div className="grid">
          {proposals.map((p, i) => {
            const active = i === step;
            const run = !skipped.has(p.call_id);
            return (
              <div
                key={p.call_id}
                ref={(el) => {
                  itemRefs.current[i] = el;
                }}
                inert={!active}
                aria-hidden={!active || undefined}
                className={cn(
                  "col-start-1 row-start-1 self-start transition-[opacity,transform] motion-reduce:transition-none",
                  SLIDE,
                  active ? "translate-y-0 opacity-100" : i < step ? "-translate-y-4 opacity-0" : "translate-y-4 opacity-0",
                )}
              >
                <div className="flex flex-wrap items-center gap-1.5 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                  {providerLabel(p.provider)}
                  <span
                    className={cn(
                      "rounded-full px-1.5 py-px normal-case tracking-normal",
                      p.risk === "write" || p.risk === "read" ? "bg-muted text-muted-foreground" : "bg-destructive/15 text-destructive",
                    )}
                  >
                    {RISK_LABELS[p.risk]}
                  </span>
                </div>
                <p className="mt-1 pr-2 text-sm font-medium text-foreground">{p.summary}</p>
                <ArgumentsPreview args={p.arguments} />
                {count > 1 ? (
                  <div role="radiogroup" aria-label={`Run “${p.summary}”?`} className="mt-3 flex flex-col gap-0.5">
                    <Choice checked={run} disabled={disabled} onSelect={() => choose(p, true)}>
                      Do this
                    </Choice>
                    <Choice checked={!run} disabled={disabled} onSelect={() => choose(p, false)}>
                      Skip this one
                    </Choice>
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>
      </div>

      {hasRisky ? (
        <p className="flex items-center gap-1.5 px-4 pb-3 text-xs text-warning">
          <AlertTriangle className="size-3.5 shrink-0" aria-hidden /> Some of these actions leave Notely or can&apos;t be undone.
        </p>
      ) : null}

      <footer className="flex items-center justify-between gap-3 border-t border-glass-border bg-muted/30 px-3 py-2">
        {count > 1 ? (
          <div className="flex items-center gap-0.5 text-muted-foreground">
            <button
              type="button"
              aria-label="Previous change"
              disabled={step === 0}
              onClick={() => goTo(step - 1)}
              className="grid size-6 place-items-center rounded-md transition-colors enabled:hover:text-foreground disabled:opacity-(--disabled-opacity)"
            >
              <ChevronUp className="size-3.5" aria-hidden />
            </button>
            <span className="inline-flex items-center text-xs font-medium tabular-nums" aria-live="polite">
              <RollingNumber value={step + 1} />
              <span className="px-1">/</span>
              {count}
            </span>
            <button
              type="button"
              aria-label="Next change"
              disabled={last}
              onClick={() => goTo(step + 1)}
              className="grid size-6 place-items-center rounded-md transition-colors enabled:hover:text-foreground disabled:opacity-(--disabled-opacity)"
            >
              <ChevronDown className="size-3.5" aria-hidden />
            </button>
          </div>
        ) : (
          <span />
        )}
        <div className="flex items-center gap-1.5">
          {count > 1 && !last ? (
            <Button variant="ghost" size="sm" className="rounded-full" disabled={disabled} onClick={() => goTo(step + 1)}>
              Next
            </Button>
          ) : (
            <Button variant="ghost" size="sm" className="rounded-full" disabled={disabled} onClick={() => onDecide([])}>
              {count === 1 ? "Cancel" : "Cancel all"}
            </Button>
          )}
          <Button size="sm" className="rounded-full px-4" disabled={disabled || approved.length === 0} onClick={() => onDecide(approved.map((p) => p.call_id))}>
            {approveLabel}
          </Button>
        </div>
      </footer>
    </section>
  );
}

function Choice({ checked, disabled, onSelect, children }: { checked: boolean; disabled?: boolean; onSelect: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={checked}
      disabled={disabled}
      onClick={onSelect}
      className="-ml-1 flex items-center gap-2 rounded-md py-1 pl-1 pr-2 text-left text-[13px] transition-colors hover:bg-muted/60 disabled:opacity-(--disabled-opacity)"
    >
      <span
        className={cn(
          "grid size-4 shrink-0 place-items-center rounded-full transition-colors duration-200",
          checked ? "bg-foreground" : "shadow-[inset_0_0_0_1.5px_var(--border)]",
        )}
        aria-hidden
      >
        <span className={cn("size-1.5 rounded-full bg-background transition-transform duration-200", checked ? "scale-100" : "scale-0")} />
      </span>
      <span className={checked ? "text-foreground" : "text-muted-foreground"}>{children}</span>
    </button>
  );
}

/** The step number rolls up when moving forward and down when moving back, like an odometer. */
function RollingNumber({ value }: { value: number }) {
  const [prev, setPrev] = React.useState(value);
  const [dir, setDir] = React.useState<"up" | "down">("up");
  if (prev !== value) {
    setDir(value > prev ? "up" : "down");
    setPrev(value);
  }
  return (
    <span className="relative inline-block overflow-hidden leading-none">
      <span
        key={value}
        className={cn(
          "inline-block motion-safe:animate-[notely-roll-up_320ms_cubic-bezier(0.4,0,0.2,1)_both]",
          dir === "down" && "motion-safe:animate-[notely-roll-down_320ms_cubic-bezier(0.4,0,0.2,1)_both]",
        )}
      >
        {value}
      </span>
    </span>
  );
}

function ArgumentsPreview({ args }: { args: Record<string, unknown> }) {
  const entries = Object.entries(args).filter(([k, v]) => k !== "title" && v !== null && v !== undefined && v !== "" && v !== "none");
  if (!entries.length) return null;
  return (
    <dl className="mt-1.5 grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-xs text-muted-foreground">
      {entries.map(([k, v]) => (
        <React.Fragment key={k}>
          <dt className="capitalize">{k.replace(/_/g, " ")}</dt>
          <dd className="truncate">{typeof v === "string" ? v : JSON.stringify(v)}</dd>
        </React.Fragment>
      ))}
    </dl>
  );
}
