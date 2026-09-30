"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import Link from "next/link";
import * as React from "react";

import { History, Search } from "@/components/icons";
import { EmptyState } from "@/components/layout/empty-state";
import { PageHeader } from "@/components/layout/page-header";
import { Input } from "@/components/ui/input";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { adminApi, adminKeys, type AuditRow } from "@/features/admin/api";
import {
  type Column,
  DataTable,
  ErrorBlock,
  Facts,
  FilterBar,
  fmt,
  LoadingBlock,
  Muted,
  Pagination,
  Section,
  StatusPill,
  Time,
  useDebounced,
  useUrlState,
} from "@/features/admin/components/admin-ui";
import { FilterSelect } from "@/features/admin/components/users";

const PAGE_SIZE = 50;

const ACTION_LABEL: Record<string, string> = {
  "admin.login": "Admin signed in",
  "admin.access_denied": "Non-staff tried the admin area",
  "admin.permission_denied": "Action refused for role",
  "user.suspend": "Suspended account",
  "user.reactivate": "Reactivated account",
  "user.sessions_revoke": "Signed account out everywhere",
  "user.role_change": "Changed role",
  "settings.update": "Changed platform setting",
  "connector.enable": "Enabled connector",
  "connector.disable": "Disabled connector",
};

function describe(row: AuditRow): string {
  const m = row.metadata;
  if (row.action === "user.role_change") return `${m.from} → ${m.to}`;
  if (row.action === "settings.update") return `${JSON.stringify(m.from)} → ${JSON.stringify(m.to)}`;
  if (row.action === "user.suspend" && typeof m.reason === "string") return `“${m.reason}”`;
  if (row.action.endsWith("_denied") && typeof m.path === "string") return String(m.path);
  if (typeof m.sessions_revoked === "number") return `${m.sessions_revoked} session(s) ended`;
  return "";
}

const columns: Column<AuditRow>[] = [
  { key: "when", header: "When", cell: (r) => <Time value={r.created_at} /> },
  {
    key: "action",
    header: "Action",
    primary: true,
    cell: (r) => (
      <span className="flex min-w-0 flex-col">
        <span className="truncate font-medium">{ACTION_LABEL[r.action] ?? fmt.label(r.action)}</span>
        <span className="truncate text-xs text-muted-foreground">{describe(r) || r.action}</span>
      </span>
    ),
  },
  { key: "actor", header: "By", cell: (r) => <span className="truncate">{r.actor.email ?? <Muted>system</Muted>}</span> },
  {
    key: "resource",
    header: "Resource",
    cell: (r) =>
      r.resource_type === "user" && r.resource_id ? (
        <Link href={`/admin/users/${r.resource_id}`} className="truncate hover:underline">
          {r.resource_label ?? r.resource_id}
        </Link>
      ) : r.resource_type === "session" ? (
        <Muted>New session</Muted>
      ) : (
        <span className="truncate">{r.resource_label ?? r.resource_id ?? <Muted>—</Muted>}</span>
      ),
  },
  {
    key: "result",
    header: "Result",
    cell: (r) => <StatusPill tone={r.result === "success" ? "success" : r.result === "denied" ? "warning" : "danger"}>{fmt.label(r.result)}</StatusPill>,
  },
  { key: "ip", header: "IP", hideOnMobile: true, cell: (r) => <span className="tabular-nums text-muted-foreground">{r.ip ?? "—"}</span> },
];

export function AdminAuditLog() {
  const { values, set, page } = useUrlState(["q", "action", "result", "from", "to", "event"] as const);
  const [search, setSearch] = React.useState(values.q);
  const debounced = useDebounced(search);
  React.useEffect(() => {
    if (debounced !== values.q) set({ q: debounced });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only react to the typed value
  }, [debounced]);
  const params = { q: values.q, action: values.action, result: values.result, from: values.from, to: values.to, page, page_size: PAGE_SIZE };
  const q = useQuery({ queryKey: adminKeys.audit(params), queryFn: () => adminApi.audit(params), placeholderData: keepPreviousData });
  const actions = (q.data?.extra.actions as string[] | undefined) ?? [];
  const filtered = Boolean(values.q || values.action || values.result || values.from || values.to);
  const selected = q.data?.items.find((r) => r.id === values.event) ?? null;

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Admin"
        title="Audit log"
        description="Every administrative action and refused attempt, newest first. Entries can't be edited or deleted from here and never contain secrets."
      />
      <Section
        title={q.data ? `${fmt.n(q.data.total)} events` : "Events"}
        flush
        actions={
          <FilterBar
            active={filtered}
            onReset={() => {
              setSearch("");
              set({ q: null, action: null, result: null, from: null, to: null });
            }}
          >
            <div className="relative w-full sm:w-56">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
              <Input type="search" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Admin or resource" aria-label="Search audit log" className="pl-8" />
            </div>
            <FilterSelect
              label="Action"
              value={values.action}
              onChange={(v) => set({ action: v })}
              className="min-w-44"
              options={[["", "Any action"], ["user.", "Any account action"], ["admin.", "Sign-ins & refusals"], ...actions.map((a) => [a, ACTION_LABEL[a] ?? a] as [string, string])]}
            />
            <FilterSelect label="Result" value={values.result} onChange={(v) => set({ result: v })} options={[["", "Any result"], ["success", "Success"], ["denied", "Denied"], ["failed", "Failed"]]} />
            <Input type="date" value={values.from} max={values.to || undefined} onChange={(e) => set({ from: e.target.value })} className="h-8 w-36" aria-label="From date" />
            <Input type="date" value={values.to} min={values.from || undefined} onChange={(e) => set({ to: e.target.value })} className="h-8 w-36" aria-label="To date" />
          </FilterBar>
        }
      >
        {q.isPending ? (
          <LoadingBlock rows={10} className="px-4" />
        ) : q.error ? (
          <ErrorBlock error={q.error} onRetry={() => q.refetch()} />
        ) : (
          <div className={q.isPlaceholderData ? "opacity-60 transition-opacity" : undefined}>
            <DataTable
              caption="Admin audit log"
              rows={q.data.items}
              rowKey={(r) => r.id}
              rowHref={(r) => {
                const qs = new URLSearchParams(Object.entries({ ...values, event: r.id, page: page > 1 ? String(page) : "" }).filter(([, v]) => v));
                return `/admin/audit?${qs.toString()}`;
              }}
              columns={columns}
              empty={<EmptyState icon={History} title={filtered ? "No events match" : "No admin activity yet"} description="Sign-ins to the admin area and every change made here are recorded." />}
            />
            {q.data.total > PAGE_SIZE ? <Pagination page={page} pageSize={PAGE_SIZE} total={q.data.total} onPage={(p) => set({ page: p })} /> : null}
          </div>
        )}
      </Section>
      <Sheet open={Boolean(selected)} onOpenChange={(o) => !o && set({ event: null, page: page > 1 ? page : null })}>
        <SheetContent side="right" className="w-full overflow-y-auto data-[side=right]:sm:max-w-lg">
          <SheetHeader>
            <SheetTitle>{selected ? (ACTION_LABEL[selected.action] ?? fmt.label(selected.action)) : "Event"}</SheetTitle>
            <SheetDescription>Audit entry</SheetDescription>
          </SheetHeader>
          {selected ? (
            <div className="space-y-4 px-4 pb-6">
              <Facts
                items={[
                  ["When", <Time key="w" value={selected.created_at} />],
                  ["Action", <code key="a" className="text-xs">{selected.action}</code>],
                  ["Result", fmt.label(selected.result)],
                  ["Admin", `${selected.actor.email ?? "system"}${selected.actor.role ? ` (${selected.actor.role})` : ""}`],
                  ["Resource", `${selected.resource_type ?? "—"}${selected.resource_label ? ` · ${selected.resource_label}` : ""}`],
                  ["IP (masked)", selected.ip ?? "—"],
                  ["Request id", selected.request_id ? <code key="r" className="text-xs">{selected.request_id}</code> : "—"],
                ]}
              />
              <div>
                <h3 className="mb-1.5 text-xs text-muted-foreground">Details</h3>
                <pre className="glass overflow-x-auto rounded-xl p-3 text-xs">{JSON.stringify(selected.metadata, null, 2)}</pre>
              </div>
            </div>
          ) : null}
        </SheetContent>
      </Sheet>
    </div>
  );
}
