"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, Copy, ExternalLink, KeyRound, Trash2 } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { messageFor } from "@/features/auth/components/auth-form-error";
import { connectionsApi } from "@/features/connections/api";
import { ApiError } from "@/lib/api/client";
import type { ProviderDetail } from "@/lib/api/types";

/**
 * Shown when a vendor has no OAuth app on this deployment and no official MCP server: the
 * workspace owner registers their own app with the vendor (guided, with the redirect URI to
 * copy) and pastes its client id + secret. From then on everyone connects with the normal
 * one-click consent flow. The secret is stored encrypted and never shown again.
 */
export function OAuthAppSetup({ provider }: { provider: ProviderDetail }) {
  const queryClient = useQueryClient();
  const guide = provider.oauth_setup;
  const existing = provider.workspace_app;
  const [clientId, setClientId] = React.useState(existing?.client_id ?? "");
  const [secret, setSecret] = React.useState("");
  const [errors, setErrors] = React.useState<Record<string, string>>({});
  const [copied, setCopied] = React.useState(false);

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["integrations"] });
  const save = useMutation({
    mutationFn: () => connectionsApi.saveOAuthApp(provider.id, { client_id: clientId, client_secret: secret || null }),
    onSuccess: () => {
      setSecret("");
      setErrors({});
      invalidate();
      toast.success(`${provider.name} sign-in is set up — everyone in this workspace can connect now`);
    },
    onError: (error) => {
      if (error instanceof ApiError && Object.keys(error.fieldErrors).length) {
        setErrors(Object.fromEntries(Object.entries(error.fieldErrors).map(([k, v]) => [k, v[0] ?? "Invalid"])));
        return;
      }
      toast.error(messageFor(error));
    },
  });
  const remove = useMutation({
    mutationFn: () => connectionsApi.deleteOAuthApp(provider.id),
    onSuccess: () => {
      setClientId("");
      invalidate();
      toast.success("Removed");
    },
    onError: (e) => toast.error(messageFor(e)),
  });

  const copy = async () => {
    if (!provider.redirect_uri) return;
    try {
      await navigator.clipboard.writeText(provider.redirect_uri);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      toast.error("Couldn't copy — select the text and copy it manually.");
    }
  };

  return (
    <Card className="md:col-span-2">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <KeyRound className="size-4" aria-hidden /> {existing ? `${provider.name} sign-in for this workspace` : `Set up ${provider.name} sign-in for this workspace`}
        </CardTitle>
        <CardDescription>
          {provider.name} only lets people sign in through an app registered with {provider.name}. Register one once (about two minutes) and everyone here connects with a click — exactly like any other app.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-6 md:grid-cols-2">
        <div className="space-y-3 text-sm">
          {guide ? (
            <>
              <Button asChild variant="outline" size="sm">
                <a href={guide.console_url} target="_blank" rel="noopener noreferrer">
                  {guide.console_label} <ExternalLink className="size-3.5" aria-hidden />
                </a>
              </Button>
              <ol className="list-decimal space-y-1.5 pl-5 text-muted-foreground">
                {guide.steps.map((step) => (
                  <li key={step}>{step}</li>
                ))}
              </ol>
            </>
          ) : null}
          {provider.redirect_uri ? (
            <div className="space-y-1">
              <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Redirect URI</p>
              <div className="flex items-center gap-2">
                <code className="min-w-0 flex-1 truncate rounded bg-muted px-2 py-1 font-mono text-xs">{provider.redirect_uri}</code>
                <Button type="button" variant="outline" size="sm" onClick={() => void copy()} aria-label="Copy redirect URI">
                  {copied ? <Check className="size-3.5 text-success" aria-hidden /> : <Copy className="size-3.5" aria-hidden />}
                </Button>
              </div>
            </div>
          ) : null}
        </div>
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate();
          }}
        >
          <div className="space-y-2">
            <Label htmlFor="app-client-id">Client ID</Label>
            <Input id="app-client-id" value={clientId} onChange={(e) => setClientId(e.target.value)} autoComplete="off" aria-invalid={errors.client_id ? true : undefined} />
            {errors.client_id ? (
              <p role="alert" className="text-xs text-destructive">
                {errors.client_id}
              </p>
            ) : null}
          </div>
          <div className="space-y-2">
            <Label htmlFor="app-client-secret">Client secret</Label>
            <Input
              id="app-client-secret"
              type="password"
              value={secret}
              onChange={(e) => setSecret(e.target.value)}
              autoComplete="off"
              placeholder={existing ? "Stored — enter a new one to replace it" : ""}
              aria-invalid={errors.client_secret ? true : undefined}
            />
            {errors.client_secret ? (
              <p role="alert" className="text-xs text-destructive">
                {errors.client_secret}
              </p>
            ) : (
              <p className="text-xs text-muted-foreground">Encrypted at rest; Notely never displays it again.</p>
            )}
          </div>
          <div className="flex flex-wrap gap-2">
            <Button type="submit" disabled={save.isPending || !clientId.trim() || (!existing && !secret)}>
              {save.isPending ? "Saving…" : existing ? "Update" : "Save and enable Connect"}
            </Button>
            {existing ? (
              <Button type="button" variant="ghost" disabled={remove.isPending} onClick={() => remove.mutate()}>
                <Trash2 aria-hidden /> Remove
              </Button>
            ) : null}
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
