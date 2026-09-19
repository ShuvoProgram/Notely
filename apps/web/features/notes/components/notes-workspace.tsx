"use client";

import { NotebookPen, Plus } from "lucide-react";
import { useParams, useRouter } from "next/navigation";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { messageFor } from "@/features/auth/components/auth-form-error";
import { NotesList } from "@/features/notes/components/notes-list";
import { useCreateNote } from "@/features/notes/hooks";
import { cn } from "@/lib/utils";

/**
 * Two-pane notes workspace. Desktop: list + editor side by side. Mobile: the list is the index
 * route and the editor takes the full screen.
 */
export function NotesWorkspace({ children }: { children: React.ReactNode }) {
  const params = useParams<{ id?: string }>();
  const activeNoteId = params?.id;
  const hasNote = Boolean(activeNoteId);

  return (
    <div className="-mx-4 -my-6 flex h-[calc(100dvh-3.5rem)] min-h-0 sm:-mx-6 sm:-my-8">
      <aside
        aria-label="Notes list"
        className={cn(
          "w-full shrink-0 border-r bg-background md:block md:w-80 lg:w-88",
          hasNote ? "hidden" : "block",
        )}
      >
        <NotesList activeNoteId={activeNoteId} />
      </aside>
      <section className={cn("min-w-0 flex-1 overflow-y-auto", hasNote ? "block" : "hidden md:block")}>
        <div className="mx-auto w-full max-w-3xl px-4 py-6 pb-24 sm:px-8 sm:py-10 md:pb-10">{children}</div>
      </section>
    </div>
  );
}

export function NotesEmptyState() {
  const router = useRouter();
  const create = useCreateNote();
  return (
    <div className="flex h-full min-h-[50vh] flex-col items-center justify-center text-center">
      <div className="grid size-12 place-items-center rounded-xl bg-ai-soft text-ai">
        <NotebookPen className="size-6" aria-hidden />
      </div>
      <h2 className="mt-4 text-lg font-semibold">Pick a note, or start a new one</h2>
      <p className="mt-1 max-w-sm text-sm text-muted-foreground">
        Everything you write is saved automatically and searchable the moment you stop typing.
      </p>
      <Button
        className="mt-5"
        onClick={() =>
          create.mutate({}, { onSuccess: (n) => router.push(`/app/notes/${n.id}`), onError: (e) => toast.error(messageFor(e)) })
        }
        disabled={create.isPending}
      >
        <Plus aria-hidden /> New note
      </Button>
    </div>
  );
}
