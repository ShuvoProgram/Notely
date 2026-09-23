"use client";

import { Volume1, Volume2, VolumeX } from "@/components/icons";
import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { messageFor } from "@/features/auth/components/auth-form-error";
import { useCurrentUser, useUpdateProfile } from "@/features/auth/hooks";
import { DEFAULT_SOUND } from "@/lib/sfx/catalog";
import { playSfx, sfx } from "@/lib/sfx/player";

/**
 * Sound effects: one switch, one volume. Changes apply to the player instantly (so the preview
 * you hear is what you get) and are saved per user, so they follow you to other devices.
 */
export function SoundSettings() {
  const { data: user, isPending } = useCurrentUser();
  const update = useUpdateProfile();
  const saved = user?.sound ?? DEFAULT_SOUND;
  // Local value while dragging or saving; the server copy takes over once it matches.
  const [volume, setVolume] = React.useState<number | null>(null);
  const shown = volume ?? saved.volume;

  const persist = (next: { enabled?: boolean; volume?: number }) => {
    const sound = { enabled: next.enabled ?? saved.enabled, volume: next.volume ?? shown };
    sfx.configure(sound);
    update.mutate(
      { sound },
      {
        // Keep the local value until the server has it, so quick successive nudges stack.
        onSuccess: () => setVolume(null),
        onError: (e) => toast.error(messageFor(e)),
      },
    );
  };

  if (isPending || !user) return null;
  const Icon = !saved.enabled || shown === 0 ? VolumeX : shown < 0.5 ? Volume1 : Volume2;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Sound effects</CardTitle>
        <CardDescription>Short, quiet cues when something completes — a save, a finished task, a reply from the assistant. Never on navigation or typing.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="flex items-center justify-between gap-4">
          <div className="min-w-0">
            <Label htmlFor="sound-enabled" className="text-sm font-medium">
              Play sounds
            </Label>
            <p className="text-xs text-muted-foreground">Off means completely silent. Visual feedback stays the same.</p>
          </div>
          <Switch
            id="sound-enabled"
            checked={saved.enabled}
            disabled={update.isPending}
            onCheckedChange={(enabled) => {
              persist({ enabled });
              if (enabled) window.setTimeout(() => playSfx("success"), 60);
            }}
          />
        </div>
        <div className={saved.enabled ? undefined : "opacity-(--disabled-opacity)"}>
          <div className="mb-2 flex items-center justify-between">
            <Label htmlFor="sound-volume" className="text-sm font-medium">
              Volume
            </Label>
            <span className="tabular-nums text-xs text-muted-foreground" aria-live="polite">
              {Math.round(shown * 100)}%
            </span>
          </div>
          <div className="flex items-center gap-3">
            <Icon className="size-4 shrink-0 text-muted-foreground" aria-hidden />
            <Slider
              id="sound-volume"
              aria-label="Sound volume"
              min={0}
              max={100}
              step={5}
              value={[Math.round(shown * 100)]}
              disabled={!saved.enabled}
              onValueChange={([v]) => {
                if (v === undefined) return;
                setVolume(v / 100);
                sfx.configure({ volume: v / 100 }); // preview follows the thumb
              }}
              onValueCommit={([v]) => {
                if (v === undefined) return;
                persist({ volume: v / 100 });
                playSfx("success");
              }}
            />
            <Button type="button" variant="outline" size="sm" disabled={!saved.enabled} onClick={() => playSfx("task-complete")}>
              Preview
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
