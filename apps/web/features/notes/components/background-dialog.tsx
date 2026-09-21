"use client";

import { Check, RotateCcw } from "lucide-react";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { isHexColor, isPresetColor, NOTE_COLORS, noteColorProps } from "@/features/notes/lib";
import type { NoteColor } from "@/lib/api/types";
import { cn } from "@/lib/utils";

/**
 * Note background: thirteen presets and a custom colour. Whatever is picked is only ever a
 * soft tint over the note surface (the swatch shows the colour at full strength), so text
 * contrast is never at risk and there is no "too bright" state to guard against.
 */
export function BackgroundDialog({
  open,
  onOpenChange,
  value,
  onSave,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  value: NoteColor;
  onSave: (color: NoteColor) => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        {/* Mounted only while open, so the draft starts from the note's colour every time. */}
        <BackgroundForm value={value} onSave={onSave} onCancel={() => onOpenChange(false)} />
      </DialogContent>
    </Dialog>
  );
}

function BackgroundForm({ value, onSave, onCancel }: { value: NoteColor; onSave: (color: NoteColor) => void; onCancel: () => void }) {
  const [draft, setDraft] = React.useState<string>(value);
  const [hex, setHex] = React.useState(() => (isHexColor(value) ? value : ""));

  const custom = !isPresetColor(draft);
  const hexValid = hex === "" || isHexColor(hex);
  const applyHex = (next: string) => {
    setHex(next);
    if (isHexColor(next)) setDraft(next.toLowerCase());
  };
  const preview = noteColorProps(draft);

  return (
    <>
        <DialogHeader>
          <DialogTitle>Note background</DialogTitle>
          <DialogDescription>Pick a paper colour or set your own. Text stays readable on all of them.</DialogDescription>
        </DialogHeader>

        <div className="mt-2 grid grid-cols-7 gap-2" role="radiogroup" aria-label="Preset colours">
          {NOTE_COLORS.map((c) => {
            const active = draft === c.value;
            return (
              <button
                key={c.value}
                type="button"
                role="radio"
                aria-checked={active}
                aria-label={c.label}
                title={c.label}
                onClick={() => setDraft(c.value)}
                className={cn("grid size-9 place-items-center rounded-full outline-none transition-transform hover:scale-105 focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-popover", c.swatch, active && "ring-2 ring-foreground ring-offset-2 ring-offset-popover")}
              >
                {active ? <Check className="size-4 text-black/70" aria-hidden /> : null}
              </button>
            );
          })}
        </div>

        <div className="mt-4 space-y-2">
          <Label htmlFor="note-color-hex">Custom colour</Label>
          <div className="flex items-center gap-2">
            <label className={cn("relative size-9 shrink-0 cursor-pointer overflow-hidden rounded-full ring-1 ring-glass-border-strong", custom && "ring-2 ring-foreground ring-offset-2 ring-offset-popover")} style={{ backgroundColor: isHexColor(hex) ? hex : "var(--muted)" }}>
              <span className="sr-only">Open colour picker</span>
              <input
                type="color"
                aria-label="Colour picker"
                value={isHexColor(hex) ? hex : "#8aa1c1"}
                onChange={(e) => applyHex(e.target.value)}
                className="absolute inset-0 size-full cursor-pointer opacity-0"
              />
            </label>
            <Input
              id="note-color-hex"
              placeholder="#8aa1c1"
              value={hex}
              aria-invalid={!hexValid || undefined}
              onChange={(e) => applyHex(e.target.value.startsWith("#") || e.target.value === "" ? e.target.value : `#${e.target.value}`)}
              className="font-mono uppercase"
              maxLength={7}
              spellCheck={false}
            />
          </div>
          {!hexValid ? <p className="text-xs text-destructive">Use a six-digit hex colour, like #8AA1C1.</p> : null}
        </div>

        <div className="mt-4 rounded-xl border border-glass-border p-4 note-surface" {...preview} aria-label="Preview">
          <p className="text-xs text-muted-foreground">Preview</p>
          <p className="mt-1 text-base font-semibold">Weekly planning</p>
          <p className="text-sm text-muted-foreground">Three things that matter this week, and one that can wait.</p>
        </div>

        <DialogFooter className="mt-2 sm:justify-between">
          <Button type="button" variant="ghost" className="text-muted-foreground" disabled={draft === "default"} onClick={() => { setDraft("default"); setHex(""); }}>
            <RotateCcw aria-hidden /> Reset to default
          </Button>
          <div className="flex gap-2">
            <Button type="button" variant="outline" onClick={onCancel}>
              Cancel
            </Button>
            <Button type="button" disabled={!isPresetColor(draft) && !isHexColor(draft)} onClick={() => onSave(draft)}>
              Apply
            </Button>
          </div>
        </DialogFooter>
    </>
  );
}
