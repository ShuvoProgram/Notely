"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  CircleDashed,
  CircleSlash,
  FlaskConical,
  Hand,
  History,
  Loader2,
  PauseCircle,
  RotateCcw,
  ShieldCheck,
  ShieldX,
} from "@/components/icons";
import Link from "next/link";
import * as React from "react";
import { toast } from "sonner";

import { EmptyState } from "@/components/layout/empty-state";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { messageFor } from "@/features/auth/components/auth-form-error";
import { cn } from "@/lib/utils";

import { TERMINAL_RUN, automationsApi } from "../api";
import { RUN_STATUS, relativeTime } from "../lib";
import type { Run, RunDetail, RunStep } from "../types";
import { DataView } from "./data-view";

const MODE: Record<string, string> = { test: "Test run", scheduled: "Scheduled", manual: "Run now" };

export function RunStatusIcon({ status, className }: { status: string; className?: string }) {
  const cls = cn("size-4 shrink-0", className);
  if (status === "queued" || status === "running") return <Loader2 className={cn(cls, "animate-spin text-info")} aria-label="Running" />;
  if (status === "completed" || status === "stopped" || status === "simulated") return <CheckCircle2 className={cn(cls, "text-success")} aria-label="Finished" />;
  if (status === "failed") return <AlertTriangle className={cn(cls, "text-destructive")} aria-label="Failed" />;
  if (status === "waiting_for_approval") return <PauseCircle className={cn(cls, "text-warning")} aria-label="Waiting for you" />;
  if (status === "skipped") return <CircleSlash className={cn(cls, "text-muted-foreground")} aria-label="Skipped" />;
  return <CircleDashed className={cn(cls, "text-muted-foreground")} aria-label="Not started" />;
}

function fixLabel(path: string): string {
  if (path.startsWith("https://console.")) return "Enable the API";
  if (path.startsWith("/app/settings/ai")) return "Set up AI";
  if (path.startsWith("/app/settings/connections")) return "Reconnect";
  return "Fix";
}

function StepRow({ step, run, automationId, onRetried }: { step: RunStep; run: RunDetail; automationId: string; onRetried: () => void }) {
  const retry = useMutation({
    mutationFn: () => automationsApi.retryStep(automationId, run.id, step.step_id),
    onSuccess: onRetried,
    onError: (e) => toast.error(messageFor(e)),
  });
  const fix = typeof step.details.fix_path === "string" ? step.details.fix_path : null;
  const hasData = step.output != null || Object.keys(step.input ?? {}).length > 0;
  return (
    <li className="relative flex gap-3 pb-4 last:pb-0">
      <span className="absolute left-2 top-6 bottom-0 w-px bg-glass-border last:hidden" aria-hidden />
      <RunStatusIcon status={step.status} className="mt-0.5" />
      <div className="min-w-0 flex-1 space-y-1">
        <p className="text-sm font-medium">{step.name ?? step.step_id}</p>
        <p className={cn("text-sm", step.status === "failed" ? "text-destructive" : "text-muted-foreground")}>
          {step.status === "failed" ? step.error : step.summary}
          {step.attempts > 1 && step.status !== "failed" ? <span className="text-xs"> · took {step.attempts} tries</span> : null}
        </p>
        <div className="flex flex-wrap gap-2">
          {step.status === "failed" && run.status === "failed" ? (
            <Button size="sm" variant="outline" disabled={retry.isPending} onClick={() => retry.mutate()}>
              {retry.isPending ? <Loader2 className="animate-spin" /> : <RotateCcw />} Retry step
            </Button>
          ) : null}
          {fix ? (
            <Button asChild size="sm" variant="outline">
              {fix.startsWith("https://") ? (
                <a href={fix} target="_blank" rel="noreferrer">
                  {fixLabel(fix)}
                </a>
              ) : (
                <Link href={fix}>{fixLabel(fix)}</Link>
              )}
            </Button>
          ) : null}
        </div>
        {hasData && step.status !== "skipped" ? (
          <details className="text-sm">
            <summary className="cursor-pointer text-xs text-muted-foreground">View details</summary>
            <div className="mt-2 grid max-h-80 gap-3 overflow-auto rounded-lg border border-glass-border bg-field p-3">
              {Object.keys(step.input ?? {}).length ? (
                <section>
                  <h4 className="mb-1 text-xs font-semibold uppercase tracking-wider text-muted-foreground">Used</h4>
                  <DataView value={step.input} />
                </section>
              ) : null}
              {step.output != null ? (
                <section>
                  <h4 className="mb-1 text-xs font-semibold uppercase tracking-wider text-muted-foreground">Result</h4>
                  <DataView value={step.output} />
                </section>
              ) : null}
            </div>
          </details>
        ) : null}
      </div>
    </li>
  );
}

function Headline({ run }: { run: RunDetail }) {
  const done = run.steps.filter((s) => s.status === "completed" || s.status === "simulated").length;
  const failed = run.steps.find((s) => s.status === "failed");
  if (run.status === "failed" && failed) {
    return (
      <div className="rounded-xl border border-destructive/30 bg-destructive/5 p-3 text-sm">
        <p className="font-medium text-destructive">⚠ {failed.name ?? "A step"} couldn&apos;t finish</p>
        <p className="text-muted-foreground">
          {done ? `${done} step${done > 1 ? "s" : ""} before it completed successfully. ` : ""}Fix the problem below, then retry the step.
        </p>
      </div>
    );
  }
  const status = RUN_STATUS[run.status] ?? RUN_STATUS.completed;
  return (
    <div className="rounded-xl border border-glass-border bg-muted/20 p-3 text-sm">
      <p className={cn("font-medium", status.tone)}>
        {run.run_mode === "test" && TERMINAL_RUN.has(run.status) && run.status !== "waiting_for_approval" ? "Test finished" : status.label}
      </p>
      {run.summary ? <p className="text-muted-foreground">{run.summary}</p> : null}
      {run.run_mode === "test" ? <p className="mt-1 text-xs text-muted-foreground">Nothing was changed: steps that would change data were only simulated.</p> : null}
    </div>
  );
}

export function RunDetailView({ automationId, runId, onBack, onFinished }: { automationId: string; runId: string; onBack?: () => void; onFinished?: (run: RunDetail) => void }) {
  const queryClient = useQueryClient();
  const detail = useQuery({
    queryKey: ["automations", automationId, "runs", runId],
    queryFn: () => automationsApi.runDetail(automationId, runId),
    refetchInterval: (q) => (q.state.data && !TERMINAL_RUN.has(q.state.data.status) ? 1500 : false),
  });
  const notified = React.useRef<string | null>(null);
  React.useEffect(() => {
    const run = detail.data;
    if (run && TERMINAL_RUN.has(run.status) && notified.current !== `${run.id}:${run.status}`) {
      notified.current = `${run.id}:${run.status}`;
      onFinished?.(run);
      void queryClient.invalidateQueries({ queryKey: ["automations"], exact: false });
    }
  }, [detail.data, onFinished, queryClient]);
  const decide = useMutation({
    mutationFn: ({ id, approved }: { id: string; approved: boolean }) => automationsApi.decide(automationId, id, approved),
    onSuccess: () => detail.refetch(),
    onError: (e) => toast.error(messageFor(e)),
  });
  const run = detail.data;
  return (
    <div className="space-y-4">
      {onBack ? (
        <button type="button" onClick={onBack} className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
          <ArrowLeft className="size-4" aria-hidden /> All runs
        </button>
      ) : null}
      {!run ? (
        <Skeleton className="h-40 rounded-2xl" />
      ) : (
        <>
          <div className="flex items-center justify-between gap-2 text-xs text-muted-foreground">
            <span>{MODE[run.run_mode] ?? run.run_mode}</span>
            <span>{relativeTime(run.started_at)}</span>
          </div>
          <Headline run={run} />
          {run.approvals
            .filter((a) => a.status === "pending")
            .map((approval) => (
              <section key={approval.id} className="space-y-3 rounded-xl border border-warning/40 bg-warning/5 p-3" aria-label="Approval needed">
                <p className="flex items-center gap-2 text-sm font-medium">
                  <Hand className="size-4 text-warning" aria-hidden /> {approval.proposal.app}: {approval.proposal.summary}
                </p>
                {approval.proposal.inputs ? (
                  <div className="rounded-lg bg-field p-2">
                    <DataView value={approval.proposal.inputs} />
                  </div>
                ) : null}
                <div className="flex gap-2">
                  <Button size="sm" disabled={decide.isPending} onClick={() => decide.mutate({ id: approval.id, approved: true })}>
                    <ShieldCheck /> Approve and continue
                  </Button>
                  <Button size="sm" variant="outline" disabled={decide.isPending} onClick={() => decide.mutate({ id: approval.id, approved: false })}>
                    <ShieldX /> Don&apos;t do it
                  </Button>
                </div>
              </section>
            ))}
          <ol aria-label="Steps in this run">
            {run.steps.map((step) => (
              <StepRow key={step.step_id} step={step} run={run} automationId={automationId} onRetried={() => detail.refetch()} />
            ))}
          </ol>
        </>
      )}
    </div>
  );
}

export function RunHistory({
  automationId,
  selected,
  onSelect,
  onFinished,
}: {
  automationId: string;
  selected: string | null;
  onSelect: (id: string | null) => void;
  onFinished?: (run: RunDetail) => void;
}) {
  const runs = useQuery({
    queryKey: ["automations", automationId, "runs"],
    queryFn: () => automationsApi.runs(automationId),
    refetchInterval: (q) => (q.state.data?.some((r: Run) => !TERMINAL_RUN.has(r.status)) ? 2000 : false),
  });
  if (selected) return <RunDetailView automationId={automationId} runId={selected} onBack={() => onSelect(null)} onFinished={onFinished} />;
  if (runs.isPending) return <Skeleton className="h-40 rounded-2xl" />;
  if (!runs.data?.length) {
    return <EmptyState icon={History} title="No runs yet" description="Test it or run it now to see exactly what happens at each step." />;
  }
  return (
    <ul className="divide-y divide-glass-border rounded-2xl border border-glass-border" aria-label="Runs">
      {runs.data.map((run) => (
        <li key={run.id}>
          <button type="button" onClick={() => onSelect(run.id)} className="flex w-full items-start gap-3 p-3 text-left hover:bg-muted/30">
            <RunStatusIcon status={run.status} className="mt-0.5" />
            <span className="min-w-0 flex-1">
              <span className="flex items-center justify-between gap-2 text-xs text-muted-foreground">
                <span className="inline-flex items-center gap-1">
                  {run.run_mode === "test" ? <FlaskConical className="size-3" aria-hidden /> : null}
                  {MODE[run.run_mode] ?? run.run_mode} · {RUN_STATUS[run.status]?.label ?? run.status}
                </span>
                <span>{relativeTime(run.started_at)}</span>
              </span>
              <span className="mt-0.5 line-clamp-2 block text-sm">{run.status === "failed" ? run.error : run.summary ?? "—"}</span>
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}
