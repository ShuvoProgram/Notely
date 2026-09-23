"use client";

import { Check, Plus, Tag as TagIcon, X } from "@/components/icons";
import * as React from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { messageFor } from "@/features/auth/components/auth-form-error";
import { useTagMutations, useTags } from "@/features/notes/hooks";
import type { Tag } from "@/lib/api/types";
import { cn } from "@/lib/utils";

interface TagPickerProps {
  selected: Tag[];
  onChange: (tagIds: string[]) => void;
  disabled?: boolean;
}

export function TagChip({ tag, onRemove }: { tag: Tag; onRemove?: () => void }) {
  return (
    <Badge variant="secondary" className="gap-1 pr-1 font-normal">
      <span className="size-2 rounded-full" style={{ background: tag.color ?? "var(--muted-foreground)" }} aria-hidden />
      {tag.name}
      {onRemove ? (
        <button
          type="button"
          onClick={onRemove}
          aria-label={`Remove tag ${tag.name}`}
          className="ml-0.5 rounded-sm p-0.5 hover:bg-foreground/10"
        >
          <X className="size-3" aria-hidden />
        </button>
      ) : null}
    </Badge>
  );
}

export function TagPicker({ selected, onChange, disabled }: TagPickerProps) {
  const { data: tags = [] } = useTags();
  const { create } = useTagMutations();
  const [open, setOpen] = React.useState(false);
  const [query, setQuery] = React.useState("");

  const selectedIds = new Set(selected.map((t) => t.id));
  const filtered = tags.filter((t) => t.name.toLowerCase().includes(query.trim().toLowerCase()));
  const exact = tags.some((t) => t.name.toLowerCase() === query.trim().toLowerCase());

  const toggle = (tag: Tag) => {
    const next = selectedIds.has(tag.id)
      ? selected.filter((t) => t.id !== tag.id).map((t) => t.id)
      : [...selected.map((t) => t.id), tag.id];
    onChange(next);
  };

  const createTag = () => {
    const name = query.trim();
    if (!name) return;
    create.mutate(
      { name },
      {
        onSuccess: (tag) => {
          onChange([...selected.map((t) => t.id), tag.id]);
          setQuery("");
        },
        onError: (e) => toast.error(messageFor(e)),
      },
    );
  };

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {selected.map((tag) => (
        <TagChip key={tag.id} tag={tag} onRemove={disabled ? undefined : () => toggle(tag)} />
      ))}
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button type="button" variant="ghost" size="sm" className="h-6 gap-1 px-2 text-xs text-muted-foreground" disabled={disabled}>
            <TagIcon className="size-3.5" aria-hidden />
            {selected.length ? "Edit tags" : "Add tag"}
          </Button>
        </PopoverTrigger>
        <PopoverContent align="start" className="w-64 p-2">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const first = filtered[0];
              if (query.trim() && !exact) createTag();
              else if (first) toggle(first);
            }}
          >
            <Input
              aria-label="Search or create tag"
              placeholder="Search or create…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              autoFocus
              className="h-8"
            />
          </form>
          <ul className="mt-2 max-h-56 overflow-y-auto" role="listbox" aria-label="Tags">
            {filtered.map((tag) => {
              const active = selectedIds.has(tag.id);
              return (
                <li key={tag.id}>
                  <button
                    type="button"
                    role="option"
                    aria-selected={active}
                    onClick={() => toggle(tag)}
                    className={cn(
                      "flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm hover:bg-accent",
                      active && "text-foreground",
                    )}
                  >
                    <span className="size-2 rounded-full" style={{ background: tag.color ?? "var(--muted-foreground)" }} aria-hidden />
                    <span className="flex-1 truncate">{tag.name}</span>
                    {active ? <Check className="size-4 text-ai" aria-hidden /> : null}
                  </button>
                </li>
              );
            })}
            {query.trim() && !exact ? (
              <li>
                <button
                  type="button"
                  onClick={createTag}
                  disabled={create.isPending}
                  className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm text-ai hover:bg-accent"
                >
                  <Plus className="size-4" aria-hidden /> Create “{query.trim()}”
                </button>
              </li>
            ) : null}
            {!filtered.length && !query.trim() ? (
              <li className="px-2 py-1.5 text-xs text-muted-foreground">No tags yet. Type to create one.</li>
            ) : null}
          </ul>
        </PopoverContent>
      </Popover>
    </div>
  );
}
