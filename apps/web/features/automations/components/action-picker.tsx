"use client";

import { Lock, Search, ShieldAlert, Sparkles, Zap } from "@/components/icons";
import Link from "next/link";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandItemMeta, CommandItemText, CommandList } from "@/components/ui/command";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";

import type { ActionSpec, Catalog } from "../types";
import { AppIcon } from "./app-icon";

const ORDER = ["notely", "ai"];

/** Choose what a step does: every action you can use, grouped by app, in plain words. */
export function ActionPicker({
  open,
  onOpenChange,
  catalog,
  onPick,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  catalog?: Catalog;
  onPick: (action: ActionSpec) => void;
}) {
  const groups = React.useMemo(() => {
    const byApp = new Map<string, ActionSpec[]>();
    for (const action of catalog?.actions ?? []) {
      byApp.set(action.app, [...(byApp.get(action.app) ?? []), action]);
    }
    const rank = (app: string, list: ActionSpec[]) =>
      ORDER.includes(app) ? ORDER.indexOf(app) : list.some((a) => a.available) ? 10 : 100;
    return [...byApp.entries()].sort(([a, la], [b, lb]) => rank(a, la) - rank(b, lb) || a.localeCompare(b));
  }, [catalog]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90dvh] gap-0 overflow-hidden p-0 sm:max-w-lg">
        <DialogHeader className="border-b border-glass-border p-4">
          <DialogTitle>What should this step do?</DialogTitle>
          <DialogDescription>Pick an app and an action. Apps you haven&apos;t connected are shown too.</DialogDescription>
        </DialogHeader>
        <Command className="rounded-none">
          <CommandInput placeholder="Search, e.g. “summarize” or “Gmail”" />
          <CommandList className="max-h-[60dvh]">
            <CommandEmpty>No action matches. Try other words.</CommandEmpty>
            {groups.map(([app, actions]) => {
              const info = catalog?.apps.find((a) => a.id === app);
              const locked = !actions.some((a) => a.available);
              return (
                <CommandGroup
                  key={app}
                  heading={
                    <span className="flex items-center gap-2">
                      <AppIcon appId={app} catalog={catalog} size="xs" />
                      {actions[0]?.app_name ?? app}
                      {locked && info?.connect_path ? (
                        <Button asChild size="sm" variant="link" className="ml-auto h-auto p-0 text-xs">
                          <Link href={info.connect_path}>Connect</Link>
                        </Button>
                      ) : null}
                    </span>
                  }
                >
                  {actions.map((action) => (
                    <CommandItem
                      key={action.id}
                      value={`${action.app_name} ${action.label} ${action.description}`}
                      disabled={!action.available}
                      onSelect={() => {
                        onPick(action);
                        onOpenChange(false);
                      }}
                    >
                      {action.group === "find" ? <Search aria-hidden /> : action.group === "ai" ? <Sparkles aria-hidden /> : <Zap aria-hidden />}
                      <CommandItemText title={action.label} description={action.description} />
                      {!action.available ? (
                        <Lock className="col-start-3 size-3.5 text-muted-foreground" aria-label="Connect this app first" />
                      ) : action.safety !== "safe" ? (
                        <CommandItemMeta className="items-center gap-1 text-warning sm:inline-flex">
                          <ShieldAlert className="size-3.5" aria-hidden /> Asks first
                        </CommandItemMeta>
                      ) : null}
                    </CommandItem>
                  ))}
                </CommandGroup>
              );
            })}
          </CommandList>
        </Command>
      </DialogContent>
    </Dialog>
  );
}
