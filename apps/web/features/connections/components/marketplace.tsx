"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, LayoutGrid, Plug, Search, Sparkles } from "@/components/icons";
import { toast } from "sonner";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";

import { EmptyState } from "@/components/layout/empty-state";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { messageFor } from "@/features/auth/components/auth-form-error";
import { connectionsApi } from "@/features/connections/api";
import { ConnectDialog } from "@/features/connections/components/connect-dialog";
import { ACTION_LABEL, ConnectionStatusBadge, describeConnection, isUnfinished } from "@/features/connections/components/connection-status";
import type { ConnectMethod, Provider } from "@/lib/api/types";
import { cn } from "@/lib/utils";

export const CATEGORY_LABELS: Record<string, string> = {
  communication: "Communication",
  email_calendar: "Email & Calendar",
  meetings: "Meetings",
  documents: "Documents & Spreadsheets",
  notes: "Notes & Knowledge",
  tasks: "Tasks & Productivity",
  project_management: "Project management",
  storage: "Cloud storage",
  payments: "Payments",
  crm: "CRM",
  developer: "Developer tools",
  automation: "Automation",
  design: "Design",
};

export const CATEGORY_ORDER = Object.keys(CATEGORY_LABELS);

export const CAPABILITY_LABELS: Record<string, string> = {
  search: "Search",
  read: "Read",
  write: "Create & update",
  schedule: "Schedule",
  send: "Send",
  sync: "Sync",
};

/** The one-line "what kind of thing is this" under the name: sharper than the category alone. */
export function providerTagline(p: Pick<Provider, "id" | "category">): string {
  if (/calendar/.test(p.id)) return "Calendar & scheduling";
  if (/meet|zoom/.test(p.id)) return "Video meetings";
  if (/sheets/.test(p.id)) return "Spreadsheets";
  if (/docs/.test(p.id)) return "Documents";
  if (/gmail|outlook/.test(p.id)) return "Email & messaging";
  if (/drive|dropbox|onedrive/.test(p.id)) return "Files & documents";
  if (/slack|teams/.test(p.id)) return "Team communication";
  if (p.id === "mcp_server") return "Any MCP server";
  return CATEGORY_LABELS[p.category] ?? p.category;
}

export function ProviderLogo({ provider, size = "md", className }: { provider: Pick<Provider, "name" | "logo_url">; size?: "sm" | "md" | "lg"; className?: string }) {
  const [loaded, setLoaded] = React.useState(false);
  const dims = size === "lg" ? "size-14 rounded-2xl text-xl" : size === "sm" ? "size-8 rounded-lg text-sm" : "size-11 rounded-xl text-base";
  const pad = size === "lg" ? "p-3" : size === "sm" ? "p-1.5" : "p-2.5";
  // The initial sits underneath and the vendor logo covers it once it has loaded, so a slow or
  // blocked CDN never leaves an empty tile.
  return (
    <div className={cn("relative grid shrink-0 place-items-center overflow-hidden bg-white/95 text-neutral-700 ring-1 ring-black/10 shadow-1", dims, className)} aria-hidden>
      <span className={cn("font-semibold transition-opacity", loaded && "opacity-0")}>{provider.name.slice(0, 1).toUpperCase()}</span>
      {provider.logo_url ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={provider.logo_url} alt="" loading="lazy" onLoad={() => setLoaded(true)} className={cn("absolute inset-0 size-full object-contain transition-opacity", pad, loaded ? "opacity-100" : "opacity-0")} />
      ) : null}
    </div>
  );
}

export function Marketplace() {
  const router = useRouter();
  const providers = useQuery({ queryKey: ["integrations", "providers"], queryFn: connectionsApi.providers });
  const [category, setCategory] = React.useState<string>("all");
  const [q, setQ] = React.useState("");
  const [connecting, setConnecting] = React.useState<{ provider: Provider; method: ConnectMethod } | null>(null);

  if (providers.isPending) {
    return (
      <div className="grid gap-6 lg:grid-cols-[220px_1fr]">
        <div className="hidden space-y-2 lg:block" aria-hidden>
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-9 w-full rounded-xl" />
          ))}
        </div>
        <div className="grid grid-cols-[repeat(auto-fill,minmax(17rem,1fr))] gap-3" aria-busy>
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-44 w-full rounded-2xl" />
          ))}
        </div>
      </div>
    );
  }
  if (providers.error) {
    return (
      <p role="alert" className="text-sm text-destructive">
        {messageFor(providers.error)}
      </p>
    );
  }

  const all = providers.data ?? [];
  const connected = all.filter((p) => p.connection && p.connection.status !== "disconnected" && !isUnfinished(p.connection));
  const categories = CATEGORY_ORDER.filter((c) => all.some((p) => p.category === c));
  const needle = q.trim().toLowerCase();
  const visible = all.filter(
    (p) =>
      (category === "all" || (category === "connected" ? connected.includes(p) : p.category === category)) &&
      (!needle || p.name.toLowerCase().includes(needle) || p.description.toLowerCase().includes(needle)),
  );
  const groups = new Map<string, Provider[]>();
  for (const p of visible) groups.set(p.category, [...(groups.get(p.category) ?? []), p]);
  const ordered = [...groups.entries()].sort(([a], [b]) => CATEGORY_ORDER.indexOf(a) - CATEGORY_ORDER.indexOf(b));

  const rail: { id: string; label: string; count: number; icon?: React.ElementType }[] = [
    { id: "all", label: "All apps", count: all.length, icon: LayoutGrid },
    ...(connected.length ? [{ id: "connected", label: "Connected", count: connected.length, icon: Check }] : []),
    ...categories.map((c) => ({ id: c, label: CATEGORY_LABELS[c] ?? c, count: all.filter((p) => p.category === c).length })),
  ];

  return (
    <div className="grid min-w-0 grid-cols-1 gap-6 lg:grid-cols-[220px_minmax(0,1fr)]">
      <nav aria-label="Categories" className="min-w-0 lg:sticky lg:top-2 lg:self-start">
        <ul className="scrollbar-thin -mx-4 flex gap-1 overflow-x-auto px-4 pb-1 lg:mx-0 lg:flex-col lg:overflow-visible lg:px-0">
          {rail.map((item) => {
            const active = category === item.id;
            const Icon = item.icon;
            return (
              <li key={item.id} className="shrink-0">
                <button
                  type="button"
                  aria-pressed={active}
                  onClick={() => setCategory(item.id)}
                  className={cn(
                    "flex w-full items-center gap-2 rounded-xl px-3 py-2 text-sm outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring",
                    active ? "liquid-selected font-medium text-foreground" : "text-muted-foreground hover:bg-muted/60 hover:text-foreground",
                  )}
                >
                  {Icon ? <Icon className="size-4" aria-hidden /> : null}
                  <span className="truncate">{item.label}</span>
                  <span className={cn("ml-auto hidden text-xs tabular-nums lg:inline", active ? "text-foreground" : "text-tertiary")}>{item.count}</span>
                </button>
              </li>
            );
          })}
        </ul>
      </nav>

      <div className="min-w-0 space-y-8">
        <div className="relative">
          <Search className="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
          <Input aria-label="Search apps" placeholder="Search apps (e.g. Gmail, Notion, Jira…)" value={q} onChange={(e) => setQ(e.target.value)} className="h-10 rounded-full bg-muted/40 pl-10" />
        </div>

        {!all.length ? (
          <EmptyState icon={Plug} title="No integrations available yet" description="This deployment has no vendor apps configured. Ask your administrator." />
        ) : !visible.length ? (
          <EmptyState icon={Search} title="No apps match" description="Try another name, or clear the search." action={<Button variant="outline" size="sm" onClick={() => setQ("")}>Clear search</Button>} />
        ) : (
          ordered.map(([cat, list]) => (
            <section key={cat} aria-labelledby={`cat-${cat}`} className="space-y-3">
              <h2 id={`cat-${cat}`} className="text-sm font-semibold">
                {CATEGORY_LABELS[cat] ?? cat}
              </h2>
              <ul className="grid min-w-0 grid-cols-[repeat(auto-fill,minmax(17rem,1fr))] gap-3">
                {list.map((p) => (
                  <ProviderCard
                    key={p.id}
                    provider={p}
                    onOpen={() => router.push(`/app/settings/connections/${p.id}`)}
                    onConnect={() => setConnecting({ provider: p, method: p.connect_methods.includes("oauth") ? "oauth" : "mcp" })}
                  />
                ))}
              </ul>
            </section>
          ))
        )}
      </div>

      {connecting ? (
        <ConnectDialog key={connecting.provider.id} provider={connecting.provider} method={connecting.method} open onOpenChange={(o) => !o && setConnecting(null)} />
      ) : null}
    </div>
  );
}

function ProviderCard({ provider, onOpen, onConnect }: { provider: Provider; onOpen: () => void; onConnect: () => void }) {
  const queryClient = useQueryClient();
  const conn = provider.connection && provider.connection.status !== "disconnected" ? provider.connection : null;
  const available = provider.connect_methods.length > 0;
  // "Try again" and "Reconnect" both start with the server-side health check, which redeems
  // the refresh token if it can. Only when that genuinely fails does Reconnect open OAuth —
  // so a connection that merely had a stale access token never sends the user to a consent
  // screen.
  const retry = useMutation({
    mutationFn: ({ id }: { id: string; thenOAuth: boolean }) => connectionsApi.test(id),
    onSuccess: (r, { thenOAuth }) => {
      queryClient.invalidateQueries({ queryKey: ["integrations"] });
      if (r.healthy) toast.success(`${provider.name} is connected again`);
      else if (thenOAuth) onConnect();
    },
    onError: (e, { thenOAuth }) => (thenOAuth ? onConnect() : toast.error(messageFor(e))),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["integrations"] }),
  });
  const view = describeConnection(conn, provider.name, { available, refreshing: retry.isPending });
  const act = () => {
    if (view.action === "connect") onConnect();
    else if (view.action === "reconnect" && conn) retry.mutate({ id: conn.id, thenOAuth: true });
    else if (view.action === "retry" && conn) retry.mutate({ id: conn.id, thenOAuth: false });
    else onOpen();
  };
  const caps = provider.capabilities;
  const shown = caps.slice(0, 4);

  return (
    <li className="min-w-0">
      <article
        data-state={view.state}
        className={cn(
          "glass lift group relative flex h-full min-w-0 flex-col rounded-2xl p-4",
          view.state === "attention" ? "border-warning/40" : view.state === "error" ? "border-destructive/40" : "border-glass-border",
        )}
      >
        <Link href={`/app/settings/connections/${provider.id}`} className="absolute inset-0 rounded-2xl outline-none focus-visible:ring-2 focus-visible:ring-ring" aria-label={`${provider.name} details`} />

        <header className="flex items-center gap-3">
          <ProviderLogo provider={provider} />
          <div className="min-w-0 flex-1">
            <h3 className="truncate text-[15px] font-semibold leading-tight" title={provider.name}>
              {provider.name}
            </h3>
            <p className="mt-0.5 flex items-center gap-1.5 truncate text-xs text-muted-foreground">
              {providerTagline(provider)}
              {provider.mcp_server_url ? (
                <span className="inline-flex items-center gap-0.5 text-ai" title="Connects through the vendor's official MCP server">
                  <Sparkles className="size-3" aria-hidden /> Official
                </span>
              ) : null}
            </p>
          </div>
        </header>

        <p className="mt-3 line-clamp-2 min-h-[2.5rem] text-xs leading-5 text-muted-foreground">{provider.description}</p>

        <ul className="mt-3 flex flex-1 flex-wrap content-start gap-1.5" aria-label="Capabilities">
          {shown.map((c) => (
            <li key={c} className="rounded-md bg-muted/60 px-2 py-0.5 text-[11px] font-medium text-muted-foreground">
              {CAPABILITY_LABELS[c] ?? c.charAt(0).toUpperCase() + c.slice(1)}
            </li>
          ))}
          {caps.length > shown.length ? <li className="px-1 py-0.5 text-[11px] text-muted-foreground">+{caps.length - shown.length}</li> : null}
        </ul>

        <footer className="relative z-10 mt-4 flex items-end justify-between gap-3 border-t border-glass-border pt-3">
          <ConnectionStatusBadge view={view} compact className="min-w-0 flex-1" />
          {view.action ? (
            <Button size="sm" variant={view.action === "connect" || view.action === "reconnect" ? "default" : "outline"} onClick={act} disabled={retry.isPending} className="shrink-0 rounded-full">
              {ACTION_LABEL[view.action]}
            </Button>
          ) : null}
        </footer>
      </article>
    </li>
  );
}
