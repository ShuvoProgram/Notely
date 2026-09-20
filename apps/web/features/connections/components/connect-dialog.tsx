"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, ExternalLink, Lock, Sparkles } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { messageFor } from "@/features/auth/components/auth-form-error";
import { connectionsApi } from "@/features/connections/api";
import { ProviderLogo } from "@/features/connections/components/marketplace";
import { ApiError } from "@/lib/api/client";
import type { ConfigField, ConnectMethod, Provider } from "@/lib/api/types";
import { cn } from "@/lib/utils";

/**
 * Connect flow. The primary path is always one click: "Continue with Notely" sends the user to
 * the vendor's own consent screen (the deployment's OAuth app, or the vendor's official MCP
 * server with a dynamically registered client) and brings them back connected. Personal tokens
 * and custom config live under "Show other options".
 */
export function ConnectDialog({
  provider,
  open,
  onOpenChange,
  reconnect = false,
  initialMethod,
}: {
  provider: Provider;
  open: boolean;
  onOpenChange: (o: boolean) => void;
  reconnect?: boolean;
  initialMethod?: ConnectMethod;
}) {
  const methods = provider.connect_methods;
  const primary: ConnectMethod | null = methods.includes("oauth") ? "oauth" : methods.includes("mcp") ? "mcp" : null;
  const isCustomServer = provider.id === "mcp_server";
  const [showOthers, setShowOthers] = React.useState(initialMethod === "token" || initialMethod === "config" || primary === null);
  const [serverUrl, setServerUrl] = React.useState(String(provider.connection?.config.server_url ?? ""));

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[92dvh] overflow-y-auto sm:max-w-md">
        <div className="flex flex-col items-center gap-3 pt-2 text-center">
          <div className="flex items-center gap-3">
            <div className="grid size-14 place-items-center rounded-2xl border bg-card">
              <Sparkles className="size-6 text-ai" aria-hidden />
            </div>
            <span className="text-muted-foreground" aria-hidden>
              •••
            </span>
            <div className="grid size-14 place-items-center rounded-2xl border bg-card">
              <ProviderLogo provider={provider} />
            </div>
          </div>
          <DialogTitle className="text-xl">
            {reconnect ? "Reconnect" : "Connect"} {provider.name}
          </DialogTitle>
          <DialogDescription className="sr-only">{provider.description}</DialogDescription>
        </div>

        <div className="mt-2 divide-y rounded-xl border bg-card px-4 text-sm">
          <Section title="You're in control">
            Notely only does what you ask, and only through the permissions you approve on {provider.name}&apos;s own consent screen. Reads run automatically; every change waits for your review.
          </Section>
          <Section title="Apps may introduce elevated risk">
            Content coming back from {provider.name} is treated as untrusted data, never as instructions — but a malicious message or page could still try to influence a request. Review approvals carefully.
          </Section>
          <Section title="Data shared with this app">
            {provider.name} receives only the requests Notely makes on your behalf (search terms, the items you ask to read, the changes you approve). Your notes are never sent unless you ask for it. Tokens are stored encrypted and revoked when you disconnect.
          </Section>
        </div>

        {primary === "mcp" && isCustomServer ? (
          <div className="space-y-2">
            <Label htmlFor="mcp-url">Server URL</Label>
            <Input id="mcp-url" type="url" placeholder="https://mcp.example.com/mcp" value={serverUrl} onChange={(e) => setServerUrl(e.target.value)} autoComplete="off" />
            <p className="text-xs text-muted-foreground">Notely asks the server how to sign in. Servers that need no sign-in connect straight away.</p>
          </div>
        ) : null}

        {primary ? <ContinueButton provider={provider} method={primary} serverUrl={isCustomServer ? serverUrl : null} /> : null}

        {provider.docs_url ? (
          <Button asChild variant="outline" className="w-full">
            <a href={provider.docs_url} target="_blank" rel="noopener noreferrer">
              Continue to {provider.name} <ExternalLink className="size-3.5" aria-hidden />
            </a>
          </Button>
        ) : null}

        {methods.includes("token") || methods.includes("config") ? (
          <div className="pt-1">
            {primary ? (
              <button type="button" className="mx-auto flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground" onClick={() => setShowOthers((v) => !v)} aria-expanded={showOthers}>
                Show other options <ChevronDown className={cn("size-4 transition-transform", showOthers && "rotate-180")} aria-hidden />
              </button>
            ) : null}
            {showOthers ? (
              <div className="mt-3">
                <TokenForm provider={provider} onDone={() => onOpenChange(false)} shared={isCustomServer ? { server_url: serverUrl } : {}} />
              </div>
            ) : null}
          </div>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="py-3">
      <h3 className="font-medium">{title}</h3>
      <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{children}</p>
    </section>
  );
}

/** One click: ask the API for the consent URL (or an immediate "connected" URL) and go there. */
function ContinueButton({ provider, method, serverUrl }: { provider: Provider; method: ConnectMethod; serverUrl: string | null }) {
  const queryClient = useQueryClient();
  const go = useMutation({
    mutationFn: async () => {
      const optional = provider.permissions.filter((p) => !p.required).map((p) => p.scope);
      const { authorize_url } = await connectionsApi.oauthStartUrl(provider.id, optional, { method, serverUrl: serverUrl || undefined });
      window.location.assign(authorize_url); // the vendor's consent page, or straight back when none is needed
    },
    onError: (e) => {
      queryClient.invalidateQueries({ queryKey: ["integrations"] });
      toast.error(messageFor(e));
    },
  });
  const disabled = go.isPending || (serverUrl !== null && !/^https?:\/\//.test(serverUrl));
  return (
    <Button size="lg" className="w-full" disabled={disabled} onClick={() => go.mutate()}>
      {go.isPending ? "Opening…" : "Continue with Notely"}
    </Button>
  );
}

/** Personal token / custom config: the fallback for deployments without a vendor app. */
function TokenForm({ provider, onDone, shared }: { provider: Provider; onDone: () => void; shared: Record<string, string> }) {
  const queryClient = useQueryClient();
  const spec = provider.token_auth;
  // Values already collected above the fold (the custom server URL) are reused, not re-asked.
  const fields: ConfigField[] = React.useMemo(() => {
    const base = (spec?.fields.length ? spec.fields : provider.config_fields).filter((f) => !(f.key in shared));
    const hasSecret = base.some((f) => f.kind === "secret");
    if (spec && !hasSecret) return [...base, { key: "__token", label: spec.label, kind: "secret", required: true, placeholder: spec.placeholder, help: "", options: [] }];
    return base;
  }, [provider.config_fields, shared, spec]);
  const [values, setValues] = React.useState<Record<string, string>>(() => Object.fromEntries(fields.map((f) => [f.key, String(provider.connection?.config[f.key] ?? "")])));
  const [errors, setErrors] = React.useState<Record<string, string>>({});
  const connect = useMutation({
    mutationFn: () => {
      const config: Record<string, unknown> = { ...shared };
      let token: string | null = null;
      for (const f of fields) {
        if (f.kind === "secret") token = values[f.key] || null;
        else config[f.key] = values[f.key] ?? "";
      }
      return connectionsApi.connect(provider.id, { config, token });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["integrations"] });
      queryClient.invalidateQueries({ queryKey: ["ai", "settings"] });
      toast.success(`${provider.name} connected`);
      onDone();
    },
    onError: (error) => {
      queryClient.invalidateQueries({ queryKey: ["integrations"] });
      if (error instanceof ApiError && Object.keys(error.fieldErrors).length) {
        setErrors(Object.fromEntries(Object.entries(error.fieldErrors).map(([k, v]) => [k === "token" ? "__token" : k, v[0] ?? "Invalid"])));
        return;
      }
      toast.error(messageFor(error));
    },
  });
  const aOrAn = (label: string) => `${/^[aeiou]/i.test(label) ? "an" : "a"} ${label.toLowerCase()}`;

  return (
    <form
      className="space-y-4 rounded-xl border bg-muted/30 p-4"
      onSubmit={(e) => {
        e.preventDefault();
        setErrors({});
        connect.mutate();
      }}
    >
      {spec ? (
        <div className="text-sm">
          <p className="font-medium">Connect with {aOrAn(spec.label)}</p>
          <p className="mt-1 text-xs text-muted-foreground">{spec.help}</p>
          {spec.help_url ? (
            <a href={spec.help_url} target="_blank" rel="noopener noreferrer" className="mt-1 inline-flex items-center gap-1 text-xs underline-offset-2 hover:underline">
              Open {provider.name} settings <ExternalLink className="size-3" aria-hidden />
            </a>
          ) : null}
        </div>
      ) : (
        <p className="text-sm font-medium">Connect with your own settings</p>
      )}
      {provider.permissions.length ? (
        <ul className="space-y-1 text-xs text-muted-foreground">
          {provider.permissions.map((p) => (
            <li key={p.scope} className="flex items-center gap-1.5">
              <Lock className="size-3" aria-hidden /> {p.label}
              {!p.required ? " (optional)" : ""}
            </li>
          ))}
        </ul>
      ) : null}
      {fields.map((f) => (
        <div key={f.key} className="space-y-1.5">
          <Label htmlFor={`cfg-${f.key}`}>
            {f.label}
            {!f.required ? <span className="ml-1 text-xs text-muted-foreground">(optional)</span> : null}
          </Label>
          <Input
            id={`cfg-${f.key}`}
            type={f.kind === "secret" ? "password" : f.kind === "url" ? "url" : "text"}
            autoComplete="off"
            placeholder={f.placeholder}
            value={values[f.key] ?? ""}
            onChange={(e) => setValues((v) => ({ ...v, [f.key]: e.target.value }))}
            aria-invalid={errors[f.key] ? true : undefined}
            aria-describedby={errors[f.key] ? `cfg-${f.key}-error` : f.help ? `cfg-${f.key}-help` : undefined}
          />
          {errors[f.key] ? (
            <p id={`cfg-${f.key}-error`} role="alert" className="text-xs text-destructive">
              {errors[f.key]}
            </p>
          ) : f.help ? (
            <p id={`cfg-${f.key}-help`} className="text-xs text-muted-foreground">
              {f.help}
            </p>
          ) : null}
        </div>
      ))}
      <Button type="submit" variant="secondary" className="w-full" disabled={connect.isPending}>
        {connect.isPending ? "Connecting…" : "Connect"}
      </Button>
    </form>
  );
}
