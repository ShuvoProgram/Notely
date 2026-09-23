"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useTheme } from "next-themes";
import * as React from "react";
import { toast } from "sonner";

import { Check, Moon, RotateCcw, Sun } from "@/components/icons";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { messageFor } from "@/features/auth/components/auth-form-error";
import { authKeys, useCurrentUser, useUpdateProfile } from "@/features/auth/hooks";
import { applyLook } from "@/lib/appearance/apply";
import { BACKGROUNDS, backgroundById, DEFAULT_APPEARANCE, GLASS_LEVELS, imageUrl, resolve } from "@/lib/appearance/model";
import type { Appearance, BackgroundId, GlassLevel, User } from "@/lib/api/types";
import { cn } from "@/lib/utils";

const LEVELS: GlassLevel[] = ["off", "subtle", "medium", "strong"];
const TUNE: { key: "blur" | "opacity" | "border"; label: string; low: string; high: string }[] = [
  { key: "blur", label: "Background blur", low: "Sharp", high: "Frosted" },
  { key: "opacity", label: "Surface opacity", low: "Clear", high: "Solid" },
  { key: "border", label: "Border intensity", low: "Soft", high: "Defined" },
];

/**
 * Settings → Appearance. Every change previews instantly on the whole app (the page itself is
 * the preview) and is saved to the account, so it follows the user to other devices. Sliders
 * preview while dragging and save when released. Backgrounds are limited to the approved images.
 */
export function AppearanceSettings() {
  const { data: user, isPending } = useCurrentUser();
  const update = useUpdateProfile();
  const queryClient = useQueryClient();
  const { resolvedTheme, setTheme } = useTheme();
  const mounted = React.useSyncExternalStore(
    () => () => {},
    () => true,
    () => false,
  );
  const [draft, setDraft] = React.useState<Appearance | null>(null);

  if (isPending || !user) return null;
  const current = draft ?? user.appearance ?? DEFAULT_APPEARANCE;
  const look = resolve(current);
  const dark = !mounted || resolvedTheme !== "light";

  /** Show a look without saving it (while a slider is being dragged). */
  const preview = (next: Appearance) => {
    setDraft(next);
    applyLook(resolve(next));
  };

  /** Save: optimistic, so everything that reads the user sees the new look at once. */
  const commit = (next: Appearance) => {
    const before = queryClient.getQueryData<User>(authKeys.me);
    queryClient.setQueryData<User>(authKeys.me, (u) => (u ? { ...u, appearance: next } : u));
    setDraft(null);
    update.mutate(
      { appearance: next },
      {
        onError: (e) => {
          if (before) queryClient.setQueryData(authKeys.me, before);
          toast.error(messageFor(e));
        },
      },
    );
  };

  const pickBackground = (background: BackgroundId) => commit({ ...current, background });

  // A bright picture under dark glass (or a dark one under light glass) is readable, but looks best flipped.
  const tone = backgroundById(current.background).tone;
  const better = tone === "light" && dark ? "light" : tone === "dark" && !dark ? "dark" : null;

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Theme</CardTitle>
          <CardDescription>Dark or light surfaces. Your background and glass settings apply to both.</CardDescription>
        </CardHeader>
        <CardContent>
          <div role="radiogroup" aria-label="Theme" className="grid grid-cols-2 gap-3 sm:max-w-sm">
            {[
              { id: "dark", label: "Dark", icon: Moon, on: dark },
              { id: "light", label: "Light", icon: Sun, on: !dark },
            ].map((t) => (
              <button
                key={t.id}
                type="button"
                role="radio"
                aria-checked={t.on}
                onClick={() => setTheme(t.id)}
                className={cn(
                  "liquid-press flex items-center gap-2.5 rounded-xl border px-3 py-2.5 text-sm font-medium",
                  t.on ? "liquid-selected border-transparent text-foreground" : "border-glass-border bg-field text-muted-foreground hover:text-foreground",
                )}
              >
                <t.icon className="size-4" />
                {t.label}
              </button>
            ))}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Background</CardTitle>
          <CardDescription>The picture behind your workspace. Panels and text adjust to keep everything readable on it.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          <div role="radiogroup" aria-label="Background" className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
            {BACKGROUNDS.map((bg) => {
              const selected = current.background === bg.id;
              return (
                <button key={bg.id} type="button" role="radio" aria-checked={selected} aria-label={bg.label} onClick={() => pickBackground(bg.id)} className="group flex flex-col gap-1.5 text-left outline-none">
                  <span
                    className={cn(
                      "relative aspect-[16/10] w-full overflow-hidden rounded-xl border bg-muted bg-cover bg-center transition-[box-shadow,border-color,transform] duration-200 ease-liquid group-hover:-translate-y-px group-active:scale-[0.98] group-focus-visible:ring-2 group-focus-visible:ring-ring",
                      selected ? "border-ai shadow-[0_0_0_2px_var(--ai)]" : "border-glass-border-strong",
                    )}
                    style={{ backgroundImage: `url("${imageUrl(bg, 384)}")` }}
                  >
                    {selected ? (
                      <span className="absolute right-1.5 top-1.5 grid size-5 place-items-center rounded-full bg-ai text-primary-foreground shadow-1">
                        <Check className="size-3" />
                      </span>
                    ) : null}
                  </span>
                  <span className={cn("truncate text-xs", selected ? "font-medium text-foreground" : "text-muted-foreground group-hover:text-foreground")}>{bg.label}</span>
                </button>
              );
            })}
          </div>

          {mounted && better ? (
            <div role="status" className="flex flex-wrap items-center gap-2 rounded-xl border border-glass-border bg-field px-3 py-2 text-sm">
              <p className="min-w-0 flex-1 text-muted-foreground">
                This picture is {better === "light" ? "bright" : "dark"}, so it looks its best with the {better === "light" ? "Light" : "Dark"} theme. Text stays readable either way.
              </p>
              <Button type="button" variant="outline" size="sm" onClick={() => setTheme(better)}>
                {better === "light" ? <Sun aria-hidden /> : <Moon aria-hidden />} Use {better === "light" ? "Light" : "Dark"} theme
              </Button>
            </div>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Glass effect</CardTitle>
          <CardDescription>How much of the background shows through panels, menus and dialogs.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          <div role="radiogroup" aria-label="Glass effect" className="grid grid-cols-2 gap-1 rounded-xl border border-glass-border bg-field p-1 sm:grid-cols-4">
            {LEVELS.map((level) => (
              <button
                key={level}
                type="button"
                role="radio"
                aria-checked={current.glass === level}
                onClick={() => commit({ ...current, glass: level, blur: null, opacity: null, border: null })}
                className={cn(
                  "liquid-press rounded-lg px-3 py-2 text-sm font-medium",
                  current.glass === level ? "glass-2 text-foreground" : "text-muted-foreground hover:text-foreground",
                )}
              >
                {GLASS_LEVELS[level].label}
              </button>
            ))}
          </div>
          <p className="text-sm text-muted-foreground">{GLASS_LEVELS[current.glass].hint}</p>

          <fieldset className="space-y-5">
            <legend className="sr-only">Fine-tune</legend>
            {TUNE.map((t) => {
              const value = look[t.key];
              const disabled = current.glass === "off" && t.key !== "border";
              return (
                <div key={t.key} className={disabled ? "opacity-(--disabled-opacity)" : undefined}>
                  <div className="mb-2 flex items-center justify-between">
                    <Label htmlFor={`tune-${t.key}`} className="text-sm font-medium">
                      {t.label}
                    </Label>
                    <span className="text-xs tabular-nums text-muted-foreground" aria-live="polite">
                      {value}%
                    </span>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="w-14 shrink-0 text-xs text-muted-foreground">{t.low}</span>
                    <Slider
                      id={`tune-${t.key}`}
                      aria-label={t.label}
                      min={0}
                      max={100}
                      step={5}
                      value={[value]}
                      disabled={disabled}
                      onValueChange={([v]) => v !== undefined && preview({ ...current, [t.key]: v })}
                      onValueCommit={([v]) => v !== undefined && commit({ ...current, [t.key]: v })}
                    />
                    <span className="w-14 shrink-0 text-right text-xs text-muted-foreground">{t.high}</span>
                  </div>
                </div>
              );
            })}
          </fieldset>
        </CardContent>
      </Card>

      <div className="flex flex-wrap items-center justify-between gap-3 px-1">
        <p className="on-backdrop text-xs text-muted-foreground">Saved to your account and applied on every device you sign in on.</p>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => {
            commit(DEFAULT_APPEARANCE);
            toast.success("Appearance reset");
          }}
        >
          <RotateCcw aria-hidden /> Reset to default
        </Button>
      </div>
    </div>
  );
}
