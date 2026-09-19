"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Check, ExternalLink, Loader2, RefreshCw, Stethoscope, Unplug, XCircle } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { messageFor } from "@/features/auth/components/auth-form-error";
import { connectionsApi } from "@/features/connections/api";
import { ConnectDialog } from "@/features/connections/components/connect-dialog";
import { ConnectionStatusBadge, relativeTime } from "@/features/connections/components/connection-status";
import { CATEGORY_LABELS, ProviderLogo } from "@/features/connections/components/marketplace";
import type { ConnectionTestResult } from "@/lib/api/types";

const CALLBACK_ERRORS: Record<string, string> = {
  OAUTH_STATE_INVALID: "The sign-in request expired or was tampered with. Please try again.",
  PROVIDER_AUTH_FAILED: "Authorization failed. Your access wasn't granted.",
  PROVIDER_ADMIN_APPROVAL_REQUIRED: "Your organization requires an administrator to approve this app.",
};

export function ProviderDetail({ providerId }: { providerId: string }) {
  const router = useRouter();
  const params = useSearchParams();
  const queryClient = useQueryClient();
  const detail = useQuery({ queryKey: ["integrations", "provider", providerId], queryFn: () => connectionsApi.provider(providerId) });
  const [connectOpen, setConnectOpen] = React.useState(false);
  const [disconnectStep, setDisconnectStep] = React.useState<0 | 1 | 2>(0);
  const [purge, setPurge] = React.useState(false);
  const [testResult, setTestResult] = React.useState<ConnectionTestResult | null>(null);

  // Surface OAuth callback outcome once, then clean the URL.
  React.useEffect(() => {
    const error = params.get("error");
    const connected = params.get("connected");
    if (!error && !connected) return;
    if (connected) toast.success("Connected");
    if (error) toast.error(CALLBACK_ERRORS[error] ?? "This action couldn't be completed. Review the details and try again.");
    queryClient.invalidateQueries({ queryKey: ["integrations"] });
    router.replace(`/app/settings/connections/${providerId}`);
  }, [params, providerId, queryClient, router]);

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["integrations"] });
    queryClient.invalidateQueries({ queryKey: ["ai", "settings"] });
  };
  const test = useMutation({
    mutationFn: connectionsApi.test,
    onSuccess: (r) => {
      setTestResult(r);
      invalidate();
    },
    onError: (e) => toast.error(messageFor(e)),
  });
  const disconnect = useMutation({
    mutationFn: ({ id, purge }: { id: string; purge: boolean }) => connectionsApi.disconnect(id, purge),
    onSuccess: () => {
      invalidate();
      setDisconnectStep(0);
      setTestResult(null);
      toast.success(`${detail.data?.name ?? "Integration"} disconnected`);
    },
    onError: (e) => toast.error(messageFor(e)),
  });

  if (detail.isPending) return <Skeleton className="h-72 w-full rounded-xl" />;
  if (detail.error || !detail.data) {
    return (
      <p role="alert" className="text-sm text-destructive">
        {messageFor(detail.error)}
      </p>
    );
  }
  const p = detail.data;
  const conn = p.connection && p.connection.status !== "disconnected" ? p.connection : null;
  const attention = conn && (conn.status === "expired" || conn.status === "needs_attention" || conn.status === "error");

  return (
    <div className="space-y-6">
      <Link href="/app/settings/connections" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="size-4" aria-hidden /> All connections
      </Link>

      <header className="flex flex-wrap items-start gap-4">
        <ProviderLogo provider={p} size="lg" />
        <div className="min-w-0 flex-1">
          <h1 className="text-2xl font-semibold tracking-tight">{p.name}</h1>
          <p className="text-sm text-muted-foreground">
            {CATEGORY_LABELS[p.category] ?? p.category}
            {p.docs_url ? (
              <>
                {" · "}
                <a href={p.docs_url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 underline-offset-2 hover:underline">
                  Documentation <ExternalLink className="size-3" aria-hidden />
                </a>
              </>
            ) : null}
          </p>
          <div className="mt-3">
            {!p.configured ? (
              <p className="text-sm text-muted-foreground">{p.name} isn&apos;t configured on this Notely deployment yet.</p>
            ) : (
              <ConnectionStatusBadge status={conn?.status ?? "none"} lastChecked={conn?.last_checked_at} lastError={conn?.last_error} />
            )}
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          {!conn && p.configured ? <Button onClick={() => setConnectOpen(true)}>Connect</Button> : null}
          {conn ? (
            <>
              {attention ? (
                <Button onClick={() => setConnectOpen(true)}>
                  <RefreshCw aria-hidden /> {conn.status === "expired" ? "Reconnect" : "Fix"}
                </Button>
              ) : null}
              <Button variant="outline" onClick={() => test.mutate(conn.id)} disabled={test.isPending}>
                {test.isPending ? <Loader2 className="animate-spin" aria-hidden /> : <Stethoscope aria-hidden />} Test connection
              </Button>
              <Button variant="outline" onClick={() => setDisconnectStep(1)}>
                <Unplug aria-hidden /> Disconnect
              </Button>
            </>
          ) : null}
        </div>
      </header>

      <p className="max-w-2xl text-sm text-muted-foreground">{p.description}</p>

      {testResult ? (
        <Card role="status" aria-live="polite">
          <CardHeader>
            <CardTitle className="text-base">{testResult.healthy ? "Connection healthy" : "Connection needs attention"}</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-1.5 text-sm">
              {testResult.steps.map((s) => (
                <li key={s.name} className="flex items-start gap-2">
                  {s.ok ? <Check className="mt-0.5 size-4 text-success" aria-hidden /> : <XCircle className="mt-0.5 size-4 text-destructive" aria-hidden />}
                  <span>
                    {s.name}
                    {s.detail ? <span className="ml-2 text-xs text-muted-foreground">{s.detail}</span> : null}
                  </span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      ) : null}

      <div className="grid gap-4 md:grid-cols-2">
        {conn ? (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Connected account</CardTitle>
            </CardHeader>
            <CardContent className="space-y-1 text-sm">
              <p className="font-medium">{conn.external_account_name ?? "—"}</p>
              {conn.external_account_id ? <p className="text-xs text-muted-foreground">{conn.external_account_id}</p> : null}
              <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-xs text-muted-foreground">
                <dt>Connected</dt>
                <dd>{relativeTime(conn.created_at)}</dd>
                <dt>Last checked</dt>
                <dd>{relativeTime(conn.last_checked_at)}</dd>
                <dt>Last sync</dt>
                <dd>{conn.last_sync_at ? relativeTime(conn.last_sync_at) : p.supports_sync ? "not yet" : "on-demand only"}</dd>
                <dt>Local data</dt>
                <dd>{p.local_item_count} indexed item{p.local_item_count === 1 ? "" : "s"}</dd>
              </dl>
              {Object.keys(conn.config).length ? (
                <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-xs text-muted-foreground">
                  {Object.entries(conn.config).map(([k, v]) => (
                    <React.Fragment key={k}>
                      <dt className="capitalize">{k.replace(/_/g, " ")}</dt>
                      <dd className="truncate">{String(v)}</dd>
                    </React.Fragment>
                  ))}
                </dl>
              ) : null}
            </CardContent>
          </Card>
        ) : null}

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Capabilities</CardTitle>
            <CardDescription>What the assistant can do through this integration.</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-1.5">
            {p.capabilities.map((c) => (
              <Badge key={c} variant="secondary" className="font-normal capitalize">
                {c}
              </Badge>
            ))}
          </CardContent>
        </Card>

        {p.permissions.length ? (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Permissions</CardTitle>
              <CardDescription>Granted scopes are ticked. Notely never asks for more than it needs.</CardDescription>
            </CardHeader>
            <CardContent>
              <ul className="space-y-1.5 text-sm">
                {p.permissions.map((perm) => {
                  const granted = conn?.scopes.includes(perm.scope) ?? false;
                  return (
                    <li key={perm.scope} className="flex items-center gap-2">
                      {granted ? <Check className="size-4 text-success" aria-hidden /> : <span className="inline-block size-4 rounded-sm border" aria-hidden />}
                      <span>{perm.label}</span>
                      <span className="sr-only">{granted ? "granted" : "not granted"}</span>
                      {!perm.required ? <span className="text-xs text-muted-foreground">optional</span> : null}
                    </li>
                  );
                })}
              </ul>
            </CardContent>
          </Card>
        ) : null}

        {conn && p.tools.length ? (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Tools ({p.tools.length})</CardTitle>
              <CardDescription>Discovered from the server. Reads run automatically; anything else asks first.</CardDescription>
            </CardHeader>
            <CardContent>
              <ul className="divide-y text-sm">
                {p.tools.map((t) => (
                  <li key={t.name} className="flex flex-wrap items-center gap-2 py-1.5">
                    <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs">{t.name}</code>
                    <span className="min-w-0 flex-1 truncate text-xs text-muted-foreground">{t.description}</span>
                    <Badge variant="outline" className="font-normal">
                      {t.destructive ? "Destructive" : t.read_only ? "Read" : "Change"}
                    </Badge>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
        ) : null}
      </div>

      {p.configured ? <ConnectDialog key={connectOpen ? "open" : "closed"} provider={p} open={connectOpen} onOpenChange={setConnectOpen} reconnect={Boolean(conn)} /> : null}

      <Dialog open={disconnectStep === 1} onOpenChange={(o) => !o && setDisconnectStep(0)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Disconnect {p.name}?</DialogTitle>
            <DialogDescription>Notely will:</DialogDescription>
          </DialogHeader>
          <ul className="space-y-1 text-sm">
            <li className="flex gap-2">
              <Check className="size-4 text-success" aria-hidden /> Stop accessing {p.name}
            </li>
            <li className="flex gap-2">
              <Check className="size-4 text-success" aria-hidden /> Stop future synchronization
            </li>
            <li className="flex gap-2">
              <Check className="size-4 text-success" aria-hidden /> Remove the active connection and its credentials
            </li>
          </ul>
          <p className="text-sm text-muted-foreground">Your existing {p.name} data will remain in {p.name}.</p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDisconnectStep(0)}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={() => setDisconnectStep(2)}>
              Disconnect
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={disconnectStep === 2} onOpenChange={(o) => !o && setDisconnectStep(0)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Remove locally stored {p.name} data?</DialogTitle>
            <DialogDescription>
              Disconnecting and deleting local data are separate. Notely has {p.local_item_count} indexed item{p.local_item_count === 1 ? "" : "s"} from {p.name}.
            </DialogDescription>
          </DialogHeader>
          <label className="flex items-start gap-3 text-sm">
            <input type="checkbox" className="mt-0.5 size-4 accent-[var(--ai)]" checked={purge} onChange={(e) => setPurge(e.target.checked)} />
            <span>
              Delete indexed {p.name} content from Notely
              <span className="block text-xs text-muted-foreground">Nothing is deleted from {p.name} itself.</span>
            </span>
          </label>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDisconnectStep(0)}>
              Cancel
            </Button>
            <Button variant="destructive" disabled={disconnect.isPending} onClick={() => conn && disconnect.mutate({ id: conn.id, purge })}>
              {disconnect.isPending ? "Disconnecting…" : purge ? "Disconnect and delete data" : "Disconnect"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
