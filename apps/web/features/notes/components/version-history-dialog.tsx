"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { History, Loader2, RotateCcw } from "@/components/icons";
import * as React from "react";
import { toast } from "sonner";

import { EmptyState } from "@/components/layout/empty-state";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { messageFor } from "@/features/auth/components/auth-form-error";
import { notesApi } from "@/features/notes/api";
import { RichTextEditor } from "@/features/notes/components/rich-text-editor";
import { noteKeys } from "@/features/notes/hooks";
import type { Note } from "@/lib/api/types";
import { cn } from "@/lib/utils";

function stamp(iso: string): string {
  return new Date(iso).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

/**
 * Version history: versions on the left, a read-only preview on the right, one Restore button.
 * The server snapshots the current state before restoring, so a restore is itself undoable
 * from this same list.
 */
export function VersionHistoryDialog({ note, open, onOpenChange, onRestored }: { note: Note; open: boolean; onOpenChange: (o: boolean) => void; onRestored: (restored: Note) => void }) {
  const queryClient = useQueryClient();
  const versions = useQuery({ queryKey: ["notes", "versions", note.id], queryFn: () => notesApi.versions(note.id), enabled: open });
  const [selected, setSelected] = React.useState<string | null>(null);
  const activeId = selected ?? versions.data?.[0]?.id ?? null;
  const detail = useQuery({
    queryKey: ["notes", "versions", note.id, activeId],
    queryFn: () => notesApi.version(note.id, activeId as string),
    enabled: open && Boolean(activeId),
  });
  const restore = useMutation({
    mutationFn: (versionId: string) => notesApi.restoreVersion(note.id, versionId),
    onSuccess: (restored) => {
      queryClient.setQueryData(noteKeys.detail(note.id), restored);
      queryClient.invalidateQueries({ queryKey: ["notes", "list"] });
      queryClient.invalidateQueries({ queryKey: ["notes", "versions", note.id] });
      toast.success("Version restored", { description: "The previous state was kept in history." });
      onRestored(restored);
      onOpenChange(false);
    },
    onError: (e) => toast.error(messageFor(e)),
  });
  const canRestore = note.access !== "viewer";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[88dvh] overflow-hidden p-0 sm:max-w-3xl">
        <DialogHeader className="px-5 pt-5">
          <DialogTitle>Version history</DialogTitle>
          <DialogDescription>Meaningful snapshots of this note. Restoring keeps today’s version in the list.</DialogDescription>
        </DialogHeader>
        <div className="grid h-[60dvh] grid-cols-1 border-t border-glass-border sm:grid-cols-[15rem_minmax(0,1fr)]">
          <aside className="scrollbar-thin overflow-y-auto border-b border-glass-border sm:border-b-0 sm:border-r" aria-label="Versions">
            {versions.isPending ? (
              <div className="space-y-2 p-3">
                {Array.from({ length: 4 }).map((_, i) => (
                  <Skeleton key={i} className="h-12 rounded-lg" />
                ))}
              </div>
            ) : versions.data?.length ? (
              <ul className="p-2">
                {versions.data.map((v) => (
                  <li key={v.id}>
                    <button
                      type="button"
                      onClick={() => setSelected(v.id)}
                      aria-current={v.id === activeId ? "true" : undefined}
                      className={cn("w-full rounded-lg px-3 py-2 text-left outline-none transition-colors hover:bg-muted/50 focus-visible:ring-2 focus-visible:ring-ring", v.id === activeId && "bg-ai-soft")}
                    >
                      <span className="block text-sm font-medium">{stamp(v.created_at)}</span>
                      <span className="block truncate text-xs text-muted-foreground">
                        {v.reason === "before_restore" ? "Before a restore" : `Version ${v.note_version}`}
                        {v.title ? ` · ${v.title}` : ""}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyState icon={History} className="py-10" title="No versions yet" description="A snapshot is kept the first time you edit after a pause." />
            )}
          </aside>
          <section className="flex min-h-0 flex-col">
            <div className="scrollbar-thin min-h-0 flex-1 overflow-y-auto px-6 py-5" data-note-color={note.color}>
              {detail.isPending && activeId ? (
                <Skeleton className="h-40 rounded-lg" />
              ) : detail.data ? (
                <>
                  <h3 className="mb-3 text-xl font-semibold tracking-tight">{detail.data.title || "Untitled"}</h3>
                  <RichTextEditor key={detail.data.id} documentKey={detail.data.id} content={detail.data.content_json} editable={false} className="[&_.notely-editor]:min-h-0" />
                </>
              ) : (
                <p className="text-sm text-muted-foreground">Pick a version to preview it.</p>
              )}
            </div>
            <footer className="flex items-center justify-between gap-3 border-t border-glass-border px-5 py-3">
              <p className="text-xs text-muted-foreground">{detail.data ? `Snapshot from ${stamp(detail.data.created_at)}` : ""}</p>
              <Button size="sm" disabled={!activeId || !canRestore || restore.isPending} onClick={() => activeId && restore.mutate(activeId)}>
                {restore.isPending ? <Loader2 className="animate-spin" aria-hidden /> : <RotateCcw aria-hidden />} Restore this version
              </Button>
            </footer>
          </section>
        </div>
      </DialogContent>
    </Dialog>
  );
}
