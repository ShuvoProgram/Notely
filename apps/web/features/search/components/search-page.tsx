"use client";

import { AlertTriangle, Bug, CheckSquare, ExternalLink, File, FileText, Folder, Mail, MessageSquare, Search as SearchIcon } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import * as React from "react";

import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { messageFor } from "@/features/auth/components/auth-form-error";
import { useSearch } from "@/features/notes/hooks";

export const SOURCE_LABELS: Record<string, string> = {
  notely: "Notely",
  slack: "Slack",
  notion: "Notion",
  todoist: "Todoist",
  asana: "Asana",
  jira: "Jira",
  microsoft_teams: "Teams",
  outlook: "Outlook",
  dropbox: "Dropbox",
  mcp_server: "MCP server",
};

const KIND_ICON: Record<string, typeof FileText> = {
  note: FileText,
  page: FileText,
  message: MessageSquare,
  email: Mail,
  task: CheckSquare,
  issue: Bug,
  file: File,
  folder: Folder,
};

export function SearchPage() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const initial = params.get("q") ?? "";
  const [value, setValue] = React.useState(initial);
  const [query, setQuery] = React.useState(initial);

  React.useEffect(() => {
    const t = setTimeout(() => {
      const trimmed = value.trim();
      setQuery(trimmed);
      const next = new URLSearchParams(params.toString());
      if (trimmed) next.set("q", trimmed);
      else next.delete("q");
      const qs = next.toString();
      router.replace(qs ? `${pathname}?${qs}` : pathname);
    }, 300);
    return () => clearTimeout(t);
  }, [value]); // eslint-disable-line react-hooks/exhaustive-deps

  const search = useSearch(query);
  const hits = search.data?.hits ?? [];

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Search</h1>
        <p className="mt-1 text-sm text-muted-foreground">Search your notes and every app you have connected. Results always say where they came from.</p>
      </div>
      <div className="relative">
        <SearchIcon className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
        <Input
          aria-label="Search"
          placeholder="Search everything…"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          autoFocus
          className="h-11 pl-9 text-base"
        />
      </div>

      {query && search.isPending ? (
        <div className="space-y-3" aria-busy>
          <Skeleton className="h-16 w-full" />
          <Skeleton className="h-16 w-full" />
        </div>
      ) : search.error ? (
        <p role="alert" className="text-sm text-destructive">
          {messageFor(search.error)}
        </p>
      ) : query && hits.length === 0 ? (
        <p className="text-sm text-muted-foreground">No results for “{query}”.</p>
      ) : hits.length ? (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground" aria-live="polite">
            <span>
              {hits.length} result{hits.length === 1 ? "" : "s"} · Sources:
            </span>
            {(search.data?.sources ?? []).map((s) => (
              <Badge key={s.source} variant={s.ok ? "outline" : "destructive"} className="gap-1 font-normal" title={s.error ?? undefined}>
                {!s.ok ? <AlertTriangle className="size-3" aria-hidden /> : null}
                {SOURCE_LABELS[s.source] ?? s.source} {s.ok ? s.count : "unavailable"}
              </Badge>
            ))}
          </div>
          <ul className="divide-y rounded-xl border bg-card">
            {hits.map((hit) => {
              const Icon = KIND_ICON[hit.kind] ?? FileText;
              const external = hit.source !== "notely";
              const inner = (
                <>
                  <Icon className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <p className="truncate text-sm font-medium">{hit.title}</p>
                      <Badge variant="secondary" className="font-normal">
                        {SOURCE_LABELS[hit.source] ?? hit.source}
                      </Badge>
                      {external && hit.url ? <ExternalLink className="size-3 text-muted-foreground" aria-hidden /> : null}
                    </div>
                    <p className="mt-0.5 line-clamp-2 text-xs text-muted-foreground">{hit.snippet || "No preview"}</p>
                  </div>
                </>
              );
              const cls = "flex gap-3 px-4 py-3 outline-none hover:bg-accent/60 focus-visible:ring-2 focus-visible:ring-ring";
              return (
                <li key={`${hit.source}:${hit.id}`}>
                  {!hit.url ? (
                    <div className={cls}>{inner}</div>
                  ) : external ? (
                    <a href={hit.url} target="_blank" rel="noopener noreferrer" className={cls}>
                      {inner}
                    </a>
                  ) : (
                    <Link href={hit.url} className={cls}>
                      {inner}
                    </Link>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
