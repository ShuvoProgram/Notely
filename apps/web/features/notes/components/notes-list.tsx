"use client";

import { Bell, Inbox, ListChecks, Plus, Search, Star, Users } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { EmptyState } from "@/components/layout/empty-state";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { messageFor } from "@/features/auth/components/auth-form-error";
import { TagChip } from "@/features/notes/components/tag-picker";
import { editedLabel, reminderLabel } from "@/features/notes/lib";
import { useCreateNote, useFolders, useNotesList, useTags } from "@/features/notes/hooks";
import type { NoteSummary, NoteView } from "@/lib/api/types";
import { cn } from "@/lib/utils";

const VIEWS: { value: NoteView; label: string }[] = [
  { value: "active", label: "Notes" },
  { value: "favorites", label: "Favorites" },
  { value: "shared", label: "Shared" },
  { value: "archived", label: "Archived" },
  { value: "trash", label: "Trash" },
];

export function useNoteListFilters() {
  const params = useSearchParams();
  const view = (params.get("view") as NoteView | null) ?? "active";
  const folderId = params.get("folder") ?? undefined;
  const tagId = params.get("tag") ?? undefined;
  return { view: VIEWS.some((v) => v.value === view) ? view : "active", folderId, tagId };
}

function NoteRow({ note, active }: { note: NoteSummary; active: boolean }) {
  // A summary from an older API or a partial cache patch may lack tags; never crash the list.
  const tags = note.tags ?? [];
  const reminder = note.reminder_at ? reminderLabel(note.reminder_at) : null;
  const checklist = note.checklist && note.checklist.total > 0 ? note.checklist : null;
  const tinted = note.color && note.color !== "default";
  return (
    <li>
      <Link
        href={`/app/notes/${note.id}`}
        aria-current={active ? "page" : undefined}
        className={cn(
          "relative block rounded-xl px-3 py-2.5 outline-none transition-colors duration-150 hover:bg-accent/50 focus-visible:ring-2 focus-visible:ring-ring",
          active && "bg-accent/80 shadow-1 ring-1 ring-glass-border",
        )}
      >
        <span aria-hidden className={cn("absolute left-0 top-1/2 h-5 w-0.5 -translate-y-1/2 rounded-full bg-ai transition-opacity", active ? "opacity-100" : "opacity-0")} />
        <div className="flex items-start gap-2">
          {tinted ? <span aria-hidden data-note-color={note.color} className="mt-1.5 size-2 shrink-0 rounded-full bg-[var(--note-tint-strong)]" /> : null}
          <p className="min-w-0 flex-1 truncate text-sm font-medium">{note.title || "Untitled"}</p>
          {note.is_favorite ? <Star className="mt-0.5 size-3.5 shrink-0 fill-warning text-warning" aria-label="Favorite" /> : null}
          <time className="shrink-0 text-[11px] text-muted-foreground" dateTime={note.updated_at} title={new Date(note.updated_at).toLocaleString()}>
            {editedLabel(note.updated_at)}
          </time>
        </div>
        <p className="mt-0.5 line-clamp-2 text-xs text-muted-foreground">{note.excerpt || "No additional text"}</p>
        {tags.length || reminder || checklist || note.shared ? (
          <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-muted-foreground">
            {reminder ? (
              <span className={cn("inline-flex items-center gap-1", !reminder.passed && "text-ai")}>
                <Bell className="size-3" aria-hidden />
                {reminder.passed ? "Passed" : reminder.text}
              </span>
            ) : null}
            {checklist ? (
              <span className={cn("inline-flex items-center gap-1", checklist.done === checklist.total && "text-success")} aria-label={`${checklist.done} of ${checklist.total} done`}>
                <ListChecks className="size-3" aria-hidden />
                {checklist.done}/{checklist.total}
              </span>
            ) : null}
            {note.shared ? (
              <span className="inline-flex items-center gap-1" aria-label="Shared">
                <Users className="size-3" aria-hidden />
                {note.access === "owner" ? "Shared" : "Shared with you"}
              </span>
            ) : null}
            {tags.slice(0, 3).map((t) => (
              <TagChip key={t.id} tag={t} />
            ))}
            {tags.length > 3 ? <span>+{tags.length - 3}</span> : null}
          </div>
        ) : null}
      </Link>
    </li>
  );
}

export function NotesList({ activeNoteId }: { activeNoteId?: string }) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const { view, folderId, tagId } = useNoteListFilters();
  const [q, setQ] = React.useState("");
  const [debouncedQ, setDebouncedQ] = React.useState("");
  React.useEffect(() => {
    const t = setTimeout(() => setDebouncedQ(q.trim()), 250);
    return () => clearTimeout(t);
  }, [q]);

  const list = useNotesList({ view, folder_id: folderId, tag_id: tagId, q: debouncedQ || undefined });
  const create = useCreateNote();
  const { data: folders = [] } = useFolders();
  const { data: tags = [] } = useTags();

  const setParam = (key: string, value?: string) => {
    const next = new URLSearchParams(params.toString());
    if (value) next.set(key, value);
    else next.delete(key);
    router.replace(`${pathname}?${next.toString()}`);
  };

  const notes = list.data?.pages.flatMap((p) => p.notes) ?? [];
  const folderName = folderId ? folders.find((f) => f.id === folderId)?.name : undefined;
  const tag = tagId ? tags.find((t) => t.id === tagId) : undefined;

  const onCreate = () =>
    create.mutate(
      { folder_id: folderId ?? null, tag_ids: tagId ? [tagId] : [] },
      { onSuccess: (n) => router.push(`/app/notes/${n.id}`), onError: (e) => toast.error(messageFor(e)) },
    );

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between px-4 pt-4">
        <h2 className="text-base font-semibold tracking-tight">Notes</h2>
        <Button size="sm" aria-label="New note" onClick={onCreate} disabled={create.isPending} className="rounded-full">
          <Plus aria-hidden /> New
        </Button>
      </div>
      <div className="px-3 pt-3">
        <div className="relative">
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
          <Input aria-label="Filter notes" placeholder="Filter notes…" value={q} onChange={(e) => setQ(e.target.value)} className="h-9 rounded-full bg-muted/40 pl-9" />
        </div>
      </div>
      <div className="px-3 pt-2">
        <Tabs value={view} onValueChange={(v) => setParam("view", v === "active" ? undefined : v)}>
          <TabsList className="w-full rounded-full">
            {VIEWS.map((v) => (
              <TabsTrigger key={v.value} value={v.value} className="flex-1 rounded-full text-xs">
                {v.label}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
      </div>
      {folderName || tag ? (
        <div className="flex items-center gap-2 px-3 pt-2 text-xs text-muted-foreground">
          <span className="truncate">
            In {folderName ? <strong className="text-foreground">{folderName}</strong> : null}
            {folderName && tag ? " · " : null}
            {tag ? <TagChip tag={tag} /> : null}
          </span>
          <button
            type="button"
            className="ml-auto underline-offset-2 hover:underline"
            onClick={() => {
              const next = new URLSearchParams(params.toString());
              next.delete("folder");
              next.delete("tag");
              router.replace(`${pathname}?${next.toString()}`);
            }}
          >
            Clear
          </button>
        </div>
      ) : null}

      <div className="scrollbar-thin mt-2 flex-1 overflow-y-auto px-2 pb-3">
        {list.isPending ? (
          <div className="space-y-1 p-1" aria-busy>
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="space-y-2 rounded-xl px-3 py-2.5">
                <Skeleton className="h-3.5 w-2/3" />
                <Skeleton className="h-3 w-full" />
              </div>
            ))}
          </div>
        ) : list.error ? (
          <p role="alert" className="p-3 text-sm text-destructive">
            {messageFor(list.error)}
          </p>
        ) : notes.length === 0 ? (
          <EmptyState
            icon={Inbox}
            className="py-8"
            title={debouncedQ ? "No matching notes" : view === "trash" ? "Trash is empty" : view === "shared" ? "Nothing shared with you yet" : "No notes here yet"}
            description={debouncedQ ? "Try a different word, or search everything from the top bar." : view === "active" ? "Your first note is one click away." : view === "shared" ? "Notes other people share with you show up here." : undefined}
            action={
              !debouncedQ && view === "active" ? (
                <Button variant="outline" size="sm" onClick={onCreate} disabled={create.isPending}>
                  <Plus aria-hidden /> Create your first note
                </Button>
              ) : undefined
            }
          />
        ) : (
          <>
            <ul className="space-y-0.5">
              {notes.map((n) => (
                <NoteRow key={n.id} note={n} active={n.id === activeNoteId} />
              ))}
            </ul>
            {list.hasNextPage ? (
              <Button variant="ghost" size="sm" className="mt-2 w-full" onClick={() => list.fetchNextPage()} disabled={list.isFetchingNextPage}>
                {list.isFetchingNextPage ? "Loading…" : "Load more"}
              </Button>
            ) : null}
          </>
        )}
      </div>
    </div>
  );
}
