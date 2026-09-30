"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import * as React from "react";

import { ChevronDown, History, RotateCcw, Sparkles, Workflow } from "@/components/icons";
import { EmptyState } from "@/components/layout/empty-state";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { messageFor } from "@/features/auth/components/auth-form-error";
import { type Batch, type BatchKind, historyApi, historyKeys } from "@/features/history/api";
import { ChangeList, RevertDialog } from "@/features/history/components/revert-dialog";
import { cn } from "@/lib/utils";

export function RevertBadge({ batch }: { batch: Batch }) {
  const r = batch.revert;
  if (!r) return null;
  const tone =
    r.status === "reverted"
      ? "border-success/35 bg-success/10 text-success"
      : r.status === "running"
        ? "border-ai/30 bg-ai-soft text-ai"
        : "border-warning/40 bg-warning/10 text-warning";
  const label = { reverted: "Reverted", running: "Reverting…", partial: "Partly reverted", failed: "Revert failed" }[r.status];
  return <span className={cn("inline-flex h-5 items-center rounded-full border px-2 text-[11px] font-semibold uppercase tracking-wide", tone)}>{label}</span>;
}

/** Everything the assistant and automations changed, newest first, each run revertible. */
export function ChangeHistory() {
  const list = useQuery({ queryKey: historyKeys.list, queryFn: historyApi.list });
  const [target, setTarget] = React.useState<{ kind: BatchKind; id: string } | null>(null);
  const [open, setOpen] = React.useState<string | null>(null);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Changes by AI &amp; automations</CardTitle>
        <CardDescription>Each run lists what it changed. Revert a run to undo everything it did that can be safely undone.</CardDescription>
      </CardHeader>
      <CardContent>
        {list.isPending ? (
          <div className="space-y-2">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-16 w-full rounded-xl" />
            ))}
          </div>
        ) : list.error ? (
          <p role="alert" className="text-sm text-destructive">
            {messageFor(list.error)}
          </p>
        ) : list.data.length === 0 ? (
          <EmptyState icon={History} title="No changes yet" description="When the assistant or an automation creates or changes something, it shows up here and can be reverted." className="py-8" />
        ) : (
          <ul className="space-y-2">
            {list.data.map((b) => {
              const key = `${b.kind}:${b.batch_id}`;
              const Icon = b.kind === "ai_run" ? Sparkles : Workflow;
              const expanded = open === key;
              return (
                <li key={key} className="glass rounded-xl">
                  <div className="flex flex-col gap-2 px-3 py-2.5 sm:flex-row sm:items-center">
                    <div className="flex min-w-0 flex-1 gap-2.5">
                      <Icon className="mt-0.5 size-4 shrink-0 text-ai" aria-hidden />
                      <div className="min-w-0">
                        <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm font-medium">
                          {b.href ? (
                            <Link href={b.href} className="truncate hover:underline">
                              {b.title}
                            </Link>
                          ) : (
                            <span className="truncate">{b.title}</span>
                          )}
                          <RevertBadge batch={b} />
                        </p>
                        <p className="text-xs text-muted-foreground">
                          {b.source} · {new Date(b.created_at).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}
                          {" · "}
                          {b.summary.map((s) => s.text).join(", ")}
                        </p>
                      </div>
                    </div>
                    <div className="flex shrink-0 items-center gap-1 self-end sm:self-auto">
                      <Button variant="ghost" size="sm" aria-expanded={expanded} onClick={() => setOpen(expanded ? null : key)}>
                        Details <ChevronDown className={cn("transition-transform", expanded && "rotate-180")} aria-hidden />
                      </Button>
                      {b.revert?.status === "reverted" ? null : (
                        <Button variant="outline" size="sm" onClick={() => setTarget({ kind: b.kind, id: b.batch_id })} disabled={b.revert?.status === "running"}>
                          <RotateCcw aria-hidden /> {b.revert ? "Review" : "Revert"}
                        </Button>
                      )}
                    </div>
                  </div>
                  {expanded ? (
                    <div className="border-t border-glass-border px-3 pb-2 pt-1 text-sm">
                      <ChangeList changes={b.changes} />
                    </div>
                  ) : null}
                </li>
              );
            })}
          </ul>
        )}
      </CardContent>
      {target ? <RevertDialog kind={target.kind} batchId={target.id} open onOpenChange={(o) => !o && setTarget(null)} /> : null}
    </Card>
  );
}

/** Compact "this run changed N things · Revert" strip for an automation run's detail view. */
export function RunChanges({ kind, batchId }: { kind: BatchKind; batchId: string }) {
  const q = useQuery({
    queryKey: historyKeys.batch(kind, batchId),
    queryFn: () => historyApi.preview(kind, batchId),
    retry: false,
  });
  const [open, setOpen] = React.useState(false);
  if (!q.data) return null; // 404: this run changed nothing
  const b = q.data;
  return (
    <section aria-label="Changes made by this run" className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-glass-border bg-muted/30 px-3 py-2 text-sm">
      <p className="min-w-0">
        <span className="font-medium">Changed:</span> {b.summary.map((s) => s.text).join(", ")} <RevertBadge batch={b} />
      </p>
      {b.revert?.status === "reverted" ? null : (
        <Button size="sm" variant="outline" onClick={() => setOpen(true)}>
          <RotateCcw aria-hidden /> {b.revert ? "Review revert" : "Revert this run"}
        </Button>
      )}
      <RevertDialog kind={kind} batchId={batchId} open={open} onOpenChange={setOpen} />
    </section>
  );
}
