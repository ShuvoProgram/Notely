"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, ChevronRight, Copy, FlaskConical, Hand, Loader2, MoreHorizontal, Play, Trash2 } from "@/components/icons";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Switch } from "@/components/ui/switch";
import { messageFor } from "@/features/auth/components/auth-form-error";
import { cn } from "@/lib/utils";

import { automationsApi } from "../api";
import { RUN_STATUS, appName, relativeTime, scheduleText } from "../lib";
import type { Automation, Catalog } from "../types";
import { AppIcon } from "./app-icon";
import { RunStatusIcon } from "./run-panel";

export function AppChain({ apps, catalog }: { apps: string[]; catalog?: Catalog }) {
  if (!apps.length) return <span className="text-sm text-muted-foreground">No steps yet</span>;
  return (
    <span className="flex flex-wrap items-center gap-1.5 text-sm text-muted-foreground" aria-label={apps.map((a) => appName(catalog, a)).join(" then ")}>
      {apps.map((app, i) => (
        <React.Fragment key={app}>
          {i > 0 ? <ArrowRight className="size-3 opacity-60" aria-hidden /> : null}
          <span className="inline-flex items-center gap-1">
            <AppIcon appId={app} catalog={catalog} size="xs" />
            {appName(catalog, app)}
          </span>
        </React.Fragment>
      ))}
    </span>
  );
}

export function AutomationCard({ automation, catalog }: { automation: Automation; catalog?: Catalog }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [confirm, setConfirm] = React.useState(false);
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["automations"] });
  const href = `/app/automations/${automation.id}`;
  const onError = (e: unknown) => toast.error(messageFor(e));

  const toggle = useMutation({ mutationFn: (on: boolean) => automationsApi.setEnabled(automation.id, on), onSuccess: refresh, onError });
  const run = useMutation({
    mutationFn: () => automationsApi.run(automation.id),
    onSuccess: (r) => {
      toast.success("Running — follow along on its page.");
      void refresh();
      router.push(`${href}?run=${r.id}`);
    },
    onError,
  });
  const test = useMutation({ mutationFn: () => automationsApi.test(automation.id), onSuccess: (r) => router.push(`${href}?run=${r.id}`), onError });
  const duplicate = useMutation({ mutationFn: () => automationsApi.duplicate(automation.id), onSuccess: refresh, onError });
  const remove = useMutation({ mutationFn: () => automationsApi.remove(automation.id), onSuccess: refresh, onError });

  const last = automation.last_run;
  const status = last ? RUN_STATUS[last.status] ?? RUN_STATUS.completed : null;

  return (
    <article className="flex min-w-0 flex-col gap-3 glass lift rounded-2xl p-4" aria-label={automation.name}>
      <div className="flex items-start justify-between gap-3">
        <Link href={href} className="min-w-0 flex-1 rounded-md focus-visible:ring-2 focus-visible:ring-ring/40">
          {/* Long names wrap (two lines, then clipped with an ellipsis); unbroken words break too. */}
          <h3 className="line-clamp-2 font-semibold [overflow-wrap:anywhere]">{automation.name}</h3>
          <p className="text-sm text-muted-foreground">{scheduleText(automation, catalog)}</p>
        </Link>
        <label className="flex shrink-0 items-center gap-2 text-xs font-medium">
          <span className={automation.enabled ? "text-success" : "text-muted-foreground"}>{automation.enabled ? "ON" : "OFF"}</span>
          <Switch checked={automation.enabled} disabled={toggle.isPending} onCheckedChange={(on) => toggle.mutate(on)} aria-label={`${automation.name} on`} />
        </label>
      </div>

      <AppChain apps={automation.apps} catalog={catalog} />

      {automation.pending_approvals ? (
        <Link href={last ? `${href}?run=${last.id}` : href} className="flex min-h-11 items-center gap-2 rounded-xl border border-warning/40 bg-warning/5 px-3 py-2 text-sm text-warning">
          <Hand className="size-4" aria-hidden /> Waiting for your approval
          <ChevronRight className="ml-auto size-4" aria-hidden />
        </Link>
      ) : null}

      <div className="min-w-0 rounded-xl bg-muted/25 px-3 py-2 text-sm">
        {last ? (
          <>
            <p className={cn("flex flex-wrap items-center gap-x-1.5 font-medium", status?.tone)}>
              <RunStatusIcon status={last.status} />
              {last.status === "running" || last.status === "queued" ? "Running now" : `Last run ${relativeTime(last.started_at)}`}
              {last.status === "failed" ? <span className="font-normal">· {status?.label}</span> : null}
            </p>
            <p className="mt-0.5 line-clamp-3 text-muted-foreground [overflow-wrap:anywhere]">{last.status === "failed" ? last.error : last.summary}</p>
          </>
        ) : (
          <p className="text-muted-foreground">Hasn&apos;t run yet</p>
        )}
        {automation.enabled && automation.next_run_at ? (
          <p className="mt-1 text-xs text-muted-foreground">
            {automation.schedule_kind === "event" ? "Next check" : "Next run"} {relativeTime(automation.next_run_at)}
          </p>
        ) : null}
        {automation.trigger_status?.status === "needs_attention" && automation.trigger_status.last_error ? (
          <p className="mt-1 text-xs text-destructive [overflow-wrap:anywhere]">
            {automation.trigger_status.last_error}{" "}
            {automation.schedule_config.provider ? (
              <Link href={`/app/settings/connections/${automation.schedule_config.provider}`} className="font-medium underline underline-offset-2">
                Fix
              </Link>
            ) : null}
          </p>
        ) : null}
        {automation.consecutive_failures >= 2 ? (
          <p className="mt-1 text-xs text-destructive">Failed {automation.consecutive_failures} times in a row</p>
        ) : null}
      </div>

      <div className="mt-auto flex flex-wrap items-center gap-2">
        <Button asChild size="sm" variant="outline">
          <Link href={href}>Open</Link>
        </Button>
        <Button size="sm" variant="outline" disabled={run.isPending || automation.running} onClick={() => run.mutate()}>
          {run.isPending || automation.running ? <Loader2 className="animate-spin" /> : <Play />}
          {automation.running ? "Running…" : "Run now"}
        </Button>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button size="icon" variant="ghost" aria-label={`More for ${automation.name}`} className="ml-auto">
              <MoreHorizontal className="size-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onSelect={() => test.mutate()}>
              <FlaskConical /> Test safely
            </DropdownMenuItem>
            <DropdownMenuItem onSelect={() => duplicate.mutate()}>
              <Copy /> Duplicate
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem variant="destructive" onSelect={() => setTimeout(() => setConfirm(true), 0)}>
              <Trash2 /> Delete
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
      <ConfirmDialog
        open={confirm}
        onOpenChange={setConfirm}
        title={`Delete “${automation.name}”?`}
        description="It stops running and its history is deleted. This can't be undone."
        confirmLabel="Delete"
        pending={remove.isPending}
        onConfirm={() => remove.mutate()}
      />
    </article>
  );
}
