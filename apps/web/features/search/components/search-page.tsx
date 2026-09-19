"use client";

import { FileText, Search as SearchIcon } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import * as React from "react";

import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { messageFor } from "@/features/auth/components/auth-form-error";
import { useSearch } from "@/features/notes/hooks";

const SOURCE_LABELS: Record<string, string> = { notely: "Notely" };

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
        <p className="mt-1 text-sm text-muted-foreground">Search across your notes. Connected apps appear here once linked.</p>
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
          <p className="text-xs text-muted-foreground" aria-live="polite">
            {hits.length} result{hits.length === 1 ? "" : "s"} · Sources:{" "}
            {(search.data?.sources ?? []).map((s) => (
              <Badge key={s} variant="outline" className="ml-1 font-normal">
                {SOURCE_LABELS[s] ?? s}
              </Badge>
            ))}
          </p>
          <ul className="divide-y rounded-xl border bg-card">
            {hits.map((hit) => (
              <li key={`${hit.source}:${hit.id}`}>
                <Link href={hit.url} className="flex gap-3 px-4 py-3 outline-none hover:bg-accent/60 focus-visible:ring-2 focus-visible:ring-ring">
                  <FileText className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <p className="truncate text-sm font-medium">{hit.title}</p>
                      <Badge variant="secondary" className="font-normal">
                        {SOURCE_LABELS[hit.source] ?? hit.source}
                      </Badge>
                    </div>
                    <p className="mt-0.5 line-clamp-2 text-xs text-muted-foreground">{hit.snippet || "No preview"}</p>
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
