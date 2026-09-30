"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import * as React from "react";
import { toast } from "sonner";

import { AlertTriangle, CheckCircle2, CircleSlash, KeyRound, Plug, Unplug } from "@/components/icons";
import { EmptyState } from "@/components/layout/empty-state";
import { PageHeader } from "@/components/layout/page-header";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Switch } from "@/components/ui/switch";
import { adminApi, adminKeys, type ConnectorHealth, type ConnectorRow } from "@/features/admin/api";
import {
  type Column,
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
  StatusPill,
  type Tone,
  Time,
  useCan,
  useRange,
  useUrlState,
} from "@/features/admin/components/admin-ui";
import { messageFor } from "@/features/auth/components/auth-form-error";

const HEALTH: Record<ConnectorHealth, { tone: Tone; label: string }> = {
  healthy: { tone: "success", label: "Healthy" },
  degraded: { tone: "warning", label: "Degraded" },
  failing: { tone: "danger", label: "Failing" },
  unused: { tone: "neutral", label: "No usage" },
  not_configured: { tone: "neutral", label: "Not configured" },
  disabled: { tone: "neutral", label: "Disabled" },
};

export function AdminConnectors() {
  const { days, setDays } = useRange(30);
  const { values, set } = useUrlState(["provider"] as const);
  const q = useQuery({ queryKey: adminKeys.connectors(days), queryFn: () => adminApi.connectors(days) });
  const canManage = useCan("platform:manage");
  const queryClient = useQueryClient();
  const [pending, setPending] = React.useState<ConnectorRow | null>(null);
  const toggle = useMutation({
    mutationFn: (c: ConnectorRow) => adminApi.setConnectorEnabled(c.provider, !c.enabled),
    onSuccess: (r) => {
      toast.success(r.enabled ? "Connector enabled" : "Connector disabled");
      setPending(null);
      void queryClient.invalidateQueries({ queryKey: ["admin", "connectors"] });
    },
    onError: (e) => toast.error(messageFor(e)),
  });

  const rows = q.data ?? [];
  const totals = rows.reduce(
    (t, c) => ({
      accounts: t.accounts + c.accounts,
      connected: t.connected + c.connected,
      reauth: t.reauth + c.auth_failing,
      failed: t.failed + c.failed_calls,
      calls: t.calls + c.calls,
      oauth: t.oauth + c.oauth_failures + c.auth_failures,
    }),
    { accounts: 0, connected: 0, reauth: 0, failed: 0, calls: 0, oauth: 0 },
  );

  const columns: Column<ConnectorRow>[] = [
    {
      key: "name",
      header: "Connector",
      primary: true,
      cell: (c) => (
        <span className="flex min-w-0 flex-col">
          <span className="truncate font-medium">{c.name}</span>
          <span className="truncate text-xs text-muted-foreground">{fmt.label(c.category)}</span>
        </span>
      ),
    },
    { key: "health", header: "Health", cell: (c) => <StatusPill tone={HEALTH[c.health].tone}>{HEALTH[c.health].label}</StatusPill> },
    { key: "accounts", header: "Accounts", numeric: true, cell: (c) => fmt.n(c.accounts) },
    { key: "connected", header: "Active", numeric: true, cell: (c) => fmt.n(c.connected) },
    { key: "expired", header: "Expired / attention", numeric: true, cell: (c) => (c.expired + c.needs_attention + c.errored ? <span className="text-warning">{fmt.n(c.expired + c.needs_attention + c.errored)}</span> : 0) },
    { key: "auth", header: "Auth failures", numeric: true, cell: (c) => (c.oauth_failures + c.auth_failures ? <span className="text-warning">{fmt.n(c.oauth_failures + c.auth_failures)}</span> : 0) },
    {
      key: "calls",
      header: "API failures",
      numeric: true,
      cell: (c) => (c.calls ? <span className={c.failed_calls ? "text-destructive" : undefined}>{`${fmt.n(c.failed_calls)} / ${fmt.n(c.calls)}`}</span> : <Muted>—</Muted>),
    },
    { key: "last", header: "Last failure", cell: (c) => (c.last_failure_at ? <Time value={c.last_failure_at} relative /> : <Muted>—</Muted>) },
    {
      key: "enabled",
      header: "Available",
      cell: (c) =>
        canManage ? (
          <Switch checked={c.enabled} onCheckedChange={() => setPending(c)} aria-label={`${c.enabled ? "Disable" : "Enable"} ${c.name}`} />
        ) : c.enabled ? (
          "Yes"
        ) : (
          "No"
        ),
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Admin"
        title="Connectors"
        description="Health of every integration, from Notely's own records of connections and calls. Credentials are never shown."
        actions={<RangePicker value={days} onChange={setDays} />}
      />
      {q.isPending ? (
        <>
          <StatsSkeleton />
          <LoadingBlock rows={8} />
        </>
      ) : q.error ? (
        <ErrorBlock error={q.error} onRetry={() => q.refetch()} />
      ) : (
        <>
          <StatGrid>
            <StatCard label="Connected accounts" value={fmt.n(totals.connected)} icon={Plug} hint={`${fmt.n(totals.accounts)} including broken ones`} />
            <StatCard label="Need reconnecting" value={fmt.n(totals.reauth)} icon={Unplug} tone={totals.reauth ? "warning" : undefined} />
            <StatCard label={`Auth failures · ${days}d`} value={fmt.n(totals.oauth)} icon={KeyRound} tone={totals.oauth ? "warning" : undefined} hint="OAuth + expired sign-ins" />
            <StatCard
              label={`API failures · ${days}d`}
              value={fmt.n(totals.failed)}
              icon={AlertTriangle}
              tone={totals.failed ? "danger" : undefined}
              hint={totals.calls ? `${fmt.n(totals.calls)} calls · ${((totals.failed / totals.calls) * 100).toFixed(1)}% failed` : "No calls"}
            />
          </StatGrid>
          <Section
            title="All connectors"
            description="Health is derived from the observed failure rate and sign-in problems — Notely has no status feed from the vendors themselves."
            flush
          >
            <DataTable
              caption="Connectors"
              rows={rows}
              rowKey={(c) => c.provider}
              rowHref={(c) => `/admin/connectors?${new URLSearchParams({ provider: c.provider, ...(days !== 30 ? { days: String(days) } : {}) })}`}
              columns={columns}
              empty={<EmptyState icon={Plug} title="No connectors registered" />}
            />
          </Section>
        </>
      )}
      <ConfirmDialog
        open={pending !== null}
        onOpenChange={(o) => !o && setPending(null)}
        title={pending?.enabled ? `Disable ${pending?.name}?` : `Enable ${pending?.name ?? ""}?`}
        description={
          pending?.enabled
            ? "People can no longer connect it, and it disappears from the connections list. Existing connections keep working until they're disconnected."
            : "It becomes available to connect again for everyone."
        }
        confirmLabel={pending?.enabled ? "Disable" : "Enable"}
        destructive={Boolean(pending?.enabled)}
        pending={toggle.isPending}
        onConfirm={() => pending && toggle.mutate(pending)}
      />
      <ConnectorSheet provider={values.provider} days={days} onClose={() => set({ provider: null })} />
    </div>
  );
}

function ConnectorSheet({ provider, days, onClose }: { provider: string; days: number; onClose: () => void }) {
  const q = useQuery({ queryKey: adminKeys.connector(provider, days), queryFn: () => adminApi.connector(provider, days), enabled: Boolean(provider) });
  return (
    <Sheet open={Boolean(provider)} onOpenChange={(o) => !o && onClose()}>
      <SheetContent side="right" className="w-full overflow-y-auto data-[side=right]:sm:max-w-xl">
        <SheetHeader>
          <SheetTitle>{q.data?.name ?? "Connector"}</SheetTitle>
          <SheetDescription>Problems from the last {days} days. Error messages are sanitized; tokens never leave the vault.</SheetDescription>
        </SheetHeader>
        <div className="space-y-6 px-4 pb-6">
          {q.isPending ? (
            <LoadingBlock rows={6} />
          ) : q.error ? (
            <ErrorBlock error={q.error} onRetry={() => q.refetch()} />
          ) : (
            <>
              <section>
                <h3 className="mb-2 text-sm font-semibold">Connections with problems</h3>
                {q.data.connections_with_problems.length ? (
                  <ul className="divide-y divide-glass-border text-sm">
                    {q.data.connections_with_problems.map((c) => (
                      <li key={c.id} className="py-2">
                        <div className="flex items-center justify-between gap-2">
                          {c.user ? (
                            <Link href={`/admin/users/${c.user.id}`} className="truncate font-medium hover:underline" onClick={onClose}>
                              {c.user.email}
                            </Link>
                          ) : (
                            <span>—</span>
                          )}
                          <StatusPill tone={c.status === "error" ? "danger" : "warning"}>{fmt.label(c.status)}</StatusPill>
                        </div>
                        <p className="mt-0.5 text-xs text-muted-foreground">
                          {c.error_code ? `${fmt.label(c.error_code)} · ` : ""}
                          {c.error ?? "No details"} · checked <Time value={c.last_checked_at} relative />
                        </p>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="flex items-center gap-2 text-sm text-muted-foreground">
                    <CheckCircle2 className="size-4 text-success" aria-hidden /> No broken connections.
                  </p>
                )}
              </section>
              <section>
                <h3 className="mb-2 text-sm font-semibold">Sign-in failures</h3>
                {q.data.auth_events.length ? (
                  <ul className="divide-y divide-glass-border text-sm">
                    {q.data.auth_events.map((e) => (
                      <li key={e.id} className="flex items-center gap-2 py-2">
                        <KeyRound className="size-4 shrink-0 text-warning" aria-hidden />
                        <span className="min-w-0 flex-1 truncate">
                          {e.message ?? fmt.label(e.kind)}
                          {e.user ? <span className="text-muted-foreground"> · {e.user.email}</span> : null}
                        </span>
                        <span className="shrink-0 text-xs text-muted-foreground">
                          <Time value={e.occurred_at} relative />
                        </span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-sm text-muted-foreground">None recorded.</p>
                )}
              </section>
              <section>
                <h3 className="mb-2 text-sm font-semibold">Failed API calls</h3>
                {q.data.recent_failures.length ? (
                  <ul className="divide-y divide-glass-border text-sm">
                    {q.data.recent_failures.map((f) => (
                      <li key={f.id} className="flex items-center gap-2 py-2">
                        <CircleSlash className="size-4 shrink-0 text-destructive" aria-hidden />
                        <span className="min-w-0 flex-1 truncate">
                          {f.tool ?? f.action}
                          {f.user ? <span className="text-muted-foreground"> · {f.user.email}</span> : null}
                        </span>
                        <span className="shrink-0 text-xs text-muted-foreground">
                          <Time value={f.created_at} relative />
                        </span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-sm text-muted-foreground">None recorded.</p>
                )}
              </section>
            </>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}
