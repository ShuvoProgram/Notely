"use client";

import { Braces, FlaskConical, Plus } from "@/components/icons";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";

import { TRIGGER_OPTIONS, type DataOption, type DataSource } from "../lib";
import type { Catalog } from "../types";
import { AppIcon } from "./app-icon";

/**
 * What the run itself offers as data: the schedule basics, or the fields of the event that
 * started it ("Subject", "From" …). The builder provides it; every picker below reads it.
 */
export const TriggerDataContext = React.createContext<{ heading: string; options: DataOption[] }>({ heading: "This run", options: TRIGGER_OPTIONS });

/** "Insert data": every piece of data earlier steps produce, grouped by step, in plain words. */
export function DataPicker({
  sources,
  catalog,
  onPick,
  label = "Insert data",
  filter,
  trigger,
}: {
  sources: DataSource[];
  catalog?: Catalog;
  onPick: (option: DataOption) => void;
  label?: string;
  filter?: (option: DataOption) => boolean;
  trigger?: React.ReactNode;
}) {
  const [open, setOpen] = React.useState(false);
  const run = React.useContext(TriggerDataContext);
  const pick = (option: DataOption) => {
    onPick(option);
    setOpen(false);
  };
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        {trigger ?? (
          <Button type="button" variant="ghost" size="sm" className="h-7 gap-1 px-2 text-xs text-ai hover:text-ai">
            <Plus className="size-3.5" aria-hidden />
            {label}
          </Button>
        )}
      </PopoverTrigger>
      <PopoverContent align="start" className="w-[min(22rem,calc(100vw-2rem))] p-0">
        <Command>
          <CommandInput placeholder="Search data…" />
          <CommandList className="max-h-80">
            <CommandEmpty>
              {sources.length ? "Nothing matches." : "Add a step before this one to use its data."}
            </CommandEmpty>
            {sources.map((source, index) => {
              const options = source.options.filter((o) => !filter || filter(o));
              const onlyEverything = options.length === 1;
              return (
                <CommandGroup
                  key={source.step.id}
                  heading={
                    <span className="flex items-center gap-1.5">
                      <AppIcon appId={source.appId} catalog={catalog} size="xs" />
                      {index + 1}. {source.title}
                    </span>
                  }
                >
                  {options.map((option) => (
                    <CommandItem key={option.path} value={`${source.title} ${option.label} ${option.path}`} onSelect={() => pick(option)}>
                      <Braces className="size-3.5 text-muted-foreground" aria-hidden />
                      <span className="truncate">{option.label}</span>
                    </CommandItem>
                  ))}
                  {onlyEverything ? (
                    <p className="flex items-center gap-1.5 px-2 pb-2 text-[11px] text-muted-foreground">
                      <FlaskConical className="size-3" aria-hidden /> Test this step to choose individual fields.
                    </p>
                  ) : null}
                </CommandGroup>
              );
            })}
            <CommandGroup heading={run.heading}>
              {run.options.filter((o) => !filter || filter(o)).map((option) => (
                <CommandItem key={option.path} value={`run ${option.label}`} onSelect={() => pick(option)}>
                  <Braces className="size-3.5 text-muted-foreground" aria-hidden />
                  {option.label}
                </CommandItem>
              ))}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
