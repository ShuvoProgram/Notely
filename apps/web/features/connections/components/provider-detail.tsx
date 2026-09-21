"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ArrowLeft, Check, ExternalLink, Loader2, RefreshCw, ShieldCheck, Stethoscope, Unplug, XCircle } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { messageFor } from "@/features/auth/components/auth-form-error";
import { connectionsApi } from "@/features/connections/api";
import { ConnectDialog } from "@/features/connections/components/connect-dialog";
import { ConnectionStatusBadge, relativeTime } from "@/features/connections/components/connection-status";
import { CATEGORY_LABELS, ProviderLogo } from "@/features/connections/components/marketplace";
import { playSfx } from "@/lib/sfx/player";
import type { ConnectMethod, ConnectionTestResult } from "@/lib/api/types";
import { cn } from "@/lib/utils";

const CALLBACK_ERRORS: Record<string, string> = {
  OAUTH_STATE_INVALID: "The sign-in request expired or was tampered with. Please try again.",
  PROVIDER_AUTH_FAILED: "Authorization failed. Your access wasn't granted.",
  PROVIDER_ADMIN_APPROVAL_REQUIRED: "Your organization requires an administrator to approve this app.",
};

const CAPABILITY_COPY: Record<string, { title: string; why: string }> = {
  search: { title: "Search your content", why: "Find relevant items when you ask a question" },
  read: { title: "Read items you point to", why: "Use their content to answer and summarize" },
  write: { title: "Create and update (with approval)", why: "Draft, create or edit — you confirm every change" },
  schedule: { title: "Schedule events (with approval)", why: "Put things on your calendar when you ask" },
  send: { title: "Send messages (with approval)", why: "Email or post on your behalf after you confirm" },
  sync: { title: "Keep a local index", why: "Faster search across your connected data" },
};

export function ProviderDetail({ providerId }: { providerId: string }) {
  const router = useRouter();
  const params = useSearchParams();
  const queryClient = useQueryClient();
  const detail = useQuery({ queryKey: ["integrations", "provider", providerId], queryFn: () => connectionsApi.provider(providerId) });
  const [connectMethod, setConnectMethod] = React.useState<ConnectMethod | null>(null);
  const [disconnectOpen, setDisconnectOpen] = React.useState(false);
  const [purge, setPurge] = React.useState(false);
  const [testResult, setTestResult] = React.useState<ConnectionTestResult | null>(null);

  // Surface OAuth callback outcome once, then clean the URL.
  React.useEffect(() => {
    const error = params.get("error");
    const connected = params.get("connected");
    if (!error && !connected) return;
    if (connected) {
      playSfx("connect");
      toast.success("Connected", { description: "The assistant can use this tool from now on." });
    } else playSfx("error");
    if (error === "PROVIDER_AUTH_FAILED" && params.get("reason") === "access_denied" && /^(gmail|google_|teams|outlook|onedrive)/.test(providerId)) {
      // Google/Microsoft send the same code for "user cancelled" and "app still in testing mode
      // on the vendor console"; the server stored the full explanation on the connection.
      toast.error("Access was refused by the vendor. If you saw “Access blocked … verification process”, this deployment's app is still in testing mode — see the status below.", { duration: 12_000 });
    } else if (error) toast.error(CALLBACK_ERRORS[error] ?? "This action couldn't be completed. Review the details and try again.");
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
      playSfx(r.healthy ? "success" : "error");
      setTestResult(r);
      invalidate();
    },
    onError: (e) => {
      playSfx("error");
      toast.error(messageFor(e));
    },
  });
  const disconnect = useMutation({
    mutationFn: ({ id, purge }: { id: string; purge: boolean }) => connectionsApi.disconnect(id, purge),
    onSuccess: () => {
      playSfx("disconnect");
      invalidate();
      setDisconnectOpen(false);
      setPurge(false);
      setTestResult(null);
      toast.success(`${detail.data?.name ?? "Integration"} disconnected`, { description: "Its credentials were removed from Notely." });
    },
    onError: (e) => toast.error(messageFor(e)),
  });

  if (detail.isPending) {
    return (
      <div className="space-y-6" aria-busy>
        <Skeleton className="h-5 w-32" />
        <Skeleton className="h-36 w-full rounded-2xl" />
        <div className="grid gap-4 md:grid-cols-2">
          <Skeleton className="h-52 rounded-2xl" />
          <Skeleton className="h-52 rounded-2xl" />
        </div>
      </div>
    );
  }
  if (detail.error || !detail.data) {
    return (
      <Alert variant="destructive">
        <XCircle />
        <AlertTitle>Couldn’t load this integration</AlertTitle>
        <AlertDescription>{messageFor(detail.error)}</AlertDescription>
      </Alert>
    );
  }
  const p = detail.data;
  const conn = p.connection && p.connection.status !== "disconnected" ? p.connection : null;
  const canOAuth = p.connect_methods.includes("oauth");
  const canMcp = p.connect_methods.includes("mcp");
  const available = canOAuth || canMcp;
  const attention = conn && (conn.status === "expired" || conn.status === "needs_attention" || conn.status === "error");
  const startConnect = () => setConnectMethod(canOAuth ? "oauth" : "mcp");

  return (
    <div className="space-y-6">
      <Link href="/app/settings/connections" className="inline-flex items-center gap-1 rounded text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="size-4" aria-hidden /> All apps
      </Link>

      {/* Hero */}
      <section className="glass rounded-2xl p-5 sm:p-6">
        <div className="flex flex-wrap items-start gap-4">
          <ProviderLogo provider={p} size="lg" />
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-2xl font-semibold tracking-tight">{p.name}</h1>
              <Badge variant="secondary" className="font-normal text-muted-foreground">
                {CATEGORY_LABELS[p.category] ?? p.category}
              </Badge>
              {conn ? (
                <Badge className={cn("font-normal", attention ? "bg-warning/15 text-warning" : "bg-success/15 text-success")}>
                  {attention ? <AlertTriangle aria-hidden /> : <Check aria-hidden />}
                  {attention ? "Needs attention" : "Connected"}
                </Badge>
              ) : null}
            </div>
            <p className="mt-1.5 max-w-2xl text-sm text-muted-foreground">{p.description}</p>
            <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
              <span className="inline-flex items-center gap-1">
                <ShieldCheck className="size-3.5 text-ai" aria-hidden /> Secure OAuth 2.0 · your credentials never touch Notely
              </span>
              {p.docs_url ? (
                <a href={p.docs_url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 underline-offset-2 hover:underline">
                  Documentation <ExternalLink className="size-3" aria-hidden />
                </a>
              ) : null}
            </div>
          </div>
          <div className="flex w-full flex-wrap gap-2 sm:w-auto">
            {!conn && available ? (
              <Button size="lg" onClick={startConnect} className="w-full rounded-full sm:w-auto">
                Connect {p.name}
              </Button>
            ) : null}
            {!conn && !available ? <p className="text-sm text-muted-foreground">{p.name} isn’t available on this deployment yet.</p> : null}
            {conn ? (
              <>
                {attention ? (
                  <Button onClick={startConnect} className="rounded-full">
                    <RefreshCw aria-hidden /> {conn.status === "expired" ? "Reconnect" : "Fix connection"}
                  </Button>
                ) : null}
                <Button variant="outline" onClick={() => test.mutate(conn.id)} disabled={test.isPending} className="rounded-full">
                  {test.isPending ? <Loader2 className="animate-spin" aria-hidden /> : <Stethoscope aria-hidden />} Test connection
                </Button>
                <Button variant="ghost" onClick={() => setDisconnectOpen(true)} className="rounded-full text-muted-foreground hover:text-destructive">
                  <Unplug aria-hidden /> Disconnect
                </Button>
              </>
            ) : null}
          </div>
        </div>
      </section>

      {conn?.last_error && attention ? (
        <Alert className="border-warning/40 bg-warning/10">
          <AlertTriangle className="text-warning" />
          <AlertTitle>{conn.status === "expired" ? "Authorization expired" : "Something needs your attention"}</AlertTitle>
          <AlertDescription className="flex flex-wrap items-center justify-between gap-3">
            <span>{conn.last_error}</span>
            <Button size="sm" onClick={startConnect}>
              {conn.status === "expired" ? "Reconnect" : "Re-authorize"}
            </Button>
          </AlertDescription>
        </Alert>
      ) : null}

      {testResult ? (
        <Alert role="status" aria-live="polite" className={testResult.healthy ? "border-success/30" : "border-warning/40 bg-warning/10"}>
          {testResult.healthy ? <Check className="text-success" /> : <AlertTriangle className="text-warning" />}
          <AlertTitle>{testResult.healthy ? "Connection healthy" : "Connection needs attention"}</AlertTitle>
          <AlertDescription>
            <ul className="mt-1 grid gap-1 sm:grid-cols-2">
              {testResult.steps.map((s) => (
                <li key={s.name} className="flex items-start gap-2">
                  {s.ok ? <Check className="mt-0.5 size-4 shrink-0 text-success" aria-hidden /> : <XCircle className="mt-0.5 size-4 shrink-0 text-destructive" aria-hidden />}
                  <span>
                    {s.name}
                    {s.detail ? <span className="ml-1.5 text-xs text-muted-foreground">{s.detail}</span> : null}
                  </span>
                </li>
              ))}
            </ul>
          </AlertDescription>
        </Alert>
      ) : null}

      <Tabs defaultValue="overview">
        <TabsList className="rounded-full">
          <TabsTrigger value="overview" className="rounded-full">
            Overview
          </TabsTrigger>
          <TabsTrigger value="permissions" className="rounded-full">
            Permissions
          </TabsTrigger>
          {conn && p.tools.length ? (
            <TabsTrigger value="tools" className="rounded-full">
              Tools <span className="ml-1 text-xs text-muted-foreground">{p.tools.length}</span>
            </TabsTrigger>
          ) : null}
        </TabsList>

        <TabsContent value="overview" className="mt-4 grid gap-4 md:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>What Notely can do</CardTitle>
              <CardDescription>Reads happen when you ask. Anything that changes data waits for your approval.</CardDescription>
            </CardHeader>
            <CardContent>
              <ul className="space-y-3">
                {p.capabilities.map((c) => {
                  const copy = CAPABILITY_COPY[c] ?? { title: c.charAt(0).toUpperCase() + c.slice(1).replace(/_/g, " "), why: "" };
                  return (
                    <li key={c} className="flex items-start gap-3">
                      <span className="mt-0.5 grid size-5 shrink-0 place-items-center rounded-md bg-ai-soft text-ai">
                        <Check className="size-3" aria-hidden />
                      </span>
                      <span>
                        <span className="block text-sm font-medium">{copy.title}</span>
                        {copy.why ? <span className="block text-xs text-muted-foreground">{copy.why}</span> : null}
                      </span>
                    </li>
                  );
                })}
              </ul>
            </CardContent>
          </Card>

          {conn ? (
            <Card>
              <CardHeader>
                <CardTitle>Connected account</CardTitle>
                <CardDescription>
                  {conn.external_account_name ?? "Account"}
                  {conn.external_account_id && conn.external_account_id !== conn.external_account_name ? ` · ${conn.external_account_id}` : ""}
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <ConnectionStatusBadge status={conn.status} lastChecked={conn.last_checked_at} lastError={conn.last_error} />
                <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-1.5 text-xs">
                  <dt className="text-muted-foreground">Connected</dt>
                  <dd>{relativeTime(conn.created_at)}</dd>
                  <dt className="text-muted-foreground">Last sync</dt>
                  <dd>{conn.last_sync_at ? relativeTime(conn.last_sync_at) : p.supports_sync ? "not yet" : "on demand"}</dd>
                  <dt className="text-muted-foreground">Indexed</dt>
                  <dd>
                    {p.local_item_count} item{p.local_item_count === 1 ? "" : "s"}
                  </dd>
                  <dt className="text-muted-foreground">Via</dt>
                  <dd>{conn.auth_type === "mcp" ? `${p.name}'s official MCP server` : "OAuth app"}</dd>
                  {Object.entries(conn.config).map(([k, v]) => (
                    <React.Fragment key={k}>
                      <dt className="capitalize text-muted-foreground">{k.replace(/_/g, " ")}</dt>
                      <dd className="truncate">{String(v)}</dd>
                    </React.Fragment>
                  ))}
                </dl>
              </CardContent>
            </Card>
          ) : (
            <Card className="border-dashed">
              <CardHeader>
                <CardTitle>You’re in control</CardTitle>
                <CardDescription>What happens when you press Connect.</CardDescription>
              </CardHeader>
              <CardContent>
                <ol className="space-y-2 text-sm">
                  {["You review what Notely will be able to do", `${p.name} asks you to sign in and approve, on its own site`, "You come back here, connected — disconnect anytime"].map((step, i) => (
                    <li key={step} className="flex gap-3">
                      <span className="grid size-5 shrink-0 place-items-center rounded-full bg-muted text-[11px] font-medium text-muted-foreground">{i + 1}</span>
                      <span>{step}</span>
                    </li>
                  ))}
                </ol>
              </CardContent>
            </Card>
          )}
        </TabsContent>

        <TabsContent value="permissions" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle>Permissions</CardTitle>
              <CardDescription>
                {conn ? "Granted permissions are ticked. Reconnect to change them." : "You choose optional permissions on the consent card before authorizing."} Notely never asks for more than a feature needs.
              </CardDescription>
            </CardHeader>
            <CardContent>
              {p.permissions.length ? (
                <ul className="divide-y divide-glass-border">
                  {p.permissions.map((perm) => {
                    const granted = conn?.scopes.includes(perm.scope) ?? false;
                    return (
                      <li key={perm.scope} className="flex items-start gap-3 py-3 first:pt-0 last:pb-0">
                        <span className={cn("mt-0.5 grid size-5 shrink-0 place-items-center rounded-md", granted ? "bg-success/15 text-success" : "bg-muted text-muted-foreground")} aria-hidden>
                          {granted ? <Check className="size-3" /> : <span className="size-1.5 rounded-full bg-current opacity-60" />}
                        </span>
                        <span className="min-w-0 flex-1">
                          <span className="flex flex-wrap items-center gap-2 text-sm font-medium">
                            {perm.label}
                            {!perm.required ? (
                              <Badge variant="outline" className="font-normal text-muted-foreground">
                                optional
                              </Badge>
                            ) : null}
                            <span className="sr-only">{granted ? "granted" : "not granted"}</span>
                          </span>
                          {perm.description ? <span className="block text-xs text-muted-foreground">{perm.description}</span> : null}
                          <code className="mt-1 block truncate font-mono text-[11px] text-muted-foreground/70">{perm.scope}</code>
                        </span>
                      </li>
                    );
                  })}
                </ul>
              ) : (
                <p className="text-sm text-muted-foreground">Permissions are defined by {p.name} during authorization.</p>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {conn && p.tools.length ? (
          <TabsContent value="tools" className="mt-4">
            <Card>
              <CardHeader>
                <CardTitle>Tools</CardTitle>
                <CardDescription>Discovered from the server. Reads run automatically; anything else asks first.</CardDescription>
              </CardHeader>
              <CardContent>
                <ul className="divide-y divide-glass-border text-sm">
                  {p.tools.map((t) => (
                    <li key={t.name} className="flex flex-wrap items-center gap-2 py-2 first:pt-0 last:pb-0">
                      <code className="rounded-md bg-muted px-1.5 py-0.5 font-mono text-xs">{t.name}</code>
                      <span className="min-w-0 flex-1 truncate text-xs text-muted-foreground">{t.description}</span>
                      <Badge variant="outline" className={cn("font-normal", t.destructive ? "text-destructive" : t.read_only ? "text-muted-foreground" : "text-warning")}>
                        {t.destructive ? "Destructive" : t.read_only ? "Read" : "Change"}
                      </Badge>
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          </TabsContent>
        ) : null}
      </Tabs>

      {connectMethod ? <ConnectDialog key={connectMethod} provider={p} method={connectMethod} open onOpenChange={(o) => !o && setConnectMethod(null)} reconnect={Boolean(conn)} /> : null}

      <Dialog
        open={disconnectOpen}
        onOpenChange={(o) => {
          setDisconnectOpen(o);
          if (!o) setPurge(false);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Disconnect {p.name}?</DialogTitle>
            <DialogDescription>This stops Notely from accessing your {p.name} account.</DialogDescription>
          </DialogHeader>
          <div className="rounded-xl bg-muted/40 p-3 ring-1 ring-glass-border">
            <p className="mb-2 text-xs font-medium text-muted-foreground">This will</p>
            <ul className="space-y-1.5 text-sm">
              <li className="flex gap-2">
                <Check className="mt-0.5 size-4 shrink-0 text-success" aria-hidden /> Revoke Notely’s access and delete the stored credentials
              </li>
              <li className="flex gap-2">
                <Check className="mt-0.5 size-4 shrink-0 text-success" aria-hidden /> Stop all future sync and assistant actions
              </li>
              <li className="flex gap-2">
                <Check className="mt-0.5 size-4 shrink-0 text-success" aria-hidden /> Leave your data in {p.name} untouched
              </li>
            </ul>
          </div>
          <label className="flex items-start gap-3 text-sm">
            <Checkbox className="mt-0.5" checked={purge} onCheckedChange={(v) => setPurge(v === true)} />
            <span>
              Also delete local data
              <span className="block text-xs text-muted-foreground">
                Remove the {p.local_item_count} {p.name} item{p.local_item_count === 1 ? "" : "s"} indexed in Notely (cannot be undone).
              </span>
            </span>
          </label>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDisconnectOpen(false)}>
              Cancel
            </Button>
            <Button variant="destructive" disabled={disconnect.isPending} onClick={() => conn && disconnect.mutate({ id: conn.id, purge })}>
              {disconnect.isPending ? <Loader2 className="animate-spin" aria-hidden /> : <Unplug aria-hidden />}
              {purge ? "Disconnect and delete data" : "Disconnect"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
