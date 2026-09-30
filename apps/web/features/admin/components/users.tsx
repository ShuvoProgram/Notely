"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import * as React from "react";

import { Search, ShieldCheck, Users } from "@/components/icons";
import { EmptyState } from "@/components/layout/empty-state";
import { PageHeader } from "@/components/layout/page-header";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { adminApi, adminKeys, type AdminUserRow } from "@/features/admin/api";
import {
  AccountStatus,
  type Column,
  DataTable,
  ErrorBlock,
  FilterBar,
  fmt,
  LoadingBlock,
  Muted,
  Pagination,
  RoleBadge,
  Section,
  Time,
  useDebounced,
  useUrlState,
} from "@/features/admin/components/admin-ui";

const PAGE_SIZE = 25;
const ALL = "all";

export function FilterSelect({
  label,
  value,
  onChange,
  options,
  className,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: [string, string][];
  className?: string;
}) {
  return (
    <Select value={value || ALL} onValueChange={(v) => onChange(v === ALL ? "" : v)}>
      <SelectTrigger aria-label={label} className={className ?? "min-w-36"}>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {options.map(([v, l]) => (
          <SelectItem key={v || ALL} value={v || ALL}>
            {l}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

const columns: Column<AdminUserRow>[] = [
  {
    key: "user",
    header: "User",
    primary: true,
    cell: (u) => (
      <span className="flex min-w-0 flex-col">
        <span className="flex items-center gap-2 truncate font-medium">
          {u.display_name}
          {u.role !== "user" ? <RoleBadge role={u.role} /> : null}
        </span>
        <span className="truncate text-xs text-muted-foreground">{u.email}</span>
      </span>
    ),
  },
  { key: "status", header: "Status", cell: (u) => <AccountStatus active={u.is_active} /> },
  { key: "created", header: "Registered", cell: (u) => <Time value={u.created_at} /> },
  { key: "active", header: "Last active", cell: (u) => (u.last_active_at ? <Time value={u.last_active_at} relative /> : <Muted>Never</Muted>) },
  { key: "notes", header: "Notes", numeric: true, cell: (u) => fmt.n(u.counts.notes) },
  { key: "automations", header: "Automations", numeric: true, cell: (u) => fmt.n(u.counts.automations) },
  { key: "connections", header: "Connected apps", numeric: true, cell: (u) => fmt.n(u.counts.connections) },
  { key: "ai", header: "AI · 30d", numeric: true, cell: (u) => fmt.n(u.counts.ai_requests_30d) },
  {
    key: "security",
    header: "2FA",
    hideOnMobile: true,
    cell: (u) => (u.two_factor_enabled ? <ShieldCheck className="size-4 text-success" aria-label="Two-factor on" /> : <Muted>Off</Muted>),
  },
];

export function AdminUsers() {
  const { values, set, page } = useUrlState(["q", "status", "role", "activity", "sort"] as const);
  const [search, setSearch] = React.useState(values.q);
  const debounced = useDebounced(search);
  React.useEffect(() => {
    if (debounced !== values.q) set({ q: debounced });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only react to the typed value
  }, [debounced]);

  const params = { q: values.q, status: values.status, role: values.role, activity: values.activity, sort: values.sort || "created_desc", page, page_size: PAGE_SIZE };
  const q = useQuery({ queryKey: adminKeys.users(params), queryFn: () => adminApi.users(params), placeholderData: keepPreviousData });
  const filtered = Boolean(values.q || values.status || values.role || values.activity);

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Admin" title="Users" description="Search accounts, check their status and usage, and open one to take action." />
      <Section
        title={q.data ? `${fmt.n(q.data.total)} ${q.data.total === 1 ? "account" : "accounts"}` : "Accounts"}
        flush
        actions={
          <FilterBar
            active={filtered}
            onReset={() => {
              setSearch("");
              set({ q: null, status: null, role: null, activity: null });
            }}
          >
            <div className="relative w-full sm:w-64">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
              <Input
                type="search"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search name or email"
                aria-label="Search users"
                className="pl-8"
                maxLength={200}
              />
            </div>
            <FilterSelect
              label="Status"
              value={values.status}
              onChange={(v) => set({ status: v })}
              options={[["", "Any status"], ["active", "Active"], ["suspended", "Suspended"]]}
            />
            <FilterSelect
              label="Role"
              value={values.role}
              onChange={(v) => set({ role: v })}
              options={[["", "Any role"], ["user", "Members"], ["staff", "All staff"], ["admin", "Admins"], ["support", "Support"], ["viewer", "Read-only admins"]]}
            />
            <FilterSelect
              label="Activity"
              value={values.activity}
              onChange={(v) => set({ activity: v })}
              options={[["", "Any activity"], ["active_7d", "Active in 7 days"], ["active_30d", "Active in 30 days"], ["dormant", "Inactive 30+ days"], ["new_7d", "Joined in 7 days"]]}
            />
            <FilterSelect
              label="Sort"
              value={values.sort === "created_desc" ? "" : values.sort}
              onChange={(v) => set({ sort: v })}
              options={[["", "Newest first"], ["created_asc", "Oldest first"], ["active_desc", "Recently active"], ["email", "Email A–Z"]]}
            />
          </FilterBar>
        }
      >
        {q.isPending ? (
          <LoadingBlock rows={8} className="px-4" />
        ) : q.error ? (
          <ErrorBlock error={q.error} onRetry={() => q.refetch()} />
        ) : (
          <div className={q.isPlaceholderData ? "opacity-60 transition-opacity" : undefined} aria-busy={q.isFetching}>
            <DataTable
              caption="Users"
              rows={q.data.items}
              columns={columns}
              rowKey={(u) => u.id}
              rowHref={(u) => `/admin/users/${u.id}`}
              empty={
                <EmptyState
                  icon={Users}
                  title={filtered ? "No accounts match" : "No accounts yet"}
                  description={filtered ? "Try a different search or clear the filters." : "People appear here as soon as they sign up."}
                />
              }
            />
            {q.data.total > PAGE_SIZE ? <Pagination page={page} pageSize={PAGE_SIZE} total={q.data.total} onPage={(p) => set({ page: p })} /> : null}
          </div>
        )}
      </Section>
    </div>
  );
}
