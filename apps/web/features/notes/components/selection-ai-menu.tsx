"use client";

import type { Editor } from "@tiptap/react";
import * as React from "react";

import { NoteAIMenu } from "@/features/ai/components/note-ai-panel";
import type { NoteAIAction } from "@/lib/api/types";
import { cn } from "@/lib/utils";


/**
 * Floating "Ask AI" pill that appears above a text selection and opens the action menu. It
 * never edits the note itself; it hands the chosen action to the suggestion panel, which
 * reads the live selection when it runs. Positioned from ProseMirror coordinates so it works
 * with wrapped selections and inside scroll containers.
 */
export function SelectionAIMenu({ editor, containerRef, onPick, disabled }: { editor: Editor; containerRef: React.RefObject<HTMLDivElement | null>; onPick: (action: NoteAIAction) => void; disabled?: boolean }) {
  const [pos, setPos] = React.useState<{ top: number; left: number; below: boolean } | null>(null);
  const menuRef = React.useRef<HTMLDivElement | null>(null);

  React.useEffect(() => {
    if (disabled) return;
    let raf = 0;
    const update = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        const { from, to, empty } = editor.state.selection;
        const container = containerRef.current;
        if (empty || !editor.isFocused || !container || to - from < 2) {
          setPos(null);
          return;
        }
        const start = editor.view.coordsAtPos(from);
        const end = editor.view.coordsAtPos(to);
        const box = container.getBoundingClientRect();
        // Above the selection unless that would collide with the sticky toolbar; then below.
        const below = start.top - box.top < 64;
        const half = (menuRef.current?.offsetWidth ?? 120) / 2;
        const centre = (start.left + end.left) / 2 - box.left;
        const left = Math.max(half + 4, Math.min(centre, box.width - half - 4));
        setPos({ top: below ? end.bottom - box.top + 8 : start.top - box.top - 8, left, below });
      });
    };
    editor.on("selectionUpdate", update);
    editor.on("focus", update);
    editor.on("blur", update);
    window.addEventListener("resize", update);
    return () => {
      editor.off("selectionUpdate", update);
      editor.off("focus", update);
      editor.off("blur", update);
      window.removeEventListener("resize", update);
      cancelAnimationFrame(raf);
    };
  }, [editor, containerRef, disabled]);

  if (!pos || disabled) return null;
  return (
    <div
      ref={menuRef}
      className={cn("animate-fade-up absolute z-30 -translate-x-1/2", !pos.below && "-translate-y-full")}
      style={{ top: pos.top, left: pos.left }}
      onMouseDown={(e) => e.preventDefault()} // keep the editor selection while clicking
    >
      <NoteAIMenu onPick={onPick} label="Ask AI about this" />
    </div>
  );
}
