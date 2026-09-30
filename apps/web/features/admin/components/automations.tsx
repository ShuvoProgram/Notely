"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import Link from "next/link";

import { Activity, CheckCircle2, Clock, RotateCcw, Workflow, X, XCircle } from "@/components/icons";
import { EmptyState } from "@/components/layout/empty-state";
import { PageHeader } from "@/components/layout/page-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { adminApi, adminKeys, type ExecutionRow } from "@/features/admin/api";
import {
  type Column,
  DataTable,
  ErrorBlock,
  executionTone,
  Facts,
  FilterBar,
  fmt,
  LoadingBlock,
  Muted,
  Pagination,
  RangePicker,
  Section,
  StatCard,
  StatGrid,
  StatsSkeleton,
  StatusPill,
  Time,
  useRange,
  useUrlState,
} from "@/features/admin/components/admin-ui";
import { BarChart, ShareBars } from "@/features/admin/components/bar-chart";
import { FilterSelect } from "@/features/admin/components/users";

const PAGE_SIZE = 25;

export const ERROR_TYPES: [string, string][] = [
  ["", "Any error"],
  ["auth_failed", "Sign-in rejected"],
  ["expired", "Connection expired"],
  ["permission_denied", "Permission denied"],
  ["admin_approval_required", "Needs vendor admin approval"],
  ["rate_limited", "Rate limited"],
  ["unavailable", "Vendor unavailable"],
  ["invalid_request", "Invalid request"],
  ["not_found", "Not found"],
  ["api_disabled", "Vendor API disabled"],
  ["misconfigured", "Misconfigured"],
  ["declined", "Approval declined"],
  ["step_error", "Step error"],
  ["run_error", "Run error (no step)"],
];
const ERROR_LABEL = Object.fromEntries(ERROR_TYPES.filter(([k]) => k));

const STATUS_LABEL: Record<string, string> = {
  completed: "Completed",
  stopped: "Stopped by condition",
  failed: "Failed",
  running: "Running",
  queued: "Queued",
  waiting_for_approval: "Waiting for approval",
  skipped: "Skipped",
};

const columns: Column<ExecutionRow>[] = [
  {
    key: "automation",
    header: "Automation",
    primary: true,
    cell: (e) => (
      <span className="flex min-w-0 flex-col">
        <span className="truncate font-medium">{e.automation.name}</span>
        <span className="truncate text-xs text-muted-foreground">{e.owner?.email ?? "—"}</span>
      </span>
    ),
  },
  { key: "status", header: "Status", cell: (e) => <StatusPill tone={executionTone(e.status)}>{STATUS_LABEL[e.status] ?? fmt.label(e.status)}</StatusPill> },
  { key: "started", header: "Started", cell: (e) => <Time value={e.started_at} /> },
  { key: "duration", header: "Duration", numeric: true, cell: (e) => fmt.ms(e.duration_ms) },
  { key: "mode", header: "Trigger", cell: (e) => fmt.label(e.run_mode) },
  { key: "attempts", header: "Attempts", numeric: true, cell: (e) => (e.attempts > 1 ? <span className="text-warning">{e.attempts}</span> : e.attempts) },
  { key: "apps", header: "Apps", cell: (e) => (e.connectors.length ? e.connectors.map(fmt.label).join(", ") : <Muted>Notely only</Muted>) },
  {
    key: "error",
    header: "Failure",
    className: "max-w-72",
    cell: (e) =>
      e.error_type ? (
        <span className="flex min-w-0 flex-col">
          <span className="truncate text-xs font-medium">{ERROR_LABEL[e.error_type] ?? fmt.label(e.error_type)}</span>
          {e.error ? <span className="truncate text-xs text-muted-foreground" title={e.error}>{e.error}</span> : null}
        </span>
      ) : (
        <Muted>—</Muted>
      ),
  },
];

export function AdminAutomations() {
  const { days, setDays } = useRange(30);
  const { values, set, page } = useUrlState(["status", "user_id", "automation_id", "connector", "error_type", "run_mode", "from", "to", "run"] as const);
  const summary = useQuery({ queryKey: adminKeys.automationSummary(days), queryFn: () => adminApi.automationSummary(days) });
  const connectors = useQuery({ queryKey: adminKeys.connectors(days), queryFn: () => adminApi.connectors(days), staleTime: 5 * 60_000 });
  const params = {
    status: values.status,
    user_id: values.user_id,
    automation_id: values.automation_id,
    connector: values.connector,
    error_type: values.error_type,
    run_mode: values.run_mode,
    from: values.from,
    to: values.to,
    page,
    page_size: PAGE_SIZE,
  };
  const runs = useQuery({ queryKey: adminKeys.executions(params), queryFn: () => adminApi.executions(params), placeholderData: keepPreviousData });
  const filtered = Boolean(values.status || values.user_id || values.automation_id || values.connector || values.error_type || values.run_mode || values.from || values.to);

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Admin"
        title="Automations"
        description="Every automation run across all accounts: outcomes, timings, retries and why runs failed."
        actions={<RangePicker value={days} onChange={setDays} />}
      />

      {summary.isPending ? (
        <StatsSkeleton count={8} />
      ) : summary.error ? (
        <ErrorBlock error={summary.error} onRetry={() => summary.refetch()} />
      ) : (
        <>
          <StatGrid>
            <StatCard label="Automations" value={fmt.n(summary.data.automations.total)} icon={Workflow} hint={`${fmt.n(summary.data.automations.enabled)} switched on`} />
            <StatCard label={`Runs · last ${days}d`} value={fmt.n(summary.data.executions.total)} icon={Activity} hint={`${fmt.n(summary.data.executions.in_progress)} in progress`} />
            <StatCard
              label="Succeeded"
              value={fmt.n(summary.data.executions.succeeded)}
              icon={CheckCircle2}
              tone="success"
              hint={summary.data.executions.success_rate === null ? "No finished runs" : `${summary.data.executions.success_rate}% success rate`}
            />
            <StatCard
              label="Failed"
              value={fmt.n(summary.data.executions.failed)}
              icon={XCircle}
              tone={summary.data.executions.failed ? "danger" : undefined}
              hint={`${fmt.n(summary.data.automations.paused_after_failures)} paused after repeated failures`}
            />
            <StatCard
              label="Avg duration"
              value={fmt.ms(summary.data.executions.duration.avg_ms)}
              icon={Clock}
              hint={`p95 ${fmt.ms(summary.data.executions.duration.p95_ms)}${summary.data.executions.duration.sampled ? " · sampled" : ""}`}
            />
            <StatCard label="Retried runs" value={fmt.n(summary.data.executions.retried)} icon={RotateCcw} hint="Needed more than one attempt" />
            <StatCard label="Waiting for approval" value={fmt.n(summary.data.executions.waiting_for_approval)} hint="Paused on a person's decision" />
            <StatCard label="Event-triggered" value={fmt.n(summary.data.automations.event_triggered)} hint={`${fmt.n(summary.data.automations.created_in_window)} created in ${days}d`} />
          </StatGrid>

          <div className="grid gap-4 lg:grid-cols-5">
            <Section className="lg:col-span-3" title="Runs per day" description="Succeeded vs failed">
              <BarChart
                label="Automation runs per day, succeeded and failed"
                data={summary.data.series}
                series={[
                  { key: "succeeded", label: "Succeeded", color: "var(--success)" },
                  { key: "failed", label: "Failed", color: "var(--destructive)" },
                ]}
              />
            </Section>
            <Section className="lg:col-span-2" title="Why runs fail" description="Failed steps by cause and by app">
              {summary.data.failures_by_error.length ? (
                <div className="space-y-5">
                  <ShareBars
                    color="var(--destructive)"
                    items={summary.data.failures_by_error.slice(0, 6).map((r) => ({
                      key: r.error_type,
                      value: r.count,
                      label: (
                        <button type="button" className="hover:underline" onClick={() => set({ error_type: r.error_type, status: "failed" })}>
                          {ERROR_LABEL[r.error_type] ?? fmt.label(r.error_type)}
                        </button>
                      ),
                    }))}
                  />
                  <ShareBars
                    color="var(--warning)"
                    items={summary.data.failures_by_connector.slice(0, 6).map((r) => ({
                      key: r.connector,
                      value: r.count,
                      label: r.connector === "notely" ? "Notely / AI steps" : r.name,
                    }))}
                  />
                </div>
              ) : (
                <EmptyState icon={CheckCircle2} title="No failed steps" description={`Nothing failed in the last ${days} days.`} />
              )}
            </Section>
          </div>

          <Section title="Most frequently failing" description={`Automations with failed runs in the last ${days} days`} flush>
            <DataTable
              caption="Most frequently failing automations"
              rows={summary.data.top_failing}
              rowKey={(r) => r.id}
              columns={[
                {
                  key: "name",
                  header: "Automation",
                  primary: true,
                  cell: (r) => (
                    <button type="button" className="flex min-w-0 flex-col text-left hover:underline" onClick={() => set({ automation_id: r.id, status: null })}>
                      <span className="truncate font-medium">{r.name}</span>
                      <span className="truncate text-xs text-muted-foreground">{r.owner?.email ?? "—"}</span>
                    </button>
                  ),
                },
                { key: "failed", header: "Failed", numeric: true, cell: (r) => fmt.n(r.failed) },
                { key: "runs", header: "Runs", numeric: true, cell: (r) => fmt.n(r.runs) },
                { key: "rate", header: "Failure rate", numeric: true, cell: (r) => fmt.pct(r.failure_rate) },
                { key: "streak", header: "In a row", numeric: true, cell: (r) => fmt.n(r.consecutive_failures) },
                { key: "state", header: "State", cell: (r) => (r.enabled ? <StatusPill tone="success">On</StatusPill> : <StatusPill tone="neutral">Paused</StatusPill>) },
                { key: "last", header: "Last run", cell: (r) => <Time value={r.last_run_at} relative /> },
              ]}
              empty={<EmptyState icon={CheckCircle2} title="No failing automations" />}
            />
          </Section>
        </>
      )}

      <Section
        title="Executions"
        description={runs.data ? `${fmt.n(runs.data.total)} matching runs` : undefined}
        flush
        actions={
          <FilterBar active={filtered} onReset={() => set({ status: null, user_id: null, automation_id: null, connector: null, error_type: null, run_mode: null, from: null, to: null })}>
            <FilterSelect
              label="Status"
              value={values.status}
              onChange={(v) => set({ status: v })}
              options={[["", "Any status"], ["succeeded", "Succeeded"], ["failed", "Failed"], ["waiting_for_approval", "Waiting for approval"], ["running", "Running"], ["queued", "Queued"], ["skipped", "Skipped"]]}
            />
            <FilterSelect label="Error type" value={values.error_type} onChange={(v) => set({ error_type: v })} options={ERROR_TYPES} className="min-w-40" />
            <FilterSelect
              label="Connector"
              value={values.connector}
              onChange={(v) => set({ connector: v })}
              options={[["", "Any app"], ...((connectors.data ?? []).filter((c) => c.provider !== "mcp_server").map((c) => [c.provider, c.name]) as [string, string][])]}
            />
            <FilterSelect
              label="Trigger"
              value={values.run_mode}
              onChange={(v) => set({ run_mode: v })}
              options={[["", "Any trigger"], ["scheduled", "Scheduled"], ["event", "Event"], ["manual", "Run now"], ["test", "Test"]]}
            />
            <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
              From
              <Input type="date" value={values.from} max={values.to || undefined} onChange={(e) => set({ from: e.target.value })} className="h-8 w-36" aria-label="From date" />
            </label>
            <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
              To
              <Input type="date" value={values.to} min={values.from || undefined} onChange={(e) => set({ to: e.target.value })} className="h-8 w-36" aria-label="To date" />
            </label>
          </FilterBar>
        }
      >
        {values.user_id || values.automation_id ? (
          <div className="flex flex-wrap gap-2 px-4 pb-3">
            {values.user_id ? <Chip label="One user" onClear={() => set({ user_id: null })} /> : null}
            {values.automation_id ? <Chip label="One automation" onClear={() => set({ automation_id: null })} /> : null}
          </div>
        ) : null}
        {runs.isPending ? (
          <LoadingBlock rows={8} className="px-4" />
        ) : runs.error ? (
          <ErrorBlock error={runs.error} onRetry={() => runs.refetch()} />
        ) : (
          <div className={runs.isPlaceholderData ? "opacity-60 transition-opacity" : undefined}>
            <DataTable
              caption="Automation executions"
              rows={runs.data.items}
              rowKey={(e) => e.id}
              rowHref={(e) => {
                const qs = new URLSearchParams(Object.entries({ ...values, run: e.id, page: page > 1 ? String(page) : "" }).filter(([, v]) => v));
                return `/admin/automations?${qs.toString()}`;
              }}
              columns={columns}
              empty={
                <EmptyState
                  icon={Workflow}
                  title={filtered ? "No runs match these filters" : "No runs yet"}
                  description={filtered ? "Try widening the date range or clearing a filter." : "Runs appear here as soon as any automation starts."}
                />
              }
            />
            {runs.data.total > PAGE_SIZE ? <Pagination page={page} pageSize={PAGE_SIZE} total={runs.data.total} onPage={(p) => set({ page: p })} /> : null}
          </div>
        )}
      </Section>

      <ExecutionSheet id={values.run} onClose={() => set({ run: null, page: page > 1 ? page : null })} />
    </div>
  );
}

function Chip({ label, onClear }: { label: string; onClear: () => void }) {
  return (
    <span className="inline-flex h-7 items-center gap-1 rounded-full border border-glass-border bg-muted/40 pl-3 pr-1 text-xs">
      {label}
      <button type="button" onClick={onClear} className="grid size-5 place-items-center rounded-full hover:bg-muted" aria-label={`Clear ${label} filter`}>
        <X className="size-3" aria-hidden />
      </button>
    </span>
  );
}

/** Technical details of one run. Step inputs/outputs are people's data, so only field names show. */
function ExecutionSheet({ id, onClose }: { id: string; onClose: () => void }) {
  const q = useQuery({ queryKey: adminKeys.execution(id), queryFn: () => adminApi.execution(id), enabled: Boolean(id) });
  return (
    <Sheet open={Boolean(id)} onOpenChange={(o) => !o && onClose()}>
      <SheetContent side="right" className="w-full overflow-y-auto data-[side=right]:sm:max-w-xl">
        <SheetHeader>
          <SheetTitle>{q.data ? q.data.automation.name : "Execution"}</SheetTitle>
          <SheetDescription>Run details for troubleshooting. Inputs and outputs are not shown — only which fields a step used.</SheetDescription>
        </SheetHeader>
        <div className="space-y-5 px-4 pb-6">
          {q.isPending ? (
            <LoadingBlock rows={6} />
          ) : q.error ? (
            <ErrorBlock error={q.error} onRetry={() => q.refetch()} />
          ) : (
            <>
              <div className="flex flex-wrap items-center gap-2">
                <StatusPill tone={executionTone(q.data.status)}>{STATUS_LABEL[q.data.status] ?? fmt.label(q.data.status)}</StatusPill>
                <span className="text-xs text-muted-foreground">
                  {fmt.label(q.data.run_mode)} run · {q.data.attempts} attempt{q.data.attempts === 1 ? "" : "s"}
                </span>
              </div>
              {q.data.error ? (
                <p role="alert" className="rounded-xl border border-destructive/35 bg-destructive/10 px-3 py-2 text-sm">
                  {q.data.error}
                </p>
              ) : null}
              <Facts
                items={[
                  ["Owner", q.data.owner ? <Link key="o" className="hover:underline" href={`/admin/users/${q.data.owner.id}`}>{q.data.owner.email}</Link> : "—"],
                  ["Scheduled for", <Time key="oc" value={q.data.occurrence_at} />],
                  ["Started", <Time key="s" value={q.data.started_at} />],
                  ["Finished", <Time key="f" value={q.data.finished_at} />],
                  ["Duration", fmt.ms(q.data.duration_ms)],
                  ["Schedule", `${fmt.label(q.data.automation.schedule_kind)} · ${q.data.automation.timezone}`],
                  ["Automation state", q.data.automation.enabled ? "On" : "Paused"],
                  ["Failures in a row", fmt.n(q.data.automation.consecutive_failures)],
                  ["Trigger fields", q.data.context_keys.length ? q.data.context_keys.join(", ") : "—"],
                  ["Execution id", <code key="id" className="text-xs">{q.data.id}</code>],
                ]}
              />
              <div>
                <h3 className="mb-2 text-sm font-semibold">Steps</h3>
                {q.data.steps.length ? (
                  <ol className="space-y-2">
                    {q.data.steps.map((s) => (
                      <li key={s.step_id} className="glass rounded-xl px-3 py-2.5 text-sm">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <span className="min-w-0 font-medium">
                            {s.position + 1}. {s.name ?? s.kind}
                          </span>
                          <StatusPill tone={executionTone(s.status === "simulated" ? "completed" : s.status)}>{fmt.label(s.status)}</StatusPill>
                        </div>
                        <p className="mt-1 text-xs text-muted-foreground">
                          <code>{s.kind}</code> · {fmt.ms(s.duration_ms)} · {s.attempts} attempt{s.attempts === 1 ? "" : "s"}
                          {s.input_fields.length ? ` · inputs: ${s.input_fields.join(", ")}` : ""}
                        </p>
                        {s.error ? (
                          <p className="mt-1.5 text-xs text-destructive">
                            {s.error_type ? <strong>{ERROR_LABEL[s.error_type] ?? fmt.label(s.error_type)}: </strong> : null}
                            {s.error}
                          </p>
                        ) : null}
                      </li>
                    ))}
                  </ol>
                ) : (
                  <p className="text-sm text-muted-foreground">No steps ran.</p>
                )}
              </div>
              {q.data.approvals.length ? (
                <div>
                  <h3 className="mb-2 text-sm font-semibold">Approvals</h3>
                  <ul className="space-y-1 text-sm">
                    {q.data.approvals.map((a) => (
                      <li key={a.step_id}>
                        <code className="text-xs">{a.step_id}</code> · {fmt.label(a.status)} {a.decided_at ? <Time value={a.decided_at} relative /> : null}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
              <Button asChild variant="outline" size="sm">
                <Link href={`/admin/automations?automation_id=${q.data.automation.id}`} onClick={onClose}>
                  All runs of this automation
                </Link>
              </Button>
            </>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}
