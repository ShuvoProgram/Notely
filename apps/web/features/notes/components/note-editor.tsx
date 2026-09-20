"use client";

import { Archive, ArchiveRestore, ArrowLeft, ChevronRight, Copy, Folder as FolderIcon, MoreHorizontal, RotateCcw, Sparkles, Star, Trash2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { NOTE_AI_ACTIONS, NoteAIPanel } from "@/features/ai/components/note-ai-panel";
import { messageFor } from "@/features/auth/components/auth-form-error";
import { RichTextEditor } from "@/features/notes/components/rich-text-editor";
import { SaveStatusIndicator } from "@/features/notes/components/save-status";
import { TagPicker } from "@/features/notes/components/tag-picker";
import { clearDraft, readDraft, shouldRestoreDraft } from "@/features/notes/drafts";
import { useFolders, useNote, useNoteActions, useUpdateNote } from "@/features/notes/hooks";
import { useAutosave } from "@/features/notes/use-autosave";
import type { Editor } from "@tiptap/react";

import { ApiError } from "@/lib/api/client";
import type { Note, NoteAIAction, TipTapDoc } from "@/lib/api/types";
import { cn } from "@/lib/utils";

export function NoteEditor({ noteId }: { noteId: string }) {
  const { data: note, isPending, error } = useNote(noteId);

  if (isPending) {
    return (
      <div className="space-y-4" aria-busy>
        <Skeleton className="h-10 w-2/3" />
        <Skeleton className="h-6 w-1/3" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }
  if (error || !note) {
    const notFound = error instanceof ApiError && error.status === 404;
    return (
      <div className="rounded-xl border bg-card p-8 text-center">
        <h2 className="text-lg font-semibold">{notFound ? "This note doesn't exist" : "Couldn't load this note"}</h2>
        <p className="mt-1 text-sm text-muted-foreground">{notFound ? "It may have been deleted." : messageFor(error)}</p>
      </div>
    );
  }
  return <LoadedNoteEditor key={note.id} note={note} />;
}

function LoadedNoteEditor({ note }: { note: Note }) {
  const router = useRouter();
  const autosave = useAutosave(note);
  const update = useUpdateNote();
  const actions = useNoteActions();
  const { data: folders = [] } = useFolders();
  const readOnly = note.deleted_at !== null;

  // Restore an unsaved local draft (e.g. after a crash) before the editor mounts.
  const [initial] = React.useState(() => {
    const draft = typeof window !== "undefined" ? readDraft(note.id) : null;
    if (shouldRestoreDraft(draft, note.version, note.content_json, note.title) && draft) {
      return { title: draft.title, content: draft.content_json, restored: true };
    }
    return { title: note.title, content: note.content_json, restored: false };
  });
  const [title, setTitle] = React.useState(initial.title);
  const editorRef = React.useRef<Editor | null>(null);
  const [editorInstance, setEditorInstance] = React.useState<Editor | null>(null);
  const [aiAction, setAiAction] = React.useState<NoteAIAction | null>(null);
  const restoredOnce = React.useRef(false);
  React.useEffect(() => {
    if (initial.restored && !restoredOnce.current) {
      restoredOnce.current = true;
      toast.message("Restored unsaved changes", { description: "We found edits that hadn't reached the server." });
      autosave.queue({ title: initial.title, content_json: initial.content });
    }
  }, [initial, autosave]);

  const onTitleChange = (value: string) => {
    setTitle(value);
    autosave.queue({ title: value });
  };
  const onBodyChange = React.useCallback((doc: TipTapDoc) => autosave.queue({ content_json: doc }), [autosave]);

  const meta = (input: Parameters<typeof update.mutate>[0]["input"], ok?: string) =>
    update.mutate({ id: note.id, input }, { onSuccess: () => ok && toast.success(ok), onError: (e) => toast.error(messageFor(e)) });

  const [confirmPurge, setConfirmPurge] = React.useState(false);

  const folderName = note.folder_id ? folders.find((f) => f.id === note.folder_id)?.name : null;
  const suggestion = aiAction ? (
    <NoteAIPanel key={aiAction} noteId={note.id} action={aiAction} editor={editorInstance} onClose={() => setAiAction(null)} />
  ) : null;

  return (
    <div className="mx-auto grid w-full max-w-6xl gap-6 2xl:grid-cols-[minmax(0,1fr)_300px]">
    <div className="surface flex min-h-full min-w-0 flex-col rounded-2xl px-5 py-6 sm:px-8 sm:py-8">
      <nav aria-label="Breadcrumb" className="mb-4 flex items-center gap-1 text-xs text-muted-foreground">
        <Link href="/app/notes" className="inline-flex items-center gap-1 rounded hover:text-foreground">
          <ArrowLeft className="size-3.5 md:hidden" aria-hidden /> Notes
        </Link>
        {folderName ? (
          <>
            <ChevronRight className="size-3" aria-hidden />
            <Link href={`/app/notes?folder=${note.folder_id}`} className="rounded hover:text-foreground">
              {folderName}
            </Link>
          </>
        ) : null}
      </nav>
      {readOnly ? (
        <div role="status" className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-warning/40 bg-warning/10 px-3 py-2 text-sm">
          <span>This note is in the trash. Restore it to keep editing.</span>
          <div className="flex gap-2">
            <Button size="sm" variant="outline" onClick={() => actions.restore.mutate(note.id, { onSuccess: () => toast.success("Note restored") })}>
              <RotateCcw aria-hidden /> Restore
            </Button>
            <Button size="sm" variant="destructive" onClick={() => setConfirmPurge(true)}>
              Delete forever
            </Button>
          </div>
        </div>
      ) : null}

      {autosave.status === "conflict" ? (
        <Alert className="mb-4 border-warning/40 bg-warning/10">
          <AlertTitle>This note changed in another tab or device</AlertTitle>
          <AlertDescription className="flex flex-wrap items-center justify-between gap-3">
            <span>Your local edits are safe until you choose.</span>
            <span className="flex gap-2">
              <Button size="sm" variant="outline" onClick={() => void autosave.loadTheirs()}>
                Load latest
              </Button>
              <Button size="sm" onClick={() => void autosave.keepMine()}>
                Keep mine
              </Button>
            </span>
          </AlertDescription>
        </Alert>
      ) : null}

      <div className="mb-2 flex items-start gap-2">
        <input
          aria-label="Note title"
          placeholder="Untitled"
          value={title}
          readOnly={readOnly}
          onChange={(e) => onTitleChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" || (e.key === "ArrowDown" && !readOnly)) {
              e.preventDefault();
              const editor = editorRef.current;
              if (editor) {
                editor.commands.focus("start");
                editor.view.focus(); // commands.focus defers to rAF; make it immediate
              }
            }
          }}
          className={cn(
            "min-w-0 flex-1 bg-transparent text-3xl font-semibold tracking-tight outline-none placeholder:text-muted-foreground/40 sm:text-4xl",
          )}
        />
        <div className="flex shrink-0 items-center gap-1">
          <SaveStatusIndicator status={autosave.status} message={autosave.errorMessage} />
          <Button
            variant="ghost"
            size="icon"
            aria-label={note.is_favorite ? "Remove from favorites" : "Add to favorites"}
            aria-pressed={note.is_favorite}
            disabled={readOnly}
            onClick={() => meta({ is_favorite: !note.is_favorite })}
          >
            <Star className={cn(note.is_favorite && "fill-warning text-warning")} aria-hidden />
          </Button>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon" aria-label="Note actions">
                <MoreHorizontal aria-hidden />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-56">
              <DropdownMenuSub>
                <DropdownMenuSubTrigger disabled={readOnly}>
                  <FolderIcon aria-hidden /> Move to folder
                </DropdownMenuSubTrigger>
                <DropdownMenuSubContent className="w-56">
                  <DropdownMenuRadioGroup
                    value={note.folder_id ?? ""}
                    onValueChange={(v) => meta(v ? { folder_id: v } : { clear_folder: true }, "Moved")}
                  >
                    <DropdownMenuRadioItem value="">No folder</DropdownMenuRadioItem>
                    {folders.length ? <DropdownMenuSeparator /> : null}
                    {folders.map((f) => (
                      <DropdownMenuRadioItem key={f.id} value={f.id}>
                        {f.name}
                      </DropdownMenuRadioItem>
                    ))}
                  </DropdownMenuRadioGroup>
                </DropdownMenuSubContent>
              </DropdownMenuSub>
              <DropdownMenuItem
                disabled={readOnly}
                onSelect={() =>
                  actions.duplicate.mutate(note.id, {
                    onSuccess: (copy) => {
                      toast.success("Duplicated");
                      router.push(`/app/notes/${copy.id}`);
                    },
                  })
                }
              >
                <Copy aria-hidden /> Duplicate
              </DropdownMenuItem>
              <DropdownMenuItem disabled={readOnly} onSelect={() => meta({ archived: !note.archived_at }, note.archived_at ? "Unarchived" : "Archived")}>
                {note.archived_at ? <ArchiveRestore aria-hidden /> : <Archive aria-hidden />}
                {note.archived_at ? "Unarchive" : "Archive"}
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              {readOnly ? (
                <>
                  <DropdownMenuItem onSelect={() => actions.restore.mutate(note.id)}>
                    <RotateCcw aria-hidden /> Restore
                  </DropdownMenuItem>
                  <DropdownMenuItem variant="destructive" onSelect={() => setConfirmPurge(true)}>
                    <Trash2 aria-hidden /> Delete forever
                  </DropdownMenuItem>
                </>
              ) : (
                <DropdownMenuItem
                  variant="destructive"
                  onSelect={() =>
                    void autosave.flush().then(() =>
                      actions.trash.mutate(note.id, {
                        onSuccess: () => {
                          toast.success("Moved to trash", {
                            action: { label: "Undo", onClick: () => actions.restore.mutate(note.id) },
                          });
                          router.push("/app/notes");
                        },
                      }),
                    )
                  }
                >
                  <Trash2 aria-hidden /> Move to trash
                </DropdownMenuItem>
              )}
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>

      <div className="mb-6 flex flex-wrap items-center gap-x-3 gap-y-2 text-xs text-muted-foreground">
        <TagPicker selected={note.tags} onChange={(tag_ids) => meta({ tag_ids })} disabled={readOnly} />
        <span className="inline-flex items-center gap-1">
          <FolderIcon className="size-3.5" aria-hidden />
          {folderName ?? "No folder"}
        </span>
        <span aria-hidden>·</span>
        <span>Edited {new Date(note.updated_at).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })}</span>
      </div>

      {suggestion ? <div className="mb-6 2xl:hidden">{suggestion}</div> : null}

      <RichTextEditor
        documentKey={note.id}
        content={initial.content}
        editable={!readOnly}
        onChange={onBodyChange}
        onAskAI={readOnly ? undefined : (action) => setAiAction(action)}
        onReady={(editor) => {
          editorRef.current = editor;
          setEditorInstance(editor);
        }}
      />

      <Dialog open={confirmPurge} onOpenChange={setConfirmPurge}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete this note forever?</DialogTitle>
            <DialogDescription>“{note.title || "Untitled"}” will be permanently removed. This cannot be undone.</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmPurge(false)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              disabled={actions.purge.isPending}
              onClick={() =>
                actions.purge.mutate(note.id, {
                  onSuccess: () => {
                    clearDraft(note.id);
                    toast.success("Note deleted");
                    router.push("/app/notes?view=trash");
                  },
                  onError: (e) => toast.error(messageFor(e)),
                })
              }
            >
              Delete forever
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>

      <aside aria-label="AI assistant" className="hidden 2xl:block">
        <div className="sticky top-2 space-y-4">
          {suggestion ?? (
            <div className="glass rounded-2xl p-4">
              <div className="mb-4 flex items-center gap-2">
                <span className="grid size-8 place-items-center rounded-xl bg-ai-soft text-ai">
                  <Sparkles className="size-4" aria-hidden />
                </span>
                <div>
                  <p className="text-sm font-semibold">AI Assistant</p>
                  <p className="text-xs text-muted-foreground">Works on your selection, or the whole note.</p>
                </div>
              </div>
              <ul className="space-y-1.5">
                {NOTE_AI_ACTIONS.map((a) => (
                  <li key={a.id}>
                    <button
                      type="button"
                      disabled={readOnly}
                      onClick={() => setAiAction(a.id)}
                      className="lift flex w-full items-center gap-3 rounded-xl bg-muted/40 px-3 py-2.5 text-left text-sm ring-1 ring-glass-border outline-none hover:bg-muted/70 focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
                    >
                      <a.icon className="size-4 shrink-0 text-ai" aria-hidden />
                      <span className="min-w-0">
                        <span className="block font-medium">{a.label}</span>
                        <span className="block truncate text-xs text-muted-foreground">{a.description}</span>
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
              <Button variant="outline" disabled={readOnly} onClick={() => setAiAction("custom")} className="mt-3 w-full justify-start gap-2 rounded-xl text-muted-foreground">
                <Sparkles className="size-4 text-ai" aria-hidden /> Ask anything about this note…
              </Button>
            </div>
          )}
        </div>
      </aside>
    </div>
  );
}
