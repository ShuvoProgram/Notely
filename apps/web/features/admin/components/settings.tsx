"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as React from "react";
import { toast } from "sonner";

import { CheckCircle2, InfoIcon, XCircle } from "@/components/icons";
import { PageHeader } from "@/components/layout/page-header";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { adminApi, adminKeys, type AdminSettings, type SettingItem } from "@/features/admin/api";
import { ErrorBlock, Facts, fmt, LoadingBlock, Section, Time, useCan } from "@/features/admin/components/admin-ui";
import { messageFor } from "@/features/auth/components/auth-form-error";

const GROUPS: { id: SettingItem["group"]; title: string; description: string }[] = [
  { id: "availability", title: "Availability", description: "Maintenance and sign-ups" },
  { id: "features", title: "Features", description: "Switch product areas on or off for everyone" },
  { id: "limits", title: "Usage limits", description: "Per-person caps. Leave empty for no cap." },
];

/** Settings whose change would disrupt everyone get a confirmation. */
const RISKY: Record<string, (v: unknown) => string | null> = {
  maintenance_mode: (v) => (v ? "Everyone will be unable to save changes until you turn it off." : null),
  signups_enabled: (v) => (v ? null : "New people won't be able to create an account."),
  ai_enabled: (v) => (v ? null : "The assistant and AI workflow drafting stop working for everyone."),
  automations_enabled: (v) => (v ? null : "Scheduled runs pause and nobody can create or run automations."),
};

type Draft = Record<string, boolean | number | string | null>;

export function AdminSettingsView() {
  const q = useQuery({ queryKey: adminKeys.settings, queryFn: adminApi.settings });
  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Admin"
        title="Settings"
        description="Platform-wide switches that take effect within seconds, no deploy needed. Secrets and provider keys stay in the server environment."
      />
      {q.isPending ? <LoadingBlock rows={8} /> : q.error ? <ErrorBlock error={q.error} onRetry={() => q.refetch()} /> : <Editor key={JSON.stringify(q.data.settings.map((s) => [s.key, s.value]))} data={q.data} />}
    </div>
  );
}

function Editor({ data }: { data: AdminSettings }) {
  const canEdit = useCan("platform:manage");
  const queryClient = useQueryClient();
  const initial = React.useMemo(() => Object.fromEntries(data.settings.map((s) => [s.key, s.value])) as Draft, [data]);
  const [draft, setDraft] = React.useState<Draft>(initial);
  const [confirm, setConfirm] = React.useState<string[] | null>(null);

  const changes = Object.fromEntries(Object.entries(draft).filter(([k, v]) => v !== initial[k]));
  const dirty = Object.keys(changes).length > 0;
  const invalid = data.settings.some((s) => s.kind === "int" && draft[s.key] !== null && (Number.isNaN(draft[s.key]) || (s.minimum !== null && (draft[s.key] as number) < s.minimum) || (s.maximum !== null && (draft[s.key] as number) > s.maximum)));

  const save = useMutation({
    mutationFn: () => adminApi.updateSettings(changes),
    onSuccess: (next) => {
      queryClient.setQueryData(adminKeys.settings, next);
      toast.success("Settings saved");
      setConfirm(null);
    },
    onError: (e) => toast.error(messageFor(e)),
  });

  const submit = () => {
    const warnings = Object.entries(changes)
      .map(([k, v]) => RISKY[k]?.(v))
      .filter((w): w is string => Boolean(w));
    if (warnings.length) setConfirm(warnings);
    else save.mutate();
  };

  return (
    <>
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        {GROUPS.map((g) => (
          <Section key={g.id} title={g.title} description={g.description}>
            <div className="divide-y divide-glass-border">
              {data.settings
                .filter((s) => s.group === g.id)
                .map((s) => (
                  <SettingRow key={s.key} item={s} value={draft[s.key] ?? null} disabled={!canEdit} onChange={(v) => setDraft((d) => ({ ...d, [s.key]: v }))} />
                ))}
            </div>
          </Section>
        ))}
        {canEdit ? (
          <div className="glass-2 sticky bottom-3 z-10 flex flex-wrap items-center justify-between gap-3 rounded-2xl px-4 py-3">
            <p className="text-sm text-muted-foreground">{dirty ? `${Object.keys(changes).length} unsaved change${Object.keys(changes).length === 1 ? "" : "s"}` : "All changes saved"}</p>
            <div className="flex gap-2">
              <Button type="button" variant="outline" disabled={!dirty || save.isPending} onClick={() => setDraft(initial)}>
                Discard
              </Button>
              <Button type="submit" disabled={!dirty || invalid || save.isPending}>
                Save changes
              </Button>
            </div>
          </div>
        ) : (
          <p className="flex items-center gap-2 text-sm text-muted-foreground">
            <InfoIcon className="size-4" aria-hidden /> Only admins can change these settings.
          </p>
        )}
      </form>

      <Environment data={data} />

      <ConfirmDialog
        open={confirm !== null}
        onOpenChange={(o) => !o && setConfirm(null)}
        title="Apply these changes?"
        description={
          <span className="block space-y-1">
            {confirm?.map((w) => (
              <span key={w} className="block">
                {w}
              </span>
            ))}
          </span>
        }
        confirmLabel="Apply"
        pending={save.isPending}
        onConfirm={() => save.mutate()}
      />
    </>
  );
}

function SettingRow({ item, value, disabled, onChange }: { item: SettingItem; value: Draft[string]; disabled: boolean; onChange: (v: Draft[string]) => void }) {
  const id = `setting-${item.key}`;
  const control =
    item.kind === "bool" ? (
      <Switch id={id} checked={Boolean(value)} onCheckedChange={(v) => onChange(v)} disabled={disabled} />
    ) : item.kind === "int" ? (
      <Input
        id={id}
        type="number"
        inputMode="numeric"
        min={item.minimum ?? undefined}
        max={item.maximum ?? undefined}
        value={value === null || value === undefined ? "" : String(value)}
        placeholder="No cap"
        onChange={(e) => onChange(e.target.value === "" ? null : Math.trunc(Number(e.target.value)))}
        disabled={disabled}
        className="w-32"
      />
    ) : null;
  return (
    <div className="flex flex-col gap-2 py-3 first:pt-0 last:pb-0 sm:flex-row sm:items-start sm:justify-between sm:gap-6">
      <div className="min-w-0 flex-1">
        <Label htmlFor={id} className="text-sm font-medium">
          {item.label}
        </Label>
        <p className="mt-0.5 text-xs text-muted-foreground">{item.description}</p>
        {item.updated_at ? (
          <p className="mt-0.5 text-[11px] text-muted-foreground">
            Changed <Time value={item.updated_at} relative />
          </p>
        ) : null}
        {item.kind === "text" ? (
          <Textarea id={id} className="mt-2" rows={2} maxLength={item.max_length ?? undefined} value={String(value ?? "")} onChange={(e) => onChange(e.target.value)} disabled={disabled} />
        ) : null}
      </div>
      {control ? <div className="shrink-0">{control}</div> : null}
    </div>
  );
}

function Flag({ on, children }: { on: boolean; children: React.ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      {on ? <CheckCircle2 className="size-4 text-success" aria-hidden /> : <XCircle className="size-4 text-muted-foreground" aria-hidden />}
      {children}
    </span>
  );
}

function Environment({ data }: { data: AdminSettings }) {
  const e = data.environment;
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Section title="AI provider" description="Configured in the server environment (read-only)">
        <Facts
          items={[
            ["Mode", e.ai.provider === "fake" ? "Scripted (development only)" : "LiteLLM gateway"],
            ["Default model alias", <code key="d" className="text-xs">{e.ai.default_model}</code>],
            ["Fast model alias", <code key="f" className="text-xs">{e.ai.fast_model}</code>],
            ["Gateway key", <Flag key="k" on={e.ai.gateway_key_configured}>{e.ai.gateway_key_configured ? "Configured" : "Not set"}</Flag>],
            ["Max tool steps per request", fmt.n(e.ai.max_tool_iterations)],
            ["Request timeout", `${e.ai.request_timeout_seconds} s`],
          ]}
        />
      </Section>
      <Section title="Security & delivery" description="Configured in the server environment (read-only)">
        <Facts
          items={[
            ["Environment", fmt.label(e.environment)],
            ["Admin session lifetime", `${e.security.admin_session_max_age_hours} h`],
            ["2FA required for admins", <Flag key="2" on={e.security.admin_require_2fa}>{e.security.admin_require_2fa ? "Yes" : "No"}</Flag>],
            ["Session lifetime", `${e.security.session_ttl_hours} h (sliding)`],
            ["Credential encryption", <Flag key="e" on={e.security.encryption_configured}>{e.security.encryption_configured ? "Configured" : "Missing"}</Flag>],
            ["Sign-in rate limit", `${e.security.rate_limit_auth_per_minute}/min per IP`],
            ["Outbound email", <Flag key="m" on={e.email.configured}>{e.email.configured ? (e.email.from_address ?? "Configured") : "Not configured"}</Flag>],
            ["Google / Microsoft sign-in", e.sign_in_providers.length ? e.sign_in_providers.map(fmt.label).join(", ") : "Off"],
            ["Connectors with OAuth apps", `${e.connectors_configured} of ${e.connectors_total}`],
          ]}
        />
      </Section>
      <Section title="Roles" description="What each staff role can do. Grant the first admin with `python -m app.manage set-role`." className="lg:col-span-2">
        <div className="grid gap-3 sm:grid-cols-3">
          {(["viewer", "support", "admin"] as const).map((r) => (
            <div key={r} className="glass rounded-xl px-3 py-2.5 text-sm">
              <p className="font-medium">{{ viewer: "Read-only admin", support: "Support", admin: "Admin" }[r]}</p>
              <ul className="mt-1 space-y-0.5 text-xs text-muted-foreground">
                {data.roles[r].map((p) => (
                  <li key={p}>
                    {
                      {
                        "admin:read": "View every admin page",
                        "users:manage": "Suspend, reactivate, sign people out",
                        "roles:manage": "Change staff roles",
                        "platform:manage": "Platform settings & connector availability",
                      }[p]
                    }
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </Section>
    </div>
  );
}
