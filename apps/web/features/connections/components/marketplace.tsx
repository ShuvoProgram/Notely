"use client";

import { useQuery } from "@tanstack/react-query";
import { ChevronRight, Plug } from "lucide-react";
import Link from "next/link";

import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { messageFor } from "@/features/auth/components/auth-form-error";
import { connectionsApi } from "@/features/connections/api";
import { ConnectionStatusBadge } from "@/features/connections/components/connection-status";
import type { Provider } from "@/lib/api/types";

export const CATEGORY_LABELS: Record<string, string> = {
  communication: "Communication",
  email_calendar: "Email & Calendar",
  notes: "Notes & Knowledge",
  tasks: "Tasks",
  project_management: "Project management",
  storage: "Storage",
  crm: "CRM",
  developer: "Developer",
};

export const CATEGORY_ORDER = Object.keys(CATEGORY_LABELS);

export function ProviderLogo({ provider, size = "md" }: { provider: Pick<Provider, "name" | "logo_url">; size?: "md" | "lg" }) {
  const dims = size === "lg" ? "size-12 text-lg" : "size-10 text-base";
  if (provider.logo_url) {
    // eslint-disable-next-line @next/next/no-img-element
    return <img src={provider.logo_url} alt="" className={`${dims} rounded-lg object-contain`} />;
  }
  return (
    <div className={`${dims} grid place-items-center rounded-lg bg-secondary font-semibold text-muted-foreground`} aria-hidden>
      {provider.name.slice(0, 1).toUpperCase()}
    </div>
  );
}

export function Marketplace() {
  const providers = useQuery({ queryKey: ["integrations", "providers"], queryFn: connectionsApi.providers });

  if (providers.isPending) {
    return (
      <div className="grid gap-3 sm:grid-cols-2">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-24 w-full rounded-xl" />
        ))}
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
  const groups = new Map<string, Provider[]>();
  for (const p of providers.data ?? []) {
    const list = groups.get(p.category) ?? [];
    list.push(p);
    groups.set(p.category, list);
  }
  const ordered = [...groups.entries()].sort(([a], [b]) => (CATEGORY_ORDER.indexOf(a) + 100) % 100 - ((CATEGORY_ORDER.indexOf(b) + 100) % 100));
  const connected = (providers.data ?? []).filter((p) => p.connection && p.connection.status !== "disconnected");

  return (
    <div className="space-y-8">
      {connected.length ? (
        <section aria-labelledby="connected-heading">
          <h2 id="connected-heading" className="mb-3 text-sm font-medium uppercase tracking-wide text-muted-foreground">
            Connected
          </h2>
          <ul className="grid gap-3 sm:grid-cols-2">
            {connected.map((p) => (
              <ProviderCard key={p.id} provider={p} />
            ))}
          </ul>
        </section>
      ) : null}
      {ordered.map(([category, list]) => (
        <section key={category} aria-labelledby={`cat-${category}`}>
          <h2 id={`cat-${category}`} className="mb-3 text-sm font-medium uppercase tracking-wide text-muted-foreground">
            {CATEGORY_LABELS[category] ?? category}
          </h2>
          <ul className="grid gap-3 sm:grid-cols-2">
            {list.map((p) => (
              <ProviderCard key={p.id} provider={p} />
            ))}
          </ul>
        </section>
      ))}
      {!providers.data?.length ? (
        <Card className="flex flex-col items-center p-8 text-center">
          <Plug className="size-6 text-muted-foreground" aria-hidden />
          <p className="mt-3 text-sm text-muted-foreground">No integrations are available on this deployment yet.</p>
        </Card>
      ) : null}
    </div>
  );
}

function ProviderCard({ provider }: { provider: Provider }) {
  const conn = provider.connection;
  return (
    <li>
      <Link
        href={`/app/settings/connections/${provider.id}`}
        className="flex h-full items-center gap-3 rounded-xl border bg-card p-4 outline-none transition-colors hover:bg-accent/40 focus-visible:ring-2 focus-visible:ring-ring"
      >
        <ProviderLogo provider={provider} />
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium">{provider.name}</p>
          <p className="truncate text-xs text-muted-foreground">{provider.description}</p>
          <div className="mt-2">
            {!provider.configured ? (
              <p className="text-xs text-muted-foreground">Not available on this deployment</p>
            ) : (
              <ConnectionStatusBadge status={conn?.status ?? "none"} lastChecked={conn?.last_checked_at} lastError={conn?.last_error} />
            )}
          </div>
        </div>
        <ChevronRight className="size-4 shrink-0 text-muted-foreground" aria-hidden />
      </Link>
    </li>
  );
}
