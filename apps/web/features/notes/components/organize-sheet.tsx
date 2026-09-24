"use client";

import { Check, Folder as FolderIcon, Inbox } from "@/components/icons";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { FolderSidebar } from "@/features/folders/components/folder-sidebar";
import { useFolders } from "@/features/notes/hooks";
import type { Folder } from "@/lib/api/types";
import { cn } from "@/lib/utils";

/** A bottom sheet that reads as part of the phone: rounded top, grab handle, clear of the home
 * indicator, never taller than most of the screen. Centred and narrower on wider screens. */
const sheetClass =
  "max-h-[85dvh] gap-0 rounded-t-3xl p-0 pb-[env(safe-area-inset-bottom)]  sm:mx-auto sm:max-w-lg";

function Handle() {
  return <span aria-hidden className="mx-auto mt-2.5 block h-1 w-10 shrink-0 rounded-full bg-muted-foreground/30" />;
}

/**
 * Notes' own "Folders & tags" entry on phones and tablets (desktop shows them in the sidebar).
 * The trigger names the folder being viewed, so it doubles as the current-filter indicator.
 */
export function OrganizeSheet({ currentLabel, className }: { currentLabel?: string; className?: string }) {
  const [open, setOpen] = React.useState(false);
  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <Button variant="outline" size="sm" className={cn("h-10 max-w-[45%] shrink-0 rounded-full px-3.5", className)} aria-label="Folders and tags">
          <FolderIcon aria-hidden />
          <span className="truncate">{currentLabel ?? "Folders & tags"}</span>
        </Button>
      </SheetTrigger>
      <SheetContent side="bottom" className={sheetClass}>
        <Handle />
        <SheetHeader className="px-5 pb-2 pt-3">
          <SheetTitle>Folders &amp; tags</SheetTitle>
          <SheetDescription>Open a folder or tag to filter your notes.</SheetDescription>
        </SheetHeader>
        <div className="scrollbar-thin overflow-y-auto overscroll-contain px-2 pb-5">
          <FolderSidebar variant="sheet" onNavigate={() => setOpen(false)} />
        </div>
      </SheetContent>
    </Sheet>
  );
}

/** Pick a destination folder (or none) for the selected notes. */
export function FolderPickerSheet({
  open,
  onOpenChange,
  count,
  pending,
  onPick,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  count: number;
  pending: boolean;
  onPick: (folderId: string | null) => void;
}) {
  const { data: folders = [] } = useFolders();
  const [choice, setChoice] = React.useState<string | null | undefined>(undefined);
  const ordered = React.useMemo(() => flatten(folders), [folders]);

  const row = (id: string | null, label: string, depth: number, icon: React.ReactNode) => (
    <li key={id ?? "none"}>
      <button
        type="button"
        onClick={() => setChoice(id)}
        aria-pressed={choice === id}
        className={cn(
          "flex min-h-12 w-full items-center gap-3 rounded-xl px-3 text-left text-[15px] outline-none hover:bg-accent/60 focus-visible:ring-2 focus-visible:ring-ring",
          choice === id && "bg-accent font-medium",
        )}
        style={{ paddingLeft: `${12 + depth * 16}px` }}
      >
        {icon}
        <span className="min-w-0 flex-1 truncate">{label}</span>
        {choice === id ? <Check className="size-4 text-ai" aria-hidden /> : null}
      </button>
    </li>
  );

  return (
    <Sheet
      open={open}
      onOpenChange={(o) => {
        if (!o) setChoice(undefined);
        onOpenChange(o);
      }}
    >
      <SheetContent side="bottom" className={sheetClass}>
        <Handle />
        <SheetHeader className="px-5 pb-2 pt-3">
          <SheetTitle>Move {count === 1 ? "1 note" : `${count} notes`}</SheetTitle>
          <SheetDescription>Choose a folder.</SheetDescription>
        </SheetHeader>
        <ul className="scrollbar-thin flex-1 overflow-y-auto overscroll-contain px-2">
          {row(null, "No folder", 0, <Inbox className="size-4 shrink-0 text-muted-foreground" aria-hidden />)}
          {ordered.map(({ folder, depth }) => row(folder.id, folder.name, depth, <FolderIcon className="size-4 shrink-0 text-muted-foreground" aria-hidden />))}
        </ul>
        <div className="flex gap-2 border-t border-border/60 px-4 py-3">
          <Button variant="outline" className="h-11 flex-1 rounded-full" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button className="h-11 flex-1 rounded-full" disabled={choice === undefined || pending} onClick={() => choice !== undefined && onPick(choice)}>
            Move
          </Button>
        </div>
      </SheetContent>
    </Sheet>
  );
}

function flatten(folders: Folder[]): { folder: Folder; depth: number }[] {
  const byParent = new Map<string | null, Folder[]>();
  for (const f of folders) byParent.set(f.parent_id, [...(byParent.get(f.parent_id) ?? []), f]);
  const out: { folder: Folder; depth: number }[] = [];
  const walk = (parent: string | null, depth: number) => {
    for (const f of byParent.get(parent) ?? []) {
      out.push({ folder: f, depth });
      walk(f.id, depth + 1);
    }
  };
  walk(null, 0);
  return out;
}
