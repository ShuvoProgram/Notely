"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  CheckSquare,
  CircleSlash,
  KeyRound,
  NotebookPen,
  Plug,
  Zap,
  Sparkles,
  UserPlus,
  Users,
  Workflow,
  XCircle,
} from "@/components/icons";
import { EmptyState } from "@/components/layout/empty-state";
import { PageHeader } from "@/components/layout/page-header";
import { adminApi, adminKeys, type Overview } from "@/features/admin/api";
import {
  AccountStatus,
  ErrorBlock,
  fmt,
  LoadingBlock,
  RangePicker,
  RoleBadge,
  Section,
  StatCard,
  StatGrid,
  StatsSkeleton,
  StatusPill,
  Time,
  useRange,
} from "@/features/admin/components/admin-ui";
import { BarChart } from "@/features/admin/components/bar-chart";

export function AdminOverview() {
  const { days, setDays } = useRange(30);
  const q = useQuery({ queryKey: adminKeys.overview(days), queryFn: () => adminApi.overview(days), refetchInterval: 60_000 });

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Admin"
        title="Overview"
        description="Live numbers from Notely's database. Nothing here is estimated."
        actions={<RangePicker value={days} onChange={setDays} />}
      />
      {q.isPending ? (
        <>
          <StatsSkeleton count={8} />
          <LoadingBlock rows={6} />
        </>
      ) : q.error ? (
        <ErrorBlock error={q.error} onRetry={() => q.refetch()} />
      ) : (
        <OverviewBody data={q.data} days={days} />
      )}
    </div>
  );
}

function delta(now: number, before: number): string {
  if (!before) return now ? "new this period" : "no change";
  const pct = Math.round(((now - before) / before) * 100);
  return `${pct >= 0 ? "+" : ""}${pct}% vs previous period`;
}

function OverviewBody({ data, days }: { data: Overview; days: number }) {
  const { users, usage, health } = data;
  const successRate = usage.automation_runs_succeeded + usage.automation_runs_failed
    ? Math.round((usage.automation_runs_succeeded / (usage.automation_runs_succeeded + usage.automation_runs_failed)) * 100)
    : null;
  const problems =
    health.api_errors + health.job_failures + health.automation_runs_failed + health.ai_requests_failed + health.connections_needing_reauth;
  return (
    <>
      <section aria-labelledby="h-users" className="space-y-3">
        <h2 id="h-users" className="text-sm font-semibold text-muted-foreground">
          Users
        </h2>
        <StatGrid>
          <StatCard label="Total users" value={fmt.n(users.total)} icon={Users} hint={`${fmt.n(users.staff)} staff`} href="/admin/users" />
          <StatCard label={`New · last ${days}d`} value={fmt.n(users.new)} icon={UserPlus} hint={delta(users.new, users.new_previous)} href="/admin/users?activity=new_7d" />
          <StatCard
            label="Active · 7 days"
            value={fmt.n(users.active.week)}
            icon={Activity}
            hint={`${fmt.n(users.active.day)} today · ${fmt.n(users.active.month)} in 30d`}
            href="/admin/users?activity=active_7d"
          />
          <StatCard
            label="Suspended"
            value={fmt.n(users.suspended)}
            icon={CircleSlash}
            tone={users.suspended ? "warning" : undefined}
            href="/admin/users?status=suspended"
          />
        </StatGrid>
      </section>

      <div className="grid gap-4 lg:grid-cols-5 lg:items-start">
        <Section className="lg:col-span-3" title="User growth" description={`Sign-ups per day, last ${days} days · ${fmt.n(users.total)} accounts in total`}>
          <BarChart label="Sign-ups per day" data={users.growth} series={[{ key: "signups", label: "Sign-ups", color: "var(--ai)" }]} />
        </Section>
        <Section
          className="lg:col-span-2"
          title="Recently registered"
          flush
          actions={
            <Link href="/admin/users" className="text-xs font-medium text-ai hover:underline">
              All users
            </Link>
          }
        >
          {users.recent.length ? (
            <ul className="divide-y divide-glass-border">
              {users.recent.map((u) => (
                <li key={u.id}>
                  <Link href={`/admin/users/${u.id}`} className="flex items-center gap-3 px-4 py-2.5 outline-none transition-colors hover:bg-muted/30 focus-visible:bg-muted/40">
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium">{u.display_name}</p>
                      <p className="truncate text-xs text-muted-foreground">{u.email}</p>
                    </div>
                    <div className="flex shrink-0 flex-col items-end gap-1">
                      <span className="text-xs text-muted-foreground">
                        <Time value={u.created_at} relative />
                      </span>
                      {u.role !== "user" ? <RoleBadge role={u.role} /> : !u.is_active ? <AccountStatus active={false} /> : null}
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState icon={Users} title="No users yet" />
          )}
        </Section>
      </div>

      <section aria-labelledby="h-usage" className="space-y-3">
        <h2 id="h-usage" className="text-sm font-semibold text-muted-foreground">
          Product usage · last {days} days
        </h2>
        <StatGrid>
          <StatCard label="Notes created" value={fmt.n(usage.notes_created)} icon={NotebookPen} hint={`${fmt.n(usage.notes_total)} notes in total`} />
          <StatCard label="Tasks created" value={fmt.n(usage.tasks_created)} icon={CheckSquare} hint={`${fmt.n(usage.tasks_completed)} completed`} />
          <StatCard label="AI requests" value={fmt.n(usage.ai_requests)} icon={Sparkles} hint={`${fmt.n(usage.ai_conversations)} new conversations`} href="/admin/ai" />
          <StatCard label="Connector calls" value={fmt.n(usage.connector_calls)} icon={Plug} hint={`${fmt.n(usage.active_connections)} live connections`} href="/admin/connectors" />
          <StatCard label="Automations" value={fmt.n(usage.automations_total)} icon={Workflow} hint={`${fmt.n(usage.automations_enabled)} on · ${fmt.n(usage.automations_created)} new`} href="/admin/automations" />
          <StatCard label="Automation runs" value={fmt.n(usage.automation_runs)} icon={Activity} hint={successRate === null ? "No finished runs" : `${successRate}% succeeded`} href="/admin/automations" />
          <StatCard label="Runs succeeded" value={fmt.n(usage.automation_runs_succeeded)} icon={CheckCircle2} tone="success" href="/admin/automations?status=succeeded" />
          <StatCard
            label="Runs failed"
            value={fmt.n(usage.automation_runs_failed)}
            icon={XCircle}
            tone={usage.automation_runs_failed ? "danger" : undefined}
            href="/admin/automations?status=failed"
          />
        </StatGrid>
        <Section title="Activity per day" description="Notes, AI requests and automation runs">
          <div className="grid gap-6 md:grid-cols-3">
            <div>
              <p className="mb-2 text-xs font-medium text-muted-foreground">Notes created</p>
              <BarChart label="Notes created per day" height={110} data={data.usage_series} series={[{ key: "notes", label: "Notes", color: "var(--ai)" }]} />
            </div>
            <div>
              <p className="mb-2 text-xs font-medium text-muted-foreground">AI requests</p>
              <BarChart label="AI requests per day" height={110} data={data.usage_series} series={[{ key: "ai_requests", label: "AI requests", color: "var(--ai)" }]} />
            </div>
            <div>
              <p className="mb-2 text-xs font-medium text-muted-foreground">Automation runs</p>
              <BarChart label="Automation runs per day" height={110} data={data.usage_series} series={[{ key: "automation_runs", label: "Runs", color: "var(--ai)" }]} />
            </div>
          </div>
        </Section>
      </section>

      <section aria-labelledby="h-health" className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <h2 id="h-health" className="text-sm font-semibold text-muted-foreground">
            System health · last {days} days
          </h2>
          {problems ? <StatusPill tone="warning">Needs a look</StatusPill> : <StatusPill tone="success">All clear</StatusPill>}
        </div>
        <StatGrid className="xl:grid-cols-6">
          <StatCard label="API errors (5xx)" value={fmt.n(health.api_errors)} icon={AlertTriangle} tone={health.api_errors ? "danger" : undefined} />
          <StatCard label="Background job failures" value={fmt.n(health.job_failures)} icon={Zap} tone={health.job_failures ? "danger" : undefined} />
          <StatCard label="Failed automation runs" value={fmt.n(health.automation_runs_failed)} icon={Workflow} tone={health.automation_runs_failed ? "danger" : undefined} href="/admin/automations?status=failed" />
          <StatCard label="Failed AI requests" value={fmt.n(health.ai_requests_failed)} icon={Sparkles} tone={health.ai_requests_failed ? "danger" : undefined} href="/admin/ai" />
          <StatCard
            label="Connector auth failures"
            value={fmt.n(health.connector_auth_failures + health.oauth_failures)}
            icon={KeyRound}
            tone={health.connector_auth_failures + health.oauth_failures ? "warning" : undefined}
            hint={`${fmt.n(health.connections_needing_reauth)} connections need reconnecting`}
            href="/admin/connectors"
          />
          <div className="glass flex min-w-0 flex-col justify-center gap-1.5 rounded-2xl px-4 py-3.5">
            <p className="text-xs font-medium text-muted-foreground">Services</p>
            <StatusPill tone={health.services.database ? "success" : "danger"}>Database</StatusPill>
            <StatusPill tone={health.services.redis ? "success" : "warning"}>{health.services.redis ? "Redis" : "Redis unreachable"}</StatusPill>
          </div>
        </StatGrid>
        <Section title="Recent incidents" description="Errors the platform recorded: API 5xx, job failures, OAuth and connector sign-in failures" flush>
          {health.recent_incidents.length ? (
            <ul className="divide-y divide-glass-border">
              {health.recent_incidents.map((e) => (
                <li key={e.id} className="flex flex-col gap-1 px-4 py-2.5 text-sm sm:flex-row sm:items-center sm:gap-3">
                  <StatusPill tone={e.kind === "connector_auth_failed" || e.kind === "oauth_failed" ? "warning" : "danger"}>{fmt.label(e.kind)}</StatusPill>
                  <span className="min-w-0 flex-1 truncate">
                    <span className="font-medium">{e.source ?? "—"}</span>
                    {e.message ? <span className="text-muted-foreground"> · {e.message}</span> : null}
                  </span>
                  {e.user ? (
                    <Link href={`/admin/users/${e.user.id}`} className="truncate text-xs text-muted-foreground hover:underline">
                      {e.user.email}
                    </Link>
                  ) : null}
                  <span className="text-xs text-muted-foreground">
                    <Time value={e.occurred_at} relative />
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState icon={CheckCircle2} title="No incidents recorded" description="Unhandled API errors, failed background jobs and connector sign-in failures will appear here." />
          )}
        </Section>
      </section>
    </>
  );
}
