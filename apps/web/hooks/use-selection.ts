"use client";

import * as React from "react";

/**
 * One selection model for every bulk-action list (notes, tasks). The set of ids is the single
 * source of truth; the toolbar and the rows both read from it. Ids survive filtering (hidden
 * items stay selected), so `visible` is passed in to compute "all visible selected" and to
 * support shift-click ranges in display order.
 */
export function useSelection(visible: string[]) {
  const [selecting, setSelecting] = React.useState(false);
  const [ids, setIds] = React.useState<Set<string>>(() => new Set());
  const anchor = React.useRef<string | null>(null);

  const exit = React.useCallback(() => {
    setSelecting(false);
    setIds(new Set());
    anchor.current = null;
  }, []);
  const enter = React.useCallback(() => setSelecting(true), []);

  // Escape leaves selection mode from anywhere on the page (unless a dialog owns the key).
  React.useEffect(() => {
    if (!selecting) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !e.defaultPrevented && !document.querySelector("[role=dialog][data-state=open]")) exit();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [selecting, exit]);

  const toggle = React.useCallback(
    (id: string, checked: boolean, opts?: { shift?: boolean }) => {
      setIds((prev) => {
        const next = new Set(prev);
        const from = anchor.current;
        if (opts?.shift && from && from !== id) {
          const a = visible.indexOf(from);
          const b = visible.indexOf(id);
          if (a >= 0 && b >= 0) {
            for (const v of visible.slice(Math.min(a, b), Math.max(a, b) + 1)) {
              if (checked) next.add(v);
              else next.delete(v);
            }
            return next;
          }
        }
        if (checked) next.add(id);
        else next.delete(id);
        return next;
      });
      anchor.current = id;
    },
    [visible],
  );

  const selectAll = React.useCallback(
    (all: boolean) => {
      setIds((prev) => {
        const next = new Set(prev);
        for (const v of visible) {
          if (all) next.add(v);
          else next.delete(v);
        }
        return next;
      });
    },
    [visible],
  );

  const visibleSelected = visible.filter((v) => ids.has(v)).length;
  return {
    selecting,
    enter,
    exit,
    ids,
    count: ids.size,
    has: (id: string) => ids.has(id),
    toggle,
    selectAll,
    /** Checkbox state for "Select all": all visible, some, or none. */
    allState: (visible.length > 0 && visibleSelected === visible.length ? true : visibleSelected > 0 ? "indeterminate" : false) as boolean | "indeterminate",
    allVisible: visible.length > 0 && visibleSelected === visible.length,
    visibleTotal: visible.length,
  };
}
