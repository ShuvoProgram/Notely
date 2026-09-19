"use client";

import { ChevronRight, Folder as FolderIcon, MoreHorizontal, Pencil, Plus, Tag as TagIcon, Trash2 } from "lucide-react";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { messageFor } from "@/features/auth/components/auth-form-error";
import { useFolderMutations, useFolders, useTagMutations, useTags } from "@/features/notes/hooks";
import type { Folder, Tag } from "@/lib/api/types";
import { cn } from "@/lib/utils";

type FolderDialog = { mode: "create"; parentId: string | null } | { mode: "rename"; folder: Folder } | { mode: "delete"; folder: Folder } | null;

function buildTree(folders: Folder[]): Map<string | null, Folder[]> {
  const byParent = new Map<string | null, Folder[]>();
  for (const f of folders) {
    const list = byParent.get(f.parent_id) ?? [];
    list.push(f);
    byParent.set(f.parent_id, list);
  }
  return byParent;
}

export function FolderSidebar({ onNavigate }: { onNavigate?: () => void }) {
  const { data: folders = [] } = useFolders();
  const { data: tags = [] } = useTags();
  const mutations = useFolderMutations();
  const tagMutations = useTagMutations();
  const pathname = usePathname();
  const params = useSearchParams();
  const activeFolder = pathname.startsWith("/app/notes") ? params.get("folder") : null;
  const activeTag = pathname.startsWith("/app/notes") ? params.get("tag") : null;
  const [dialog, setDialog] = React.useState<FolderDialog>(null);
  const [name, setName] = React.useState("");
  const [collapsed, setCollapsed] = React.useState<Set<string>>(new Set());
  const [tagToDelete, setTagToDelete] = React.useState<Tag | null>(null);

  const tree = buildTree(folders);

  const openDialog = (d: FolderDialog) => {
    setName(d?.mode === "rename" ? d.folder.name : "");
    setDialog(d);
  };

  const submit = () => {
    if (!dialog || dialog.mode === "delete") return;
    const trimmed = name.trim();
    if (!trimmed) return;
    const opts = { onSuccess: () => setDialog(null), onError: (e: unknown) => toast.error(messageFor(e)) };
    if (dialog.mode === "create") mutations.create.mutate({ name: trimmed, parent_id: dialog.parentId }, opts);
    else mutations.update.mutate({ id: dialog.folder.id, name: trimmed }, opts);
  };

  const renderLevel = (parentId: string | null, depth: number): React.ReactNode =>
    (tree.get(parentId) ?? []).map((folder) => {
      const children = tree.get(folder.id) ?? [];
      const isCollapsed = collapsed.has(folder.id);
      const active = activeFolder === folder.id;
      return (
        <li key={folder.id}>
          <div
            className={cn(
              "group flex items-center gap-1 rounded-md pr-1 text-sm hover:bg-sidebar-accent/60",
              active && "bg-sidebar-accent text-sidebar-accent-foreground",
            )}
            style={{ paddingLeft: `${depth * 12}px` }}
          >
            <button
              type="button"
              aria-label={isCollapsed ? "Expand" : "Collapse"}
              aria-expanded={!isCollapsed}
              className={cn("grid size-6 shrink-0 place-items-center rounded text-muted-foreground", !children.length && "invisible")}
              onClick={() =>
                setCollapsed((s) => {
                  const next = new Set(s);
                  if (next.has(folder.id)) next.delete(folder.id);
                  else next.add(folder.id);
                  return next;
                })
              }
            >
              <ChevronRight className={cn("size-3.5 transition-transform", !isCollapsed && "rotate-90")} aria-hidden />
            </button>
            <Link
              href={`/app/notes?folder=${folder.id}`}
              onClick={onNavigate}
              aria-current={active ? "page" : undefined}
              className="flex min-w-0 flex-1 items-center gap-2 py-1.5 outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <FolderIcon className="size-4 shrink-0 text-muted-foreground" aria-hidden />
              <span className="truncate">{folder.name}</span>
              <span className="ml-auto text-xs text-muted-foreground">{folder.note_count || ""}</span>
            </Link>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="icon-sm" aria-label={`Folder actions for ${folder.name}`} className="opacity-0 focus-visible:opacity-100 group-hover:opacity-100">
                  <MoreHorizontal aria-hidden />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="start">
                <DropdownMenuItem onSelect={() => openDialog({ mode: "create", parentId: folder.id })}>
                  <Plus aria-hidden /> New subfolder
                </DropdownMenuItem>
                <DropdownMenuItem onSelect={() => openDialog({ mode: "rename", folder })}>
                  <Pencil aria-hidden /> Rename
                </DropdownMenuItem>
                <DropdownMenuItem variant="destructive" onSelect={() => openDialog({ mode: "delete", folder })}>
                  <Trash2 aria-hidden /> Delete
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
          {children.length && !isCollapsed ? <ul>{renderLevel(folder.id, depth + 1)}</ul> : null}
        </li>
      );
    });

  return (
    <div className="space-y-4">
      <section>
        <div className="flex items-center justify-between px-3">
          <h2 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Folders</h2>
          <Button variant="ghost" size="icon-sm" aria-label="New folder" onClick={() => openDialog({ mode: "create", parentId: null })}>
            <Plus aria-hidden />
          </Button>
        </div>
        {folders.length ? (
          <ul className="mt-1 px-1">{renderLevel(null, 0)}</ul>
        ) : (
          <p className="mt-1 px-3 text-xs text-muted-foreground">No folders yet.</p>
        )}
      </section>

      {tags.length ? (
        <section>
          <h2 className="px-3 text-xs font-medium uppercase tracking-wide text-muted-foreground">Tags</h2>
          <ul className="mt-1 px-1">
            {tags.map((tag) => {
              const active = activeTag === tag.id;
              return (
                <li key={tag.id} className={cn("group flex items-center rounded-md pr-1 text-sm hover:bg-sidebar-accent/60", active && "bg-sidebar-accent")}>
                  <Link
                    href={`/app/notes?tag=${tag.id}`}
                    onClick={onNavigate}
                    aria-current={active ? "page" : undefined}
                    className="flex min-w-0 flex-1 items-center gap-2 px-2 py-1.5 outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    <span className="size-2 shrink-0 rounded-full" style={{ background: tag.color ?? "var(--muted-foreground)" }} aria-hidden />
                    <span className="truncate">{tag.name}</span>
                    <span className="ml-auto text-xs text-muted-foreground">{tag.note_count || ""}</span>
                  </Link>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    aria-label={`Delete tag ${tag.name}`}
                    className="opacity-0 focus-visible:opacity-100 group-hover:opacity-100"
                    onClick={() => setTagToDelete(tag)}
                  >
                    <Trash2 aria-hidden />
                  </Button>
                </li>
              );
            })}
          </ul>
        </section>
      ) : (
        <p className="flex items-center gap-1.5 px-3 text-xs text-muted-foreground">
          <TagIcon className="size-3.5" aria-hidden /> Tags you add to notes show up here.
        </p>
      )}

      <Dialog open={dialog !== null && dialog.mode !== "delete"} onOpenChange={(o) => !o && setDialog(null)}>
        <DialogContent>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              submit();
            }}
          >
            <DialogHeader>
              <DialogTitle>{dialog?.mode === "rename" ? "Rename folder" : "New folder"}</DialogTitle>
              <DialogDescription>
                {dialog?.mode === "create" && dialog.parentId ? "The folder will be created inside the selected folder." : "Folders help you group related notes."}
              </DialogDescription>
            </DialogHeader>
            <div className="my-4 space-y-2">
              <Label htmlFor="folder-name">Name</Label>
              <Input id="folder-name" value={name} onChange={(e) => setName(e.target.value)} autoFocus maxLength={120} />
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setDialog(null)}>
                Cancel
              </Button>
              <Button type="submit" disabled={!name.trim() || mutations.create.isPending || mutations.update.isPending}>
                {dialog?.mode === "rename" ? "Save" : "Create"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog open={dialog?.mode === "delete"} onOpenChange={(o) => !o && setDialog(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete “{dialog?.mode === "delete" ? dialog.folder.name : ""}”?</DialogTitle>
            <DialogDescription>Notes inside will be kept and moved out of the folder. Subfolders are removed.</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialog(null)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              disabled={mutations.remove.isPending}
              onClick={() =>
                dialog?.mode === "delete" &&
                mutations.remove.mutate(dialog.folder.id, {
                  onSuccess: () => {
                    setDialog(null);
                    toast.success("Folder deleted");
                  },
                  onError: (e) => toast.error(messageFor(e)),
                })
              }
            >
              Delete folder
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={tagToDelete !== null} onOpenChange={(o) => !o && setTagToDelete(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete tag “{tagToDelete?.name}”?</DialogTitle>
            <DialogDescription>The tag is removed from every note. Notes themselves are not affected.</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setTagToDelete(null)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              disabled={tagMutations.remove.isPending}
              onClick={() =>
                tagToDelete &&
                tagMutations.remove.mutate(tagToDelete.id, {
                  onSuccess: () => {
                    setTagToDelete(null);
                    toast.success("Tag deleted");
                  },
                  onError: (e) => toast.error(messageFor(e)),
                })
              }
            >
              Delete tag
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
