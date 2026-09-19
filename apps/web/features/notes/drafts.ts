/**
 * Local draft backup for the editor. Written on every change, cleared once the server confirms
 * the save, so an unexpected tab close or a failed request never loses content.
 */

import type { TipTapDoc } from "@/lib/api/types";

export interface Draft {
  title: string;
  content_json: TipTapDoc;
  /** Server version the draft was based on. */
  base_version: number;
  saved_at: number;
}

const PREFIX = "notely:draft:";

export function draftKey(noteId: string): string {
  return `${PREFIX}${noteId}`;
}

export function readDraft(noteId: string): Draft | null {
  try {
    const raw = window.localStorage.getItem(draftKey(noteId));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Draft;
    if (!parsed || typeof parsed.base_version !== "number") return null;
    return parsed;
  } catch {
    return null;
  }
}

export function writeDraft(noteId: string, draft: Omit<Draft, "saved_at">): void {
  try {
    window.localStorage.setItem(draftKey(noteId), JSON.stringify({ ...draft, saved_at: Date.now() }));
  } catch {
    // Storage may be full or blocked; the in-memory editor state is still the source until saved.
  }
}

export function clearDraft(noteId: string): void {
  try {
    window.localStorage.removeItem(draftKey(noteId));
  } catch {
    // ignore
  }
}

/** A draft is worth restoring if it was based on the current server version and differs from it. */
export function shouldRestoreDraft(draft: Draft | null, serverVersion: number, serverContent: unknown, serverTitle: string): boolean {
  if (!draft) return false;
  if (draft.base_version !== serverVersion) return false;
  return draft.title !== serverTitle || JSON.stringify(draft.content_json) !== JSON.stringify(serverContent);
}
