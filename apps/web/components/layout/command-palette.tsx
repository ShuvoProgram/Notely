"use client";

import { useQuery } from "@tanstack/react-query";
import { ExternalLink, FileText, Plus, Search, Sparkles } from "@/components/icons";
import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  CommandDialog,
  CommandEmpty,
  CommandFooter,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandItemMeta,
  CommandItemText,
  CommandList,
  CommandSeparator,
} from "@/components/ui/command";
import { Kbd } from "@/components/ui/kbd";
import { messageFor } from "@/features/auth/components/auth-form-error";
import { notesApi, searchApi } from "@/features/notes/api";
import { useCreateNote } from "@/features/notes/hooks";
import { primaryNav } from "@/lib/navigation";
import { PROVIDER_LABELS } from "@/lib/providers";
import { cn } from "@/lib/utils";

/**
 * ⌘K palette: jump anywhere, create a note, or open a note by title. The trigger doubles as the
 * top-bar search field so there is one obvious place to "ask for anything".
 */
export function CommandPalette({ className }: { className?: string }) {
  const [open, setOpen] = React.useState(false);
  const [q, setQ] = React.useState("");
  const router = useRouter();
  const create = useCreateNote();

  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((o) => !o);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // No query: recent notes. With a query: full-text search (stemmed, ranked) across notes and
  // connected tools, so the palette is the one search box.
  const searching = q.trim().length >= 2;
  const notes = useQuery({
    queryKey: ["notes", "palette", "recent"],
    queryFn: () => notesApi.list({ limit: 6 }),
    enabled: open && !searching,
    staleTime: 10_000,
    retry: false,
  });

  // Cross-app search (connected tools too) once there is a real query.
  const everything = useQuery({
    queryKey: ["search", "palette", q.trim()],
    queryFn: () => searchApi.search(q.trim(), 12),
    enabled: open && searching,
    staleTime: 15_000,
    retry: false,
  });
  const hits = everything.data?.hits ?? [];
  const external = hits.filter((h) => h.source !== "notely");
  const noteRows = searching
    ? hits
        .filter((h) => h.source === "notely" && h.url)
        .map((h) => ({ id: h.id, title: h.title, excerpt: h.snippet, href: h.url as string }))
    : (notes.data?.notes ?? []).map((n) => ({ id: n.id, title: n.title, excerpt: n.excerpt, href: `/app/notes/${n.id}` }));
  const busy = notes.isFetching || everything.isFetching;
  const failed = searching ? everything.isError : notes.isError;
  const failure = searching ? everything.error : notes.error;

  const go = (href: string) => {
    setOpen(false);
    router.push(href);
  };

  return (
    <>
      <Button
        type="button"
        variant="outline"
        onClick={() => setOpen(true)}
        aria-label="Open command palette"
        className={cn(
          "hidden h-9 w-full max-w-md justify-start gap-2 rounded-full bg-muted/40 px-3 font-normal text-muted-foreground shadow-none hover:bg-muted/70 sm:flex dark:bg-muted/40",
          className,
        )}
      >
        <Search className="size-4" aria-hidden />
        <span className="flex-1 truncate text-left">Search notes, ask anything…</span>
        <Kbd>⌘K</Kbd>
      </Button>
      <Button type="button" variant="ghost" size="icon" onClick={() => setOpen(true)} aria-label="Open command palette" className="sm:hidden">
        <Search aria-hidden />
      </Button>
      <CommandDialog open={open} onOpenChange={setOpen} title="Search and commands" description="Jump to a page, create a note, or open one by title">
        <CommandInput placeholder="Search notes, or type a command…" value={q} onValueChange={setQ} loading={busy} />
        <CommandList>
          <CommandEmpty>{busy ? "Searching…" : "Nothing matches yet."}</CommandEmpty>
          {failed ? (
            <p role="alert" className="px-3 py-2 text-xs text-destructive">
              Notes couldn’t be searched right now ({messageFor(failure)}). Commands still work.
            </p>
          ) : null}
          <CommandGroup heading="Actions">
            <CommandItem
              value="new note create"
              onSelect={() =>
                create.mutate(
                  {},
                  {
                    onSuccess: (n) => go(`/app/notes/${n.id}`),
                    onError: (e) => toast.error(messageFor(e)),
                  },
                )
              }
            >
              <Plus aria-hidden />
              <CommandItemText title="New note" />
              <CommandItemMeta>Action</CommandItemMeta>
            </CommandItem>

          </CommandGroup>
          {noteRows.length ? (
            <>
              <CommandSeparator />
              <CommandGroup heading={searching ? "Notes" : "Recent notes"}>
                {noteRows.map((n) => (
                  <CommandItem key={n.id} value={`note ${n.title || "Untitled"} ${n.excerpt ?? ""} ${n.id}`} onSelect={() => go(n.href)}>
                    <FileText aria-hidden />
                    <CommandItemText title={n.title || "Untitled"} description={n.excerpt || undefined} />
                    <CommandItemMeta>Note</CommandItemMeta>
                  </CommandItem>
                ))}
              </CommandGroup>
            </>
          ) : null}
          {external.length ? (
            <>
              <CommandSeparator />
              <CommandGroup heading="From your tools">
                {external.map((h) => (
                  <CommandItem
                    key={`${h.source}-${h.id}`}
                    value={`ext ${h.title} ${h.snippet ?? ""} ${h.id}`}
                    onSelect={() => {
                      if (h.url) window.open(h.url, "_blank", "noopener,noreferrer");
                      setOpen(false);
                    }}
                  >
                    <ExternalLink aria-hidden />
                    <CommandItemText title={h.title} description={h.snippet ?? undefined} />
                    <CommandItemMeta>{PROVIDER_LABELS[h.source] ?? h.source}</CommandItemMeta>
                  </CommandItem>
                ))}
              </CommandGroup>
            </>
          ) : null}
          <CommandSeparator />
          <CommandGroup heading="Go to">
            {primaryNav.map((item) => (
              <CommandItem key={item.href} value={`go ${item.label}`} onSelect={() => go(item.href)}>
                <item.icon aria-hidden />
                <CommandItemText title={item.label} />
                <CommandItemMeta>Go to</CommandItemMeta>
              </CommandItem>
            ))}
          </CommandGroup>
        </CommandList>
        <CommandFooter>
          <span className="inline-flex items-center gap-1">
            <Kbd>↑</Kbd>
            <Kbd>↓</Kbd>
            <span className="ml-0.5">navigate</span>
          </span>
          <span className="inline-flex items-center gap-1">
            <Kbd>↵</Kbd>
            <span className="ml-0.5">open</span>
          </span>
          <span className="inline-flex items-center gap-1">
            <Kbd>esc</Kbd>
            <span className="ml-0.5">close</span>
          </span>
          <span className="ml-auto hidden items-center gap-1 sm:inline-flex">
            <Sparkles className="size-3 text-ai" aria-hidden /> Notely
          </span>
        </CommandFooter>
      </CommandDialog>
    </>
  );
}
