"use client";

import { AlertTriangle, Sparkles } from "lucide-react";
import * as React from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { PendingApproval } from "@/features/ai/use-chat";
import type { RiskLevel } from "@/lib/api/types";
import { providerLabel } from "@/lib/providers";
const RISK_LABELS: Record<RiskLevel, string> = {
  read: "Read",
  write: "Change",
  external_communication: "Sends externally",
  destructive: "Destructive",
};

/**
 * "Ready to execute" card. Every proposed change is listed with a checkbox; nothing runs until
 * the user reviews and approves. External actions are never hidden behind a generic "Done".
 */
export function ApprovalCard({ approval, onDecide, disabled }: { approval: PendingApproval; onDecide: (approvedCallIds: string[]) => void; disabled?: boolean }) {
  const [selected, setSelected] = React.useState<Set<string>>(() => new Set(approval.proposals.map((p) => p.call_id)));
  const proposals = approval.proposals;
  const grouped = React.useMemo(() => {
    const map = new Map<string, typeof proposals>();
    for (const p of proposals) {
      const list = map.get(p.provider) ?? [];
      list.push(p);
      map.set(p.provider, list);
    }
    return [...map.entries()];
  }, [proposals]);
  const count = approval.proposals.length;
  const hasDestructive = approval.proposals.some((p) => p.risk === "destructive" || p.risk === "external_communication");

  return (
    <section aria-labelledby="approval-title" className="rounded-xl border border-ai/40 bg-ai-soft/40 p-4">
      <div className="flex items-center gap-2">
        <Sparkles className="size-4 text-ai" aria-hidden />
        <h3 id="approval-title" className="text-sm font-semibold">
          Ready to execute
        </h3>
      </div>
      <p className="mt-1 text-sm text-muted-foreground">
        Notely wants to make {count} {count === 1 ? "change" : "changes"}. Untick anything you don&apos;t want.
      </p>
      <div className="mt-3 space-y-3">
        {grouped.map(([provider, proposals]) => (
          <div key={provider}>
            <p className="mb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">{providerLabel(provider)}</p>
            <ul className="space-y-1.5">
              {proposals.map((p) => {
                const id = `approve-${p.call_id}`;
                return (
                  <li key={p.call_id} className="flex items-start gap-2 rounded-md bg-card px-3 py-2">
                    <input
                      id={id}
                      type="checkbox"
                      className="mt-1 size-4 accent-[var(--ai)]"
                      checked={selected.has(p.call_id)}
                      disabled={disabled}
                      onChange={(e) =>
                        setSelected((s) => {
                          const next = new Set(s);
                          if (e.target.checked) next.add(p.call_id);
                          else next.delete(p.call_id);
                          return next;
                        })
                      }
                    />
                    <label htmlFor={id} className="min-w-0 flex-1 text-sm">
                      <span className="font-medium">+ {p.summary}</span>
                      <Badge variant={p.risk === "write" ? "secondary" : "destructive"} className="ml-2 align-middle font-normal">
                        {RISK_LABELS[p.risk]}
                      </Badge>
                      <ArgumentsPreview args={p.arguments} />
                    </label>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </div>
      {hasDestructive ? (
        <p className="mt-3 flex items-center gap-1.5 text-xs text-warning">
          <AlertTriangle className="size-3.5" aria-hidden /> Some of these actions leave Notely or can&apos;t be undone.
        </p>
      ) : null}
      <div className="mt-4 flex flex-wrap justify-end gap-2">
        <Button variant="outline" size="sm" disabled={disabled} onClick={() => onDecide([])}>
          Cancel
        </Button>
        <Button size="sm" disabled={disabled || selected.size === 0} onClick={() => onDecide([...selected])}>
          Approve {selected.size === count ? "all" : `${selected.size} of ${count}`}
        </Button>
      </div>
    </section>
  );
}

function ArgumentsPreview({ args }: { args: Record<string, unknown> }) {
  const entries = Object.entries(args).filter(([k, v]) => k !== "title" && v !== null && v !== undefined && v !== "" && v !== "none");
  if (!entries.length) return null;
  return (
    <dl className="mt-1 grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-xs text-muted-foreground">
      {entries.map(([k, v]) => (
        <React.Fragment key={k}>
          <dt className="capitalize">{k.replace(/_/g, " ")}</dt>
          <dd className="truncate">{typeof v === "string" ? v : JSON.stringify(v)}</dd>
        </React.Fragment>
      ))}
    </dl>
  );
}
