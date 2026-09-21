"use client";

import { Check, ChevronsUpDown, Loader2 } from "lucide-react";
import * as React from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import type { ModelInfo, ModelPrice } from "@/lib/api/types";
import { cn } from "@/lib/utils";

const PRICE_LABEL: Record<ModelPrice, string> = { free: "Free", budget: "$", standard: "$$", premium: "$$$", unknown: "" };

export function formatContext(tokens: number | null): string {
  if (!tokens) return "";
  if (tokens >= 1_000_000) return `${(tokens / 1_000_000).toFixed(tokens % 1_000_000 ? 1 : 0)}M ctx`;
  return `${Math.round(tokens / 1000)}K ctx`;
}

/**
 * Searchable model combobox. Options come from the vendor (live) or the catalog (suggested),
 * are grouped Free / Paid when pricing is known, and a name that is not in the list can still
 * be used verbatim — some servers simply do not report what they serve.
 */
export function ModelPicker({
  id,
  value,
  onChange,
  options,
  loading,
  disabled,
  placeholder = "Choose a model",
  invalid,
  groupByPrice,
}: {
  id?: string;
  value: string;
  onChange: (id: string) => void;
  options: ModelInfo[];
  loading?: boolean;
  disabled?: boolean;
  placeholder?: string;
  invalid?: boolean;
  /** OpenRouter: show Free and Paid sections. */
  groupByPrice?: boolean;
}) {
  const [open, setOpen] = React.useState(false);
  const [query, setQuery] = React.useState("");
  const selected = options.find((m) => m.id === value);
  const needle = query.trim().toLowerCase();
  const filtered = needle ? options.filter((m) => m.id.toLowerCase().includes(needle) || m.name.toLowerCase().includes(needle)) : options;
  const groups: { label: string; items: ModelInfo[] }[] = groupByPrice
    ? [
        { label: "Free", items: filtered.filter((m) => m.price === "free") },
        { label: "Paid", items: filtered.filter((m) => m.price !== "free") },
      ].filter((g) => g.items.length)
    : [{ label: "", items: filtered }];
  const canUseTyped = needle !== "" && !options.some((m) => m.id.toLowerCase() === needle);

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button id={id} type="button" variant="outline" role="combobox" aria-expanded={open} aria-invalid={invalid || undefined} disabled={disabled} className="w-full justify-between bg-background/60 font-normal">
          <span className={cn("min-w-0 truncate text-left", !value && "text-muted-foreground")}>{selected ? selected.name : value || placeholder}</span>
          {loading ? <Loader2 className="size-4 shrink-0 animate-spin opacity-60" aria-hidden /> : <ChevronsUpDown className="size-4 shrink-0 opacity-60" aria-hidden />}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-(--radix-popover-trigger-width) min-w-[20rem] p-0">
        <Command shouldFilter={false}>
          <CommandInput placeholder="Search models…" value={query} onValueChange={setQuery} />
          <CommandList className="max-h-72">
            <CommandEmpty>{loading ? "Loading models…" : "No model matches."}</CommandEmpty>
            {canUseTyped ? (
              <CommandGroup>
                <CommandItem
                  value={`use:${query.trim()}`}
                  onSelect={() => {
                    onChange(query.trim());
                    setOpen(false);
                  }}
                >
                  <span className="col-span-full truncate">
                    Use “<span className="font-mono">{query.trim()}</span>” as typed
                  </span>
                </CommandItem>
              </CommandGroup>
            ) : null}
            {groups.map((g) => (
              <CommandGroup key={g.label || "all"} heading={g.label || undefined}>
                {g.items.slice(0, 150).map((m) => (
                  <CommandItem
                    key={m.id}
                    value={m.id}
                    onSelect={() => {
                      onChange(m.id);
                      setOpen(false);
                    }}
                    className="gap-2"
                  >
                    <Check className={cn("size-4 shrink-0", m.id === value ? "opacity-100" : "opacity-0")} aria-hidden />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate">{m.name}</span>
                      {m.name !== m.id ? <span className="block truncate font-mono text-[11px] text-muted-foreground">{m.id}</span> : null}
                    </span>
                    <span className="flex shrink-0 items-center gap-1 text-[11px] text-muted-foreground">
                      {m.status === "preview" ? <Badge variant="outline" className="h-4 px-1 font-normal">preview</Badge> : null}
                      {m.status === "deprecated" ? <Badge variant="outline" className="h-4 px-1 font-normal text-warning">retiring</Badge> : null}
                      {!m.tools ? <Badge variant="outline" className="h-4 px-1 font-normal text-warning">no tools</Badge> : null}
                      {m.context ? <span>{formatContext(m.context)}</span> : null}
                      {PRICE_LABEL[m.price] ? <span className={cn(m.price === "free" && "text-success")}>{PRICE_LABEL[m.price]}</span> : null}
                    </span>
                  </CommandItem>
                ))}
              </CommandGroup>
            ))}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
