"use client";

import { useQueryClient } from "@tanstack/react-query";
import * as React from "react";

import { notesApi } from "@/features/notes/api";
import { clearDraft, writeDraft } from "@/features/notes/drafts";
import { noteKeys } from "@/features/notes/hooks";
import { ApiError } from "@/lib/api/client";
import type { Note, TipTapDoc } from "@/lib/api/types";

export type SaveStatus = "idle" | "dirty" | "saving" | "saved" | "offline" | "conflict" | "error";

export interface PendingChange {
  title?: string;
  content_json?: TipTapDoc;
}

export interface Autosave {
  status: SaveStatus;
  /** Server version the editor is currently based on. */
  version: number;
  /** Version the server reported when it rejected our save. */
  conflictVersion: number | null;
  queue: (change: PendingChange) => void;
  flush: () => Promise<void>;
  /** Conflict resolution: overwrite the server copy with the local one. */
  keepMine: () => Promise<void>;
  /** Conflict resolution: discard local changes and reload the server copy. */
  loadTheirs: () => Promise<void>;
  errorMessage: string | null;
}

const DEBOUNCE_MS = 900;

// Saves outlive the hook instance that started them (the editor unmounts on navigation and
// flushes on the way out). A freshly mounted editor for the same note must wait for that save
// and continue from the version it produced, or its first save would be a false conflict.
const inflightByNote = new Map<string, Promise<void>>();
const savedVersionByNote = new Map<string, number>();

function hasPending(change: PendingChange): boolean {
  return change.title !== undefined || change.content_json !== undefined;
}

/**
 * Debounced, version-checked autosave. Every change is mirrored to localStorage immediately;
 * the server save is debounced and sends `expected_version` so concurrent edits surface as a
 * conflict rather than silently overwriting each other.
 */
export function useAutosave(note: Note): Autosave {
  const queryClient = useQueryClient();
  const [status, setStatus] = React.useState<SaveStatus>("idle");
  const [conflictVersion, setConflictVersion] = React.useState<number | null>(null);
  const [errorMessage, setErrorMessage] = React.useState<string | null>(null);
  const [version, setVersion] = React.useState(note.version);

  // A previous instance may have saved a newer version while this one was mounting.
  const versionRef = React.useRef(Math.max(note.version, savedVersionByNote.get(note.id) ?? 0));
  const pendingRef = React.useRef<PendingChange>({});
  const latestRef = React.useRef<{ title: string; content_json: TipTapDoc }>({
    title: note.title,
    content_json: note.content_json ?? { type: "doc", content: [] },
  });
  const timerRef = React.useRef<ReturnType<typeof setTimeout> | null>(null);
  const inflightRef = React.useRef<Promise<void> | null>(null);

  // Callers mount one hook instance per note (`key={note.id}`), so no reset-on-change is needed.

  // The detail cache is what a remounted editor initialises from, so it must always hold what
  // the user sees — not what the server had before they started typing.
  const mirrorToCache = React.useCallback(
    (patch: Partial<Note>) => {
      queryClient.setQueryData<Note>(noteKeys.detail(note.id), (old) =>
        old ? { ...old, ...patch, title: latestRef.current.title, content_json: latestRef.current.content_json } : old,
      );
    },
    [note.id, queryClient],
  );

  const save = React.useCallback(
    async (force: boolean): Promise<void> => {
      if (!force && !hasPending(pendingRef.current)) return;
      const prior = inflightRef.current ?? inflightByNote.get(note.id);
      if (prior) await prior;
      const carriedVersion = savedVersionByNote.get(note.id);
      if (carriedVersion !== undefined && carriedVersion > versionRef.current) {
        versionRef.current = carriedVersion;
      }
      // Re-read after awaiting: more may have been typed, or the prior save may have sent it.
      const change = pendingRef.current;
      if (!force && !hasPending(change)) return;

      const payload: PendingChange & { expected_version?: number } = force
        ? { ...latestRef.current }
        : { ...change, expected_version: versionRef.current };
      pendingRef.current = {};
      setStatus("saving");

      const run = (async () => {
        try {
          const saved = await notesApi.update(note.id, payload);
          versionRef.current = saved.version;
          savedVersionByNote.set(note.id, saved.version);
          setVersion(saved.version);
          mirrorToCache(saved);
          queryClient.invalidateQueries({ queryKey: ["notes", "list"] });
          setConflictVersion(null);
          setErrorMessage(null);
          if (hasPending(pendingRef.current)) {
            setStatus("dirty");
          } else {
            clearDraft(note.id);
            setStatus("saved");
          }
        } catch (error) {
          // Keep the unsent change so a retry or the draft backup still has it.
          pendingRef.current = { ...payload, ...pendingRef.current };
          delete (pendingRef.current as { expected_version?: number }).expected_version;
          if (error instanceof ApiError && error.code === "NOTE_VERSION_CONFLICT") {
            const current = error.details["current_version"];
            setConflictVersion(typeof current === "number" ? current : null);
            setStatus("conflict");
          } else if (error instanceof ApiError) {
            setErrorMessage(error.message);
            setStatus("error");
          } else {
            setStatus("offline");
          }
        }
      })();
      inflightRef.current = run;
      inflightByNote.set(note.id, run);
      await run;
      inflightRef.current = null;
      if (inflightByNote.get(note.id) === run) inflightByNote.delete(note.id);
    },
    [note.id, mirrorToCache, queryClient],
  );

  const schedule = React.useCallback(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      timerRef.current = null;
      void save(false);
    }, DEBOUNCE_MS);
  }, [save]);

  const queue = React.useCallback(
    (change: PendingChange) => {
      pendingRef.current = { ...pendingRef.current, ...change };
      latestRef.current = { ...latestRef.current, ...change };
      writeDraft(note.id, { ...latestRef.current, base_version: versionRef.current });
      mirrorToCache({});
      if (status === "conflict") return; // wait for the user to resolve
      setStatus("dirty");
      schedule();
    },
    [note.id, mirrorToCache, schedule, status],
  );

  const flush = React.useCallback(async () => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    await save(false);
  }, [save]);

  const keepMine = React.useCallback(async () => {
    setConflictVersion(null);
    await save(true);
  }, [save]);

  const loadTheirs = React.useCallback(async () => {
    pendingRef.current = {};
    clearDraft(note.id);
    setConflictVersion(null);
    setStatus("idle");
    await queryClient.invalidateQueries({ queryKey: noteKeys.detail(note.id) });
  }, [note.id, queryClient]);

  // Flush on unmount / navigation, and warn on tab close with unsaved changes.
  React.useEffect(() => {
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      if (hasPending(pendingRef.current)) {
        e.preventDefault();
      }
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    const onOnline = () => {
      if (hasPending(pendingRef.current)) void save(false);
    };
    window.addEventListener("online", onOnline);
    return () => {
      window.removeEventListener("beforeunload", onBeforeUnload);
      window.removeEventListener("online", onOnline);
      if (timerRef.current) clearTimeout(timerRef.current);
      void save(false);
    };
  }, [save]);

  return {
    status,
    version,
    conflictVersion,
    queue,
    flush,
    keepMine,
    loadTheirs,
    errorMessage,
  };
}
