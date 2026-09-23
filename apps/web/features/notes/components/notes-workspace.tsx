"use client";

import { NotebookPen, Plus, Sparkles } from "@/components/icons";
import { useParams, useRouter } from "next/navigation";
import { toast } from "sonner";

import { EmptyState } from "@/components/layout/empty-state";
import { Button } from "@/components/ui/button";
import { Kbd } from "@/components/ui/kbd";
import { messageFor } from "@/features/auth/components/auth-form-error";
import { NotesList } from "@/features/notes/components/notes-list";
import { useCreateNote } from "@/features/notes/hooks";
import { cn } from "@/lib/utils";

/**
 * Notes workspace. Desktop: a glass list panel beside the editor; the editor page adds its own
 * assistant rail on wide screens. Phone: the list is the index route and the editor takes the
 * full screen, so there is never a squeezed two-column layout.
 */
export function NotesWorkspace({ children }: { children: React.ReactNode }) {
  const params = useParams<{ id?: string }>();
  const activeNoteId = params?.id;
  const hasNote = Boolean(activeNoteId);

  return (
    <div data-full-bleed className="flex h-[calc(100dvh-4rem)] min-h-0">
      <aside
        aria-label="Notes list"
        className={cn(
          "glass w-full shrink-0 rounded-none border-y-0 border-l-0 md:block md:w-72 lg:w-80",
          hasNote ? "hidden" : "block",
        )}
      >
        <NotesList activeNoteId={activeNoteId} />
      </aside>
      <section className={cn("scrollbar-thin min-w-0 flex-1 overflow-y-auto", hasNote ? "block" : "hidden md:block")}>
        <div className="w-full px-4 py-4 pb-28 sm:px-6 sm:py-6 md:pb-8">{children}</div>
      </section>
    </div>
  );
}

export function NotesEmptyState() {
  const router = useRouter();
  const create = useCreateNote();
  return (
    <div className="flex h-full min-h-[60vh] items-center justify-center">
      <EmptyState
        icon={NotebookPen}
        tone="ai"
        title="Pick a note, or start a new one"
        description={
          <>
            Everything you write is saved as you type. Select any text and press <span className="inline-flex items-center gap-1 text-ai"><Sparkles className="size-3" aria-hidden />Ask AI</span> to summarize, rewrite or turn it into tasks.
          </>
        }
        action={
          <>
            <Button
              onClick={() =>
                create.mutate({}, { onSuccess: (n) => router.push(`/app/notes/${n.id}`), onError: (e) => toast.error(messageFor(e)) })
              }
              disabled={create.isPending}
            >
              <Plus aria-hidden /> New note
            </Button>
            <span className="inline-flex items-center gap-1.5 self-center text-xs text-muted-foreground">
              or press <Kbd>⌘K</Kbd>
            </span>
          </>
        }
      />
    </div>
  );
}
