"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as React from "react";
import { toast } from "sonner";

import { AlertTriangle, CheckCircle2, CircleSlash, Loader2, RotateCcw, XCircle } from "@/components/icons";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { messageFor } from "@/features/auth/components/auth-form-error";
import { type Batch, type BatchKind, type Change, historyApi, historyKeys } from "@/features/history/api";
import { ApiError } from "@/lib/api/client";
import { playSfx } from "@/lib/sfx/player";

const STATUS: Record<Change["status"], { text: string; icon: typeof CheckCircle2; cls: string }> = {
  applied: { text: "Not reverted", icon: CircleSlash, cls: "text-muted-foreground" },
  reverted: { text: "Reverted", icon: CheckCircle2, cls: "text-success" },
  revert_skipped: { text: "Left as is", icon: CircleSlash, cls: "text-warning" },
  revert_failed: { text: "Couldn't revert", icon: XCircle, cls: "text-destructive" },
};

/**
 * Revert one AI run or automation run. Opens on a dry-run preview from the server ("This will
 * revert: 3 tasks created, 1 Google Calendar event created"), lists what will be left alone and
 * what can't be undone, and only reverts after an explicit confirm. Afterwards it shows exactly
 * what happened to each change; a partial failure can be retried (only the failures run again).
 */
export function RevertDialog({
  kind,
  batchId,
  open,
  onOpenChange,
}: {
  kind: BatchKind;
  batchId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const queryClient = useQueryClient();
  const preview = useQuery({
    queryKey: historyKeys.batch(kind, batchId),
    queryFn: () => historyApi.preview(kind, batchId),
    enabled: open,
    staleTime: 0,
  });
  const [result, setResult] = React.useState<Batch | null>(null);

  const revert = useMutation({
    mutationFn: (retry: boolean) => historyApi.revert(kind, batchId, retry),
    onSuccess: (batch) => {
      setResult(batch);
      void queryClient.invalidateQueries({ queryKey: historyKeys.all });
      // Reverted tasks, notes and events: every list reads fresh.
      void queryClient.invalidateQueries({ queryKey: ["tasks"] });
      void queryClient.invalidateQueries({ queryKey: ["notes"] });
      void queryClient.invalidateQueries({ queryKey: ["automations"] });
      const s = batch.revert?.summary ?? {};
      if (batch.revert?.status === "reverted") {
        playSfx("restore");
        toast.success(s.skipped || s.not_reversible ? "Reverted what could be reverted" : "Run reverted");
      } else {
        playSfx("error");
        toast.error("Some changes couldn't be reverted", { description: "Details are in the dialog. You can retry." });
      }
    },
    onError: (e) => {
      playSfx("error");
      if (e instanceof ApiError && e.code === "ALREADY_REVERTED") {
        toast.message("Already reverted");
        void queryClient.invalidateQueries({ queryKey: historyKeys.all });
      } else toast.error(messageFor(e));
    },
  });

  const close = (o: boolean) => {
    if (!o) setResult(null);
    onOpenChange(o);
  };

  const data = result ?? preview.data ?? null;
  const state = data?.revert ?? null;
  const p = preview.data?.preview;
  const willCount = p?.will_revert.reduce((n, l) => n + l.count, 0) ?? 0;
  const showResult = Boolean(result) || (state && state.status !== "running");
  const retryable = state?.status === "partial" || state?.status === "failed";

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{showResult ? (state?.status === "reverted" ? "Reverted" : "Revert results") : "Revert this run?"}</DialogTitle>
          <DialogDescription>{data ? `${data.source} · ${data.title}` : "Loading…"}</DialogDescription>
        </DialogHeader>

        {preview.isPending && !result ? (
          <div className="space-y-2" aria-busy>
            <Skeleton className="h-5 w-2/3" />
            <Skeleton className="h-5 w-1/2" />
            <Skeleton className="h-5 w-3/5" />
          </div>
        ) : preview.error && !result ? (
          <p role="alert" className="text-sm text-destructive">
            {messageFor(preview.error)}
          </p>
        ) : showResult && data ? (
          <ResultView batch={data} />
        ) : p ? (
          <div className="space-y-4 text-sm">
            {p.will_revert.length ? (
              <section>
                <h3 className="font-medium">This will revert:</h3>
                <ul className="mt-1.5 space-y-1">
                  {p.will_revert.map((l) => (
                    <li key={l.key} className="flex items-center gap-2">
                      <RotateCcw className="size-3.5 shrink-0 text-ai" aria-hidden /> {l.text}
                    </li>
                  ))}
                </ul>
              </section>
            ) : (
              <p className="text-muted-foreground">Nothing left that can be reverted automatically.</p>
            )}
            {p.will_leave.length ? (
              <section>
                <h3 className="font-medium">Will be left as is:</h3>
                <ul className="mt-1.5 space-y-1.5">
                  {p.will_leave.map((l, i) => (
                    <li key={i} className="flex gap-2">
                      <CircleSlash className="mt-0.5 size-3.5 shrink-0 text-warning" aria-hidden />
                      <span>
                        {l.label} <span className="block text-xs text-muted-foreground">{l.reason}</span>
                      </span>
                    </li>
                  ))}
                </ul>
              </section>
            ) : null}
            {p.cannot_revert.length ? (
              <section className="rounded-xl border border-warning/40 bg-warning/10 p-3">
                <h3 className="flex items-center gap-1.5 font-medium">
                  <AlertTriangle className="size-4 text-warning" aria-hidden /> Can&apos;t be reverted
                </h3>
                <ul className="mt-1.5 space-y-1.5">
                  {p.cannot_revert.map((l, i) => (
                    <li key={i}>
                      {l.app}: {l.label}
                      <span className="block text-xs text-muted-foreground">{l.reason}</span>
                    </li>
                  ))}
                </ul>
              </section>
            ) : null}
            <p className="text-xs text-muted-foreground">The history entry is kept and marked Reverted. Notes go to the trash; nothing else is permanently deleted from Notely.</p>
          </div>
        ) : null}

        <DialogFooter className="mt-2">
          {showResult ? (
            <>
              {retryable ? (
                <Button variant="outline" onClick={() => revert.mutate(true)} disabled={revert.isPending}>
                  {revert.isPending ? <Loader2 className="animate-spin" aria-hidden /> : <RotateCcw aria-hidden />} Retry failed changes
                </Button>
              ) : null}
              <Button key="done" variant="default" onClick={() => close(false)}>
                Done
              </Button>
            </>
          ) : (
            <>
              <Button key="cancel" variant="outline" onClick={() => close(false)} disabled={revert.isPending}>
                Cancel
              </Button>
              <Button key="revert" variant="destructive" onClick={() => revert.mutate(false)} disabled={revert.isPending || !willCount}>
                {revert.isPending ? <Loader2 className="animate-spin" aria-hidden /> : <RotateCcw aria-hidden />}
                Revert {willCount} change{willCount === 1 ? "" : "s"}
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ResultView({ batch }: { batch: Batch }) {
  const s = batch.revert?.summary ?? {};
  return (
    <div className="space-y-3 text-sm">
      <p className="text-muted-foreground">
        {[
          s.reverted ? `${s.reverted} reverted` : null,
          s.skipped ? `${s.skipped} left as is` : null,
          s.failed ? `${s.failed} failed` : null,
          s.not_reversible ? `${s.not_reversible} can't be reverted` : null,
        ]
          .filter(Boolean)
          .join(" · ")}
        {batch.revert?.requested_by ? ` · by ${batch.revert.requested_by}` : ""}
        {batch.revert?.finished_at ? ` · ${new Date(batch.revert.finished_at).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })}` : ""}
      </p>
      <ChangeList changes={batch.changes} />
    </div>
  );
}

export function ChangeList({ changes }: { changes: Change[] }) {
  return (
    <ul className="divide-y divide-glass-border">
      {changes.map((c) => {
        const st = c.reversible ? STATUS[c.status] : { text: "Can't be reverted", icon: AlertTriangle, cls: "text-warning" };
        const Icon = st.icon;
        return (
          <li key={c.id} className="flex gap-2.5 py-2">
            <Icon className={`mt-0.5 size-4 shrink-0 ${st.cls}`} aria-hidden />
            <div className="min-w-0 flex-1">
              <p className="break-words">
                {c.provider !== "notely" ? <span className="text-muted-foreground">{c.app}: </span> : null}
                {c.label}
              </p>
              <p className="text-xs text-muted-foreground">
                {st.text}
                {c.revert_note ? ` — ${c.revert_note}` : !c.reversible && c.irreversible_reason ? ` — ${c.irreversible_reason}` : ""}
                {c.revert_attempts > 1 ? ` · ${c.revert_attempts} attempts` : ""}
              </p>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
