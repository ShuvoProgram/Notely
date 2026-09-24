"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { ArchiveRestore, Folder, LogOut, Trash2 } from "@/components/icons";
import type { SelectionAction } from "@/components/layout/selection-bar";
import { messageFor } from "@/features/auth/components/auth-form-error";
import { notesApi } from "@/features/notes/api";
import type { NoteView } from "@/lib/api/types";
import { playSfx } from "@/lib/sfx/player";

const plural = (n: number) => `${n} ${n === 1 ? "note" : "notes"}`;

/**
 * What can be done to a selection of notes, per list view. The toolbar renders these; the list
 * only passes the ids. Reversible actions run straight away with an Undo toast; irreversible ones
 * (delete forever, leave) carry a confirmation.
 */
export function useNoteBulkActions(view: NoteView, ids: Set<string>, done: () => void, onMove?: () => void): SelectionAction[] {
  const queryClient = useQueryClient();
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["notes"] });
  const fail = (e: unknown) => toast.error(messageFor(e));

  const restore = useMutation({ mutationFn: notesApi.restoreMany, onSettled: refresh, onError: fail });
  const trash = useMutation({
    mutationFn: notesApi.trashMany,
    onSuccess: ({ moved }, sent) => {
      playSfx("delete");
      done();
      toast.success(`Moved ${plural(moved)} to trash`, {
        action: { label: "Undo", onClick: () => restore.mutate(sent) },
      });
    },
    onSettled: refresh,
    onError: fail,
  });
  const purge = useMutation({
    mutationFn: notesApi.purgeMany,
    onSuccess: ({ deleted }) => {
      playSfx("delete");
      done();
      toast.success(`Deleted ${plural(deleted)} forever`);
    },
    onSettled: refresh,
    onError: fail,
  });
  const leave = useMutation({
    mutationFn: notesApi.leaveMany,
    onSuccess: ({ left }) => {
      done();
      toast.success(`Left ${plural(left)}`);
    },
    onSettled: refresh,
    onError: fail,
  });

  const selected = [...ids];
  const n = selected.length;

  if (view === "trash") {
    return [
      {
        id: "restore",
        label: "Restore",
        icon: ArchiveRestore,
        tone: "primary",
        pending: restore.isPending,
        onRun: () =>
          restore.mutate(selected, {
            onSuccess: ({ restored }) => {
              done();
              toast.success(`Restored ${plural(restored)}`);
            },
          }),
      },
      {
        id: "purge",
        label: "Delete forever",
        icon: Trash2,
        tone: "destructive",
        pending: purge.isPending,
        confirm: {
          title: `Delete ${plural(n)} forever?`,
          description: `This can't be undone. ${n === 1 ? "The note and its" : "The notes and their"} version history are removed permanently.`,
          label: "Delete forever",
        },
        onRun: () => purge.mutate(selected),
      },
    ];
  }
  if (view === "shared") {
    return [
      {
        id: "leave",
        label: "Leave",
        icon: LogOut,
        tone: "destructive",
        pending: leave.isPending,
        confirm: {
          title: `Leave ${plural(n)}?`,
          description: "You'll lose access. The owner keeps the notes and can invite you again.",
          label: "Leave",
        },
        onRun: () => leave.mutate(selected),
      },
    ];
  }
  return [
    // Picking the folder happens in the list (a sheet), so this only opens it.
    ...(onMove ? [{ id: "move", label: "Move to folder", icon: Folder, onRun: onMove } satisfies SelectionAction] : []),
    {
      id: "trash",
      label: "Move to trash",
      icon: Trash2,
      tone: "destructive",
      pending: trash.isPending,
      onRun: () => trash.mutate(selected),
    },
  ];
}
