"use client";

import { useQuery } from "@tanstack/react-query";
import { FileText, Plus, Search, Sparkles } from "lucide-react";
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
  CommandList,
  CommandSeparator,
} from "@/components/ui/command";
import { Kbd } from "@/components/ui/kbd";
import { messageFor } from "@/features/auth/components/auth-form-error";
import { notesApi } from "@/features/notes/api";
import { useCreateNote } from "@/features/notes/hooks";
import { primaryNav } from "@/lib/navigation";
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

  const notes = useQuery({
    queryKey: ["notes", "palette", q],
    queryFn: () => notesApi.list({ q: q.trim() || undefined, limit: 6 }),
    enabled: open,
    staleTime: 10_000,
    retry: false,
  });

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
        <CommandInput placeholder="Search notes, or type a command…" value={q} onValueChange={setQ} loading={notes.isFetching} />
        <CommandList>
          <CommandEmpty>{notes.isFetching ? "Searching…" : "Nothing matches yet."}</CommandEmpty>
          {notes.isError ? (
            <p role="alert" className="px-3 py-2 text-xs text-destructive">
              Notes couldn’t be searched right now ({messageFor(notes.error)}). Commands still work.
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
              <Plus aria-hidden /> New note
              <span className="ml-auto hidden text-[11px] text-muted-foreground sm:inline">Action</span>
            </CommandItem>
            {q.trim() ? (
              <CommandItem value={`search ${q}`} onSelect={() => go(`/app/search?q=${encodeURIComponent(q.trim())}`)}>
                <Search aria-hidden /> Search everything for “{q.trim()}”
              </CommandItem>
            ) : null}
          </CommandGroup>
          {notes.data?.notes.length ? (
            <>
              <CommandSeparator />
              <CommandGroup heading="Notes">
                {notes.data.notes.map((n) => (
                  <CommandItem key={n.id} value={`note ${n.title || "Untitled"} ${n.excerpt ?? ""} ${n.id}`} onSelect={() => go(`/app/notes/${n.id}`)} className="h-11">
                    <FileText aria-hidden />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate">{n.title || "Untitled"}</span>
                      {n.excerpt ? <span className="block truncate text-xs text-muted-foreground">{n.excerpt}</span> : null}
                    </span>
                    <span className="hidden text-[11px] text-muted-foreground sm:inline">Note</span>
                  </CommandItem>
                ))}
              </CommandGroup>
            </>
          ) : null}
          <CommandSeparator />
          <CommandGroup heading="Go to">
            {primaryNav.map((item) => (
              <CommandItem key={item.href} value={`go ${item.label}`} onSelect={() => go(item.href)}>
                <item.icon aria-hidden /> {item.label}
                <span className="ml-auto hidden text-[11px] text-muted-foreground sm:inline">Go to</span>
              </CommandItem>
            ))}
          </CommandGroup>
        </CommandList>
        <CommandFooter>
          <span className="inline-flex items-center gap-1.5">
            <Kbd>↑</Kbd>
            <Kbd>↓</Kbd> navigate
          </span>
          <span className="inline-flex items-center gap-1.5">
            <Kbd>↵</Kbd> open
          </span>
          <span className="inline-flex items-center gap-1.5">
            <Kbd>esc</Kbd> close
          </span>
          <span className="ml-auto hidden items-center gap-1.5 sm:inline-flex">
            <Sparkles className="size-3 text-ai" aria-hidden /> Notely
          </span>
        </CommandFooter>
      </CommandDialog>
    </>
  );
}
