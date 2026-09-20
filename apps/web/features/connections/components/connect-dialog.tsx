"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, Lock, ShieldCheck, Unplug } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { LogoMark } from "@/components/brand/logo";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { messageFor } from "@/features/auth/components/auth-form-error";
import { connectionsApi } from "@/features/connections/api";
import { ProviderLogo } from "@/features/connections/components/marketplace";
import type { ConnectMethod, Provider } from "@/lib/api/types";

/**
 * Connect flow: one click. "Continue with Notely" sends the user to the vendor's own consent
 * screen — through the deployment's OAuth app, or the vendor's official MCP server (which
 * registers Notely as a client on the fly) — and brings them back connected. No tokens, ever.
 */
export function ConnectDialog({
  provider,
  open,
  onOpenChange,
  reconnect = false,
  method,
}: {
  provider: Provider;
  open: boolean;
  onOpenChange: (o: boolean) => void;
  reconnect?: boolean;
  method: ConnectMethod;
}) {
  const isCustomServer = provider.id === "mcp_server";
  const [serverUrl, setServerUrl] = React.useState(String(provider.connection?.config.server_url ?? ""));

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[92dvh] overflow-y-auto sm:max-w-md">
        <div className="flex flex-col items-center gap-3 pt-2 text-center">
          <div className="flex items-center gap-3">
            <LogoMark size={56} className="shadow-2" />
            <span className="flex items-center gap-1" aria-hidden>
              <span className="size-1.5 rounded-full bg-muted-foreground/40" />
              <span className="size-1.5 rounded-full bg-muted-foreground/60" />
              <span className="size-1.5 rounded-full bg-ai" />
            </span>
            <ProviderLogo provider={provider} size="lg" className="shadow-2" />
          </div>
          <DialogTitle className="text-xl">
            {reconnect ? "Reconnect" : "Connect"} Notely to {provider.name}
          </DialogTitle>
          <DialogDescription className="max-w-xs text-muted-foreground">
            You’ll be taken to {provider.name} to sign in and approve access, then brought straight back.
          </DialogDescription>
        </div>

        <div className="mt-2 divide-y divide-glass-border rounded-xl bg-muted/30 px-4 text-sm ring-1 ring-glass-border">
          <Section icon={Lock} title="You're in control">
            Notely only does what you ask, and only through the permissions you approve on {provider.name}&apos;s own consent screen. Reads run automatically; every change waits for your review.
          </Section>
          <Section icon={ShieldCheck} title="Apps may introduce elevated risk">
            Content coming back from {provider.name} is treated as untrusted data, never as instructions — but a malicious message or page could still try to influence a request. Review approvals carefully.
          </Section>
          <Section icon={Unplug} title="Data shared with this app">
            {provider.name} receives only the requests Notely makes on your behalf (search terms, the items you ask to read, the changes you approve). Your notes are never sent unless you ask for it. Access is stored encrypted and revoked when you disconnect.
          </Section>
        </div>

        {isCustomServer ? (
          <div className="space-y-2">
            <Label htmlFor="mcp-url">Server URL</Label>
            <Input id="mcp-url" type="url" placeholder="https://mcp.example.com/mcp" value={serverUrl} onChange={(e) => setServerUrl(e.target.value)} autoComplete="off" />
            <p className="text-xs text-muted-foreground">Notely asks the server how to sign in. Servers that need no sign-in connect straight away.</p>
          </div>
        ) : null}

        <ContinueButton provider={provider} method={method} serverUrl={isCustomServer ? serverUrl : null} />

        {provider.docs_url ? (
          <Button asChild variant="ghost" className="w-full text-muted-foreground">
            <a href={provider.docs_url} target="_blank" rel="noopener noreferrer">
              Continue to {provider.name} <ExternalLink className="size-3.5" aria-hidden />
            </a>
          </Button>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}

function Section({ icon: Icon, title, children }: { icon: React.ElementType; title: string; children: React.ReactNode }) {
  return (
    <section className="flex gap-3 py-3">
      <span className="mt-0.5 grid size-6 shrink-0 place-items-center rounded-md bg-ai-soft text-ai">
        <Icon className="size-3.5" aria-hidden />
      </span>
      <span>
        <h3 className="font-medium">{title}</h3>
        <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">{children}</p>
      </span>
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
    <Button size="lg" className="w-full rounded-full" disabled={disabled} onClick={() => go.mutate()}>
      {go.isPending ? "Opening…" : "Continue with Notely"}
    </Button>
  );
}
