"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import * as React from "react";
import { toast } from "sonner";

import {
  AlertTriangle,
  ArrowLeft,
  CircleSlash,
  History,
  KeyRound,
  Laptop,
  LogOut,
  Plug,
  RotateCcw,
  ShieldCheck,
  Sparkles,
  Workflow,
} from "@/components/icons";
import { EmptyState } from "@/components/layout/empty-state";
import { PageHeader } from "@/components/layout/page-header";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { adminApi, adminKeys, type AdminUserDetail } from "@/features/admin/api";
import {
  AccountStatus,
  ErrorBlock,
  executionTone,
  Facts,
  fmt,
  LoadingBlock,
  Muted,
  RoleBadge,
  Section,
  StatCard,
  StatGrid,
  StatsSkeleton,
  StatusPill,
  Time,
  useAdminMe,
  useCan,
} from "@/features/admin/components/admin-ui";
import { messageFor } from "@/features/auth/components/auth-form-error";
import type { PlatformRole } from "@/lib/api/types";

const ROLE_LABEL: Record<PlatformRole, string> = { user: "Member", viewer: "Read-only admin", support: "Support", admin: "Admin" };
const RANK: Record<PlatformRole, number> = { user: 0, viewer: 1, support: 2, admin: 3 };

export function AdminUserDetailView({ id }: { id: string }) {
  const q = useQuery({ queryKey: adminKeys.user(id), queryFn: () => adminApi.user(id) });
  return (
    <div className="space-y-6">
      <Button asChild variant="ghost" size="sm" className="-ml-2">
        <Link href="/admin/users">
          <ArrowLeft aria-hidden /> Users
        </Link>
      </Button>
      {q.isPending ? (
        <>
          <LoadingBlock rows={2} />
          <StatsSkeleton />
          <LoadingBlock rows={6} />
        </>
      ) : q.error ? (
        <ErrorBlock error={q.error} onRetry={() => q.refetch()} />
      ) : (
        <Detail data={q.data} />
      )}
    </div>
  );
}

function Detail({ data }: { data: AdminUserDetail }) {
  const p = data.profile;
  return (
    <>
      <PageHeader
        title={
          <span className="flex flex-wrap items-center gap-2">
            {p.display_name} <AccountStatus active={p.is_active} /> {p.role !== "user" ? <RoleBadge role={p.role} /> : null}
          </span>
        }
        description={p.email}
        actions={<Actions data={data} />}
      />

      {!p.is_active ? (
        <div role="status" className="flex items-start gap-3 rounded-2xl border border-destructive/35 bg-destructive/10 px-4 py-3 text-sm">
          <CircleSlash className="mt-0.5 size-4 shrink-0 text-destructive" aria-hidden />
          <div>
            <p className="font-medium">Suspended {p.suspended_at ? <Time value={p.suspended_at} relative /> : null}</p>
            {p.suspension_reason ? <p className="mt-0.5 text-muted-foreground">Reason: {p.suspension_reason}</p> : null}
          </div>
        </div>
      ) : null}

      <StatGrid>
        <StatCard label="Notes" value={fmt.n(data.usage.notes)} hint={`${fmt.n(data.usage.notes_created_30d)} created in 30 days`} />
        <StatCard label="Tasks" value={fmt.n(data.usage.tasks_open + data.usage.tasks_done)} hint={`${fmt.n(data.usage.tasks_open)} open · ${fmt.n(data.usage.tasks_done)} done`} />
        <StatCard label="AI requests · 30d" value={fmt.n(data.ai.requests_30d)} icon={Sparkles} hint={`${fmt.n(data.ai.requests)} all time · ${fmt.n(data.ai.failed)} failed`} />
        <StatCard
          label="Automations"
          value={fmt.n(data.automations.total)}
          icon={Workflow}
          hint={`${fmt.n(data.automations.runs_30d)} runs · ${fmt.n(data.automations.failed_30d)} failed (30d)`}
          tone={data.automations.failed_30d ? "warning" : undefined}
        />
      </StatGrid>

      <div className="grid gap-4 lg:grid-cols-2">
        <Section title="Account">
          <Facts
            items={[
              ["Registered", <Time key="r" value={p.created_at} />],
              ["Last active", p.last_active_at ? <Time key="a" value={p.last_active_at} relative /> : <Muted key="a">Never</Muted>],
              ["Last sign-in", p.last_login_at ? <Time key="l" value={p.last_login_at} /> : <Muted key="l">Never</Muted>],
              ["Email", p.email_verified ? "Verified" : "Not verified"],
              ["Sign-in methods", p.sign_in_methods.length ? p.sign_in_methods.map(fmt.label).join(", ") : "—"],
              [
                "Two-factor",
                p.two_factor_enabled ? (
                  <StatusPill key="2" tone="success" icon={ShieldCheck}>
                    On
                  </StatusPill>
                ) : (
                  <Muted key="2">Off</Muted>
                ),
              ],
              ["Workspace", p.workspace ? `${p.workspace.name} (${p.workspace.kind})` : "—"],
              ["Account id", <code key="id" className="text-xs">{p.id}</code>],
            ]}
          />
        </Section>
        <Section title="AI usage">
          <Facts
            items={[
              ["Conversations", fmt.n(data.ai.conversations)],
              ["Requests (all time)", fmt.n(data.ai.requests)],
              ["Failed requests", fmt.n(data.ai.failed)],
              ["Tokens in / out", `${fmt.compact(data.ai.input_tokens)} / ${fmt.compact(data.ai.output_tokens)}`],
              ["Last request", data.ai.last_request_at ? <Time key="lr" value={data.ai.last_request_at} relative /> : <Muted key="lr">Never</Muted>],
              [
                "Own model",
                data.ai.own_model ? `${data.ai.own_model.provider} · ${data.ai.own_model.model}${data.ai.own_model.enabled ? "" : " (off)"}` : "Workspace default",
              ],
            ]}
          />
        </Section>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Section title="Connected services" description="Status only. Tokens and account identifiers are never shown." flush>
          {data.connections.length ? (
            <ul className="divide-y divide-glass-border">
              {data.connections.map((c) => (
                <li key={c.id} className="flex items-center gap-3 px-4 py-2.5 text-sm">
                  <Plug className="size-4 shrink-0 text-muted-foreground" aria-hidden />
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-medium">{c.name}</p>
                    <p className="truncate text-xs text-muted-foreground">
                      Connected <Time value={c.connected_at} /> · {c.scopes_count} permission{c.scopes_count === 1 ? "" : "s"}
                      {c.last_error_code ? ` · ${fmt.label(c.last_error_code)}` : ""}
                    </p>
                  </div>
                  <ConnectionStatus status={c.status} />
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState icon={Plug} title="No connected apps" />
          )}
        </Section>
        <Section title="Automations" flush>
          {data.automations.items.length ? (
            <ul className="divide-y divide-glass-border">
              {data.automations.items.map((a) => (
                <li key={a.id}>
                  <Link
                    href={`/admin/automations?automation_id=${a.id}`}
                    className="flex items-center gap-3 px-4 py-2.5 text-sm outline-none transition-colors hover:bg-muted/30 focus-visible:bg-muted/40"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-medium">{a.name}</p>
                      <p className="truncate text-xs text-muted-foreground">
                        {fmt.label(a.schedule_kind)} · last run {a.last_run_at ? fmt.ago(a.last_run_at) : "never"}
                        {a.consecutive_failures ? ` · ${a.consecutive_failures} failures in a row` : ""}
                      </p>
                    </div>
                    {a.enabled ? <StatusPill tone="success">On</StatusPill> : <StatusPill tone="neutral">Off</StatusPill>}
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState icon={Workflow} title="No automations" />
          )}
        </Section>
      </div>

      <Section title="Recent errors" description="Failed AI requests, automation runs, connector problems and platform errors" flush>
        {data.errors.length ? (
          <ul className="divide-y divide-glass-border">
            {data.errors.map((e) => (
              <li key={`${e.source}-${e.ref}`} className="flex flex-col gap-1 px-4 py-2.5 text-sm sm:flex-row sm:items-center sm:gap-3">
                <StatusPill tone={e.source === "connector" ? "warning" : "danger"}>{fmt.label(e.source)}</StatusPill>
                <span className="min-w-0 flex-1">
                  {e.label ? <span className="font-medium">{e.label} · </span> : null}
                  <span className="text-muted-foreground">{e.message ?? "No details"}</span>
                </span>
                <span className="shrink-0 text-xs text-muted-foreground">
                  <Time value={e.occurred_at} relative />
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState icon={AlertTriangle} title="No recent errors" />
        )}
      </Section>

      <div className="grid gap-4 lg:grid-cols-2">
        <Section title="Recent activity" description="Tools the assistant ran for this person (metadata only)" flush>
          {data.activity.length ? (
            <ul className="divide-y divide-glass-border">
              {data.activity.map((a) => (
                <li key={a.id} className="flex items-center gap-3 px-4 py-2 text-sm">
                  <div className="min-w-0 flex-1">
                    <p className="truncate">
                      <span className="font-medium">{a.provider_name}</span> <span className="text-muted-foreground">· {a.tool ?? a.action}</span>
                    </p>
                  </div>
                  <StatusPill tone={executionTone(a.status === "failed" ? "failed" : "completed")}>{fmt.label(a.status)}</StatusPill>
                  <span className="hidden shrink-0 text-xs text-muted-foreground sm:block">
                    <Time value={a.created_at} relative />
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState icon={History} title="No recorded activity" />
          )}
        </Section>
        <Section title="Active sessions" description="Devices currently signed in. IP addresses are partially masked." flush>
          {data.sessions.length ? (
            <ul className="divide-y divide-glass-border">
              {data.sessions.map((s) => (
                <li key={s.id} className="flex items-center gap-3 px-4 py-2.5 text-sm">
                  <Laptop className="size-4 shrink-0 text-muted-foreground" aria-hidden />
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-medium">{s.device}</p>
                    <p className="truncate text-xs text-muted-foreground">
                      {s.ip ?? "Unknown IP"} · signed in <Time value={s.created_at} relative />
                    </p>
                  </div>
                  <span className="shrink-0 text-xs text-muted-foreground">
                    seen <Time value={s.last_seen_at} relative />
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState icon={Laptop} title="No active sessions" />
          )}
        </Section>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Section title="Security events" description="Sign-ins, failed attempts, password and 2FA changes" flush>
          {data.security_events.length ? (
            <ul className="divide-y divide-glass-border">
              {data.security_events.map((e) => (
                <li key={e.id} className="flex items-center gap-3 px-4 py-2 text-sm">
                  <KeyRound className={e.kind.includes("failed") || e.kind.includes("blocked") ? "size-4 shrink-0 text-warning" : "size-4 shrink-0 text-muted-foreground"} aria-hidden />
                  <span className="min-w-0 flex-1 truncate">{e.message ?? fmt.label(e.kind)}</span>
                  <span className="shrink-0 text-xs text-muted-foreground">
                    <Time value={e.occurred_at} relative />
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState icon={KeyRound} title="No security events yet" />
          )}
        </Section>
        <Section title="Admin actions on this account" flush>
          {data.admin_actions.length ? (
            <ul className="divide-y divide-glass-border">
              {data.admin_actions.map((a) => (
                <li key={a.id} className="px-4 py-2 text-sm">
                  <p>
                    <span className="font-medium">{fmt.label(a.action)}</span> <span className="text-muted-foreground">by {a.actor.email ?? "system"}</span>
                  </p>
                  <p className="text-xs text-muted-foreground">
                    <Time value={a.created_at} />
                    {typeof a.metadata.reason === "string" ? ` · “${a.metadata.reason}”` : ""}
                  </p>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState icon={History} title="No admin actions yet" />
          )}
        </Section>
      </div>
    </>
  );
}

function ConnectionStatus({ status }: { status: string }) {
  if (status === "connected" || status === "syncing") return <StatusPill tone="success">{fmt.label(status)}</StatusPill>;
  if (status === "disconnected") return <StatusPill tone="neutral">Disconnected</StatusPill>;
  if (status === "expired" || status === "needs_attention") return <StatusPill tone="warning">{fmt.label(status)}</StatusPill>;
  if (status === "error") return <StatusPill tone="danger">Error</StatusPill>;
  return <StatusPill tone="neutral">{fmt.label(status)}</StatusPill>;
}

function Actions({ data }: { data: AdminUserDetail }) {
  const p = data.profile;
  const me = useAdminMe();
  const canManage = useCan("users:manage");
  const canRoles = useCan("roles:manage");
  const queryClient = useQueryClient();
  const [dialog, setDialog] = React.useState<"suspend" | "reactivate" | "revoke" | "role" | null>(null);
  const [reason, setReason] = React.useState("");
  const [revokeSessions, setRevokeSessions] = React.useState(true);
  const [role, setRole] = React.useState<PlatformRole>(p.role);

  const done = (message: string) => {
    toast.success(message);
    setDialog(null);
    void queryClient.invalidateQueries({ queryKey: adminKeys.all });
  };
  const fail = (error: unknown) => toast.error(messageFor(error));

  const suspend = useMutation({ mutationFn: () => adminApi.suspend(p.id, reason.trim(), revokeSessions), onSuccess: () => done("Account suspended"), onError: fail });
  const reactivate = useMutation({ mutationFn: () => adminApi.reactivate(p.id), onSuccess: () => done("Account reactivated"), onError: fail });
  const revoke = useMutation({
    mutationFn: () => adminApi.revokeSessions(p.id),
    onSuccess: (r) => done(`Signed out of ${r.revoked} session${r.revoked === 1 ? "" : "s"}`),
    onError: fail,
  });
  const changeRole = useMutation({ mutationFn: () => adminApi.setRole(p.id, role), onSuccess: () => done("Role updated"), onError: fail });

  const self = me.data?.id === p.id;
  const myRank = RANK[me.data?.role ?? "user"];
  // Mirrors the server rules so people aren't offered buttons that would be refused.
  const outranked = me.data?.role !== "admin" && RANK[p.role] >= myRank;
  if (self) return <p className="text-xs text-muted-foreground">This is your account. Use your own settings to change it.</p>;
  if (!canManage && !canRoles) return <p className="text-xs text-muted-foreground">Read-only access</p>;

  return (
    <>
      {canRoles ? (
        <Button variant="outline" onClick={() => (setRole(p.role), setDialog("role"))}>
          <ShieldCheck aria-hidden /> Change role
        </Button>
      ) : null}
      {canManage && !outranked ? (
        <>
          <Button variant="outline" onClick={() => setDialog("revoke")} disabled={!data.sessions.length}>
            <LogOut aria-hidden /> Sign out everywhere
          </Button>
          {p.is_active ? (
            <Button variant="destructive" onClick={() => (setReason(""), setRevokeSessions(true), setDialog("suspend"))}>
              <CircleSlash aria-hidden /> Suspend
            </Button>
          ) : (
            <Button onClick={() => setDialog("reactivate")}>
              <RotateCcw aria-hidden /> Reactivate
            </Button>
          )}
        </>
      ) : null}

      <Dialog open={dialog === "suspend"} onOpenChange={(o) => !o && setDialog(null)}>
        <DialogContent className="sm:max-w-md">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (reason.trim().length >= 3) suspend.mutate();
            }}
          >
            <DialogHeader>
              <DialogTitle>Suspend {p.display_name}?</DialogTitle>
              <DialogDescription>
                They won&apos;t be able to sign in and their automations stop running. Their data is kept, and you can reactivate the account at any time.
              </DialogDescription>
            </DialogHeader>
            <div className="mt-4 space-y-3">
              <div className="space-y-1.5">
                <Label htmlFor="suspend-reason">Reason (kept in the audit log)</Label>
                <Textarea id="suspend-reason" value={reason} onChange={(e) => setReason(e.target.value)} maxLength={500} rows={3} required minLength={3} autoFocus />
              </div>
              <label className="flex items-center gap-2 text-sm">
                <Checkbox checked={revokeSessions} onCheckedChange={(v) => setRevokeSessions(v === true)} />
                Sign them out of every device now
              </label>
            </div>
            <DialogFooter className="mt-4">
              <Button type="button" variant="outline" onClick={() => setDialog(null)} disabled={suspend.isPending}>
                Cancel
              </Button>
              <Button type="submit" variant="destructive" disabled={suspend.isPending || reason.trim().length < 3}>
                Suspend account
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={dialog === "reactivate"}
        onOpenChange={(o) => !o && setDialog(null)}
        title={`Reactivate ${p.display_name}?`}
        description="They'll be able to sign in again. Automations stay as they were; paused ones remain paused."
        confirmLabel="Reactivate"
        destructive={false}
        pending={reactivate.isPending}
        onConfirm={() => reactivate.mutate()}
      />
      <ConfirmDialog
        open={dialog === "revoke"}
        onOpenChange={(o) => !o && setDialog(null)}
        title="Sign out of every device?"
        description={`${p.display_name} will be signed out of ${data.sessions.length} active session${data.sessions.length === 1 ? "" : "s"} and must sign in again.`}
        confirmLabel="Sign out everywhere"
        pending={revoke.isPending}
        onConfirm={() => revoke.mutate()}
      />
      <Dialog open={dialog === "role"} onOpenChange={(o) => !o && setDialog(null)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Change platform role</DialogTitle>
            <DialogDescription>
              Staff roles open this admin area. Read-only admins can view everything; support can also suspend and sign people out; admins can change roles and platform
              settings. Lowering a role signs the person out.
            </DialogDescription>
          </DialogHeader>
          <div className="mt-2 space-y-1.5">
            <Label htmlFor="role-select">Role</Label>
            <Select value={role} onValueChange={(v) => setRole(v as PlatformRole)}>
              <SelectTrigger id="role-select" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {(Object.keys(ROLE_LABEL) as PlatformRole[]).map((r) => (
                  <SelectItem key={r} value={r}>
                    {ROLE_LABEL[r]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <DialogFooter className="mt-4">
            <Button variant="outline" onClick={() => setDialog(null)} disabled={changeRole.isPending}>
              Cancel
            </Button>
            <Button
              variant={RANK[role] < RANK[p.role] ? "destructive" : "default"}
              onClick={() => changeRole.mutate()}
              disabled={changeRole.isPending || role === p.role}
            >
              {RANK[role] > RANK[p.role] ? `Make ${ROLE_LABEL[role].toLowerCase()}` : `Change to ${ROLE_LABEL[role].toLowerCase()}`}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
