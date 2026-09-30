"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

import { Activity, Clock, InfoIcon, MessageSquareText, Sparkles, Users, WandSparkles, XCircle, Zap } from "@/components/icons";
import { EmptyState } from "@/components/layout/empty-state";
import { PageHeader } from "@/components/layout/page-header";
import { adminApi, adminKeys, type AIUsage } from "@/features/admin/api";
import {
  DataTable,
  ErrorBlock,
  fmt,
  LoadingBlock,
  Muted,
  RangePicker,
  Section,
  StatCard,
  StatGrid,
  StatsSkeleton,
  useRange,
} from "@/features/admin/components/admin-ui";
import { BarChart, ShareBars } from "@/features/admin/components/bar-chart";

export function AdminAIUsage() {
  const { days, setDays } = useRange(30);
  const q = useQuery({ queryKey: adminKeys.ai(days), queryFn: () => adminApi.ai(days) });
  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Admin"
        title="AI usage"
        description="Assistant requests, models, tokens, latency and tool calls, from the run records Notely keeps."
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
        <Body data={q.data} days={days} />
      )}
    </div>
  );
}

function Body({ data, days }: { data: AIUsage; days: number }) {
  const { requests, tokens, latency, tools } = data;
  return (
    <>
      <StatGrid>
        <StatCard label={`AI requests · ${days}d`} value={fmt.n(requests.total)} icon={Sparkles} hint={`${fmt.n(requests.conversations)} new conversations`} />
        <StatCard
          label="Failed requests"
          value={fmt.n(requests.failed)}
          icon={XCircle}
          tone={requests.failed ? "danger" : undefined}
          hint={requests.failure_rate === null ? "No requests" : `${requests.failure_rate}% of requests`}
        />
        <StatCard label="People using AI" value={fmt.n(requests.active_users)} icon={Users} hint={`${fmt.n(data.own_model_users)} bring their own model`} />
        <StatCard
          label="Avg response time"
          value={fmt.ms(latency.avg_ms)}
          icon={Clock}
          hint={latency.count ? `p50 ${fmt.ms(latency.p50_ms)} · p95 ${fmt.ms(latency.p95_ms)}` : "No completed runs"}
        />
        <StatCard label="Input tokens" value={fmt.compact(tokens.input)} icon={Activity} hint={tokens.runs_without_usage ? `${fmt.n(tokens.runs_without_usage)} runs reported no usage` : "All runs reported usage"} />
        <StatCard label="Output tokens" value={fmt.compact(tokens.output)} icon={Activity} />
        <StatCard label="Tool calls" value={fmt.n(tools.total)} icon={Zap} hint={`${fmt.n(tools.by_status.failed ?? 0)} failed`} />
        <StatCard
          label="AI workflow drafts"
          value={fmt.n(data.automation_drafts.succeeded)}
          icon={WandSparkles}
          hint={data.automation_drafts.failed ? `${fmt.n(data.automation_drafts.failed)} failed` : "Automations drafted from plain language"}
        />
      </StatGrid>

      <p className="flex items-start gap-2 text-xs text-muted-foreground">
        <InfoIcon className="mt-0.5 size-3.5 shrink-0" aria-hidden />
        {data.cost.tracked
          ? `Estimated cost ${data.cost.estimated_usd?.toFixed(2)} USD across ${fmt.n(data.cost.runs_with_cost)} runs — an estimate from the gateway's price table, not your provider's invoice.`
          : "Cost isn't tracked: runs don't record a price, so no cost is shown. Check your model provider's billing for actual spend."}{" "}
        Response time counts completed requests that didn&apos;t pause for approval.
      </p>

      <div className="grid gap-4 lg:grid-cols-2">
        <Section title="Requests per day" description="Succeeded vs failed">
          <BarChart
            label="AI requests per day"
            data={data.series.map((d) => ({ date: d.date, ok: d.requests - d.failed, failed: d.failed }))}
            series={[
              { key: "ok", label: "Succeeded", color: "var(--success)" },
              { key: "failed", label: "Failed", color: "var(--destructive)" },
            ]}
          />
        </Section>
        <Section title="Tokens per day" description="Input + output tokens reported by the model">
          <BarChart
            label="Tokens per day"
            data={data.series.map((d) => ({ date: d.date, tokens: d.input_tokens + d.output_tokens }))}
            series={[{ key: "tokens", label: "Tokens", color: "var(--ai)" }]}
            format={(v) => fmt.compact(Math.round(v))}
          />
        </Section>
      </div>

      <Section title="By model" description="Provider and model recorded on each run" flush>
        <DataTable
          caption="AI requests by model"
          rows={data.by_model}
          rowKey={(r) => `${r.provider}/${r.model}`}
          columns={[
            { key: "model", header: "Model", primary: true, cell: (r) => <span className="font-medium">{r.model}</span> },
            { key: "provider", header: "Provider", cell: (r) => fmt.label(r.provider) },
            { key: "requests", header: "Requests", numeric: true, cell: (r) => fmt.n(r.requests) },
            { key: "failed", header: "Failed", numeric: true, cell: (r) => (r.failed ? <span className="text-destructive">{fmt.n(r.failed)}</span> : 0) },
            { key: "in", header: "Input tokens", numeric: true, cell: (r) => fmt.compact(r.input_tokens) },
            { key: "out", header: "Output tokens", numeric: true, cell: (r) => fmt.compact(r.output_tokens) },
          ]}
          empty={<EmptyState icon={Sparkles} title="No AI requests in this period" />}
        />
      </Section>

      <div className="grid gap-4 lg:grid-cols-2">
        <Section title="Most used tools">
          {tools.top.length ? (
            <ShareBars
              items={tools.top.map((t) => ({
                key: `${t.provider}/${t.tool}`,
                value: t.calls,
                label: (
                  <>
                    <span className="font-medium">{t.tool}</span>
                    <span className="text-muted-foreground">
                      {" "}
                      · {t.provider_name}
                      {t.failed ? ` · ${t.failed} failed` : ""}
                    </span>
                  </>
                ),
              }))}
            />
          ) : (
            <EmptyState icon={Zap} title="No tool calls" />
          )}
        </Section>
        <Section title="Heaviest users" flush>
          <DataTable
            caption="Top AI users"
            rows={data.top_users}
            rowKey={(r) => r.user?.id ?? "unknown"}
            rowHref={(r) => (r.user ? `/admin/users/${r.user.id}` : "/admin/users")}
            columns={[
              {
                key: "user",
                header: "User",
                primary: true,
                cell: (r) => <span className="truncate">{r.user?.email ?? <Muted>Deleted user</Muted>}</span>,
              },
              { key: "requests", header: "Requests", numeric: true, cell: (r) => fmt.n(r.requests) },
              { key: "tokens", header: "Tokens", numeric: true, cell: (r) => fmt.compact(r.input_tokens + r.output_tokens) },
            ]}
            empty={<EmptyState icon={MessageSquareText} title="Nobody used the assistant yet" />}
          />
        </Section>
      </div>
      <p className="text-xs text-muted-foreground">
        Per-person limits and the AI on/off switch live in <Link href="/admin/settings" className="underline">settings</Link>.
      </p>
    </>
  );
}
