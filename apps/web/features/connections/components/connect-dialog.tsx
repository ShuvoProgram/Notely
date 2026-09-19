"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, Lock } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { messageFor } from "@/features/auth/components/auth-form-error";
import { connectionsApi } from "@/features/connections/api";
import { ApiError } from "@/lib/api/client";
import type { Provider } from "@/lib/api/types";

/**
 * Connect flow: shows what Notely will be able to do (permissions) and either sends the user to
 * the provider's consent screen (OAuth) or collects non-secret config + a token (token/none).
 */
export function ConnectDialog({ provider, open, onOpenChange, reconnect = false }: { provider: Provider; open: boolean; onOpenChange: (o: boolean) => void; reconnect?: boolean }) {
  const queryClient = useQueryClient();
  const [values, setValues] = React.useState<Record<string, string>>(() =>
    Object.fromEntries(provider.config_fields.map((f) => [f.key, String(provider.connection?.config[f.key] ?? "")])),
  );
  const [optionalScopes, setOptionalScopes] = React.useState<Set<string>>(() => new Set(provider.connection?.scopes ?? []));
  const [fieldErrors, setFieldErrors] = React.useState<Record<string, string>>({});

  const connect = useMutation({
    mutationFn: async () => {
      if (provider.auth === "oauth2") {
        const optional = provider.permissions.filter((p) => !p.required && optionalScopes.has(p.scope)).map((p) => p.scope);
        const { authorize_url } = await connectionsApi.oauthStartUrl(provider.id, optional);
        window.location.assign(authorize_url); // full navigation to the provider's consent page
        return null;
      }
      const config: Record<string, unknown> = {};
      let token: string | null = null;
      for (const f of provider.config_fields) {
        if (f.kind === "secret") token = values[f.key] || null;
        else config[f.key] = values[f.key] ?? "";
      }
      return connectionsApi.connect(provider.id, { config, token });
    },
    onSuccess: (conn) => {
      if (!conn) return;
      queryClient.invalidateQueries({ queryKey: ["integrations"] });
      queryClient.invalidateQueries({ queryKey: ["ai", "settings"] });
      toast.success(`${provider.name} connected`);
      onOpenChange(false);
    },
    onError: (error) => {
      // The backend records the failure on the connection; make the page reflect it.
      queryClient.invalidateQueries({ queryKey: ["integrations"] });
      if (error instanceof ApiError && Object.keys(error.fieldErrors).length) {
        setFieldErrors(Object.fromEntries(Object.entries(error.fieldErrors).map(([k, v]) => [k, v[0] ?? "Invalid"])));
        return;
      }
      toast.error(messageFor(error));
    },
  });

  const required = provider.permissions.filter((p) => p.required);
  const optional = provider.permissions.filter((p) => !p.required);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90dvh] overflow-y-auto">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            setFieldErrors({});
            connect.mutate();
          }}
        >
          <DialogHeader>
            <DialogTitle>
              {reconnect ? "Reconnect" : "Connect"} {provider.name}
            </DialogTitle>
            <DialogDescription>{provider.description}</DialogDescription>
          </DialogHeader>

          <div className="my-5 space-y-5">
            {provider.permissions.length ? (
              <section>
                <h3 className="text-sm font-medium">Notely will be able to</h3>
                <ul className="mt-2 space-y-1.5 text-sm">
                  {required.map((p) => (
                    <li key={p.scope} className="flex items-start gap-2">
                      <Lock className="mt-0.5 size-3.5 text-muted-foreground" aria-hidden />
                      <span>
                        {p.label}
                        {p.description ? <span className="block text-xs text-muted-foreground">{p.description}</span> : null}
                      </span>
                    </li>
                  ))}
                  {optional.map((p) => {
                    const id = `perm-${p.scope}`;
                    return (
                      <li key={p.scope} className="flex items-start gap-2">
                        <input
                          id={id}
                          type="checkbox"
                          className="mt-0.5 size-4 accent-[var(--ai)]"
                          checked={optionalScopes.has(p.scope)}
                          onChange={(e) =>
                            setOptionalScopes((s) => {
                              const next = new Set(s);
                              if (e.target.checked) next.add(p.scope);
                              else next.delete(p.scope);
                              return next;
                            })
                          }
                        />
                        <label htmlFor={id}>
                          {p.label} <span className="text-xs text-muted-foreground">(optional)</span>
                          {p.description ? <span className="block text-xs text-muted-foreground">{p.description}</span> : null}
                        </label>
                      </li>
                    );
                  })}
                </ul>
                <p className="mt-2 text-xs text-muted-foreground">Notely only requests the minimum permissions needed. You can disconnect at any time.</p>
              </section>
            ) : null}

            {provider.config_fields.map((f) => (
              <div key={f.key} className="space-y-2">
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
                  aria-invalid={fieldErrors[f.key] ? true : undefined}
                  aria-describedby={fieldErrors[f.key] ? `cfg-${f.key}-error` : f.help ? `cfg-${f.key}-help` : undefined}
                />
                {fieldErrors[f.key] ? (
                  <p id={`cfg-${f.key}-error`} role="alert" className="text-xs text-destructive">
                    {fieldErrors[f.key]}
                  </p>
                ) : f.help ? (
                  <p id={`cfg-${f.key}-help`} className="text-xs text-muted-foreground">
                    {f.help}
                  </p>
                ) : null}
              </div>
            ))}

            {provider.auth === "oauth2" ? (
              <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <ExternalLink className="size-3.5" aria-hidden /> You&apos;ll be taken to {provider.name} to sign in and approve access, then brought back here.
              </p>
            ) : null}
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={connect.isPending}>
              {connect.isPending ? "Connecting…" : provider.auth === "oauth2" ? `Continue to ${provider.name}` : "Connect"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
