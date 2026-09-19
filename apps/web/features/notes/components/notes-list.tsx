"use client";

import { Plus, Search, Star } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { messageFor } from "@/features/auth/components/auth-form-error";
import { TagChip } from "@/features/notes/components/tag-picker";
import { useCreateNote, useFolders, useNotesList, useTags } from "@/features/notes/hooks";
import type { NoteSummary, NoteView } from "@/lib/api/types";
import { cn } from "@/lib/utils";

const VIEWS: { value: NoteView; label: string }[] = [
  { value: "active", label: "Notes" },
  { value: "favorites", label: "Favorites" },
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

function relative(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.round(diff / 60_000);
  if (m < 1) return "now";
  if (m < 60) return `${m}m`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h}h`;
  const d = Math.round(h / 24);
  return d < 7 ? `${d}d` : new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function NoteRow({ note, active }: { note: NoteSummary; active: boolean }) {
  return (
    <li>
      <Link
        href={`/app/notes/${note.id}`}
        aria-current={active ? "page" : undefined}
        className={cn(
          "block rounded-lg px-3 py-2.5 outline-none transition-colors hover:bg-accent/60 focus-visible:ring-2 focus-visible:ring-ring",
          active && "bg-accent",
        )}
      >
        <div className="flex items-start gap-2">
          <p className="min-w-0 flex-1 truncate text-sm font-medium">{note.title || "Untitled"}</p>
          {note.is_favorite ? <Star className="mt-0.5 size-3.5 shrink-0 fill-warning text-warning" aria-label="Favorite" /> : null}
          <time className="shrink-0 text-xs text-muted-foreground" dateTime={note.updated_at}>
            {relative(note.updated_at)}
          </time>
        </div>
        <p className="mt-0.5 line-clamp-2 text-xs text-muted-foreground">{note.excerpt || "No additional text"}</p>
        {note.tags.length ? (
          <div className="mt-1.5 flex flex-wrap gap-1">
            {note.tags.slice(0, 3).map((t) => (
              <TagChip key={t.id} tag={t} />
            ))}
            {note.tags.length > 3 ? <span className="text-[11px] text-muted-foreground">+{note.tags.length - 3}</span> : null}
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
      <div className="flex items-center gap-2 px-3 pt-3">
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
          <Input aria-label="Filter notes" placeholder="Filter notes…" value={q} onChange={(e) => setQ(e.target.value)} className="h-9 pl-8" />
        </div>
        <Button size="icon" aria-label="New note" onClick={onCreate} disabled={create.isPending}>
          <Plus aria-hidden />
        </Button>
      </div>
      <div className="px-3 pt-2">
        <Tabs value={view} onValueChange={(v) => setParam("view", v === "active" ? undefined : v)}>
          <TabsList className="w-full">
            {VIEWS.map((v) => (
              <TabsTrigger key={v.value} value={v.value} className="flex-1 text-xs">
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

      <div className="mt-2 flex-1 overflow-y-auto px-2 pb-3">
        {list.isPending ? (
          <div className="space-y-2 p-1" aria-busy>
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-14 w-full" />
            ))}
          </div>
        ) : list.error ? (
          <p role="alert" className="p-3 text-sm text-destructive">
            {messageFor(list.error)}
          </p>
        ) : notes.length === 0 ? (
          <div className="p-6 text-center">
            <p className="text-sm font-medium">{debouncedQ ? "No matching notes" : view === "trash" ? "Trash is empty" : "No notes here yet"}</p>
            {!debouncedQ && view === "active" ? (
              <Button variant="outline" size="sm" className="mt-3" onClick={onCreate} disabled={create.isPending}>
                <Plus aria-hidden /> Create your first note
              </Button>
            ) : null}
          </div>
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
