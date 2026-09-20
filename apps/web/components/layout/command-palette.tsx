"use client";

import { useQuery } from "@tanstack/react-query";
import { FileText, Plus, Search } from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  CommandDialog,
  CommandEmpty,
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
      <CommandDialog open={open} onOpenChange={setOpen} title="Search and commands" description="Jump to a page, create a note, or open one by title" className="glass-3">
        <CommandInput placeholder="Type a command or search notes…" value={q} onValueChange={setQ} />
        <CommandList className="max-h-[60vh]">
          <CommandEmpty>Nothing matches yet.</CommandEmpty>
          <CommandGroup heading="Actions">
            <CommandItem
              value="new note"
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
                  <CommandItem key={n.id} value={`note ${n.title || "Untitled"} ${n.id}`} onSelect={() => go(`/app/notes/${n.id}`)}>
                    <FileText aria-hidden />
                    <span className="truncate">{n.title || "Untitled"}</span>
                    {n.excerpt ? <span className="ml-auto max-w-[40%] truncate text-xs text-muted-foreground">{n.excerpt}</span> : null}
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
              </CommandItem>
            ))}
          </CommandGroup>
        </CommandList>
      </CommandDialog>
    </>
  );
}
