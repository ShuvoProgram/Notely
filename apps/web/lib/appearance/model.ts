import type { Appearance, BackgroundId, GlassLevel } from "@/lib/api/types";

/*
 * Workspace appearance: which approved background sits behind the app, and how much of it shows
 * through the glass. The only backgrounds are the images in `public/assets`; there is no upload.
 *
 *   background image ─▶ scrim ─▶ glass nav/header ─▶ glass cards ─▶ popovers ─▶ dialogs
 *
 * The page reads everything from <html>: `data-bg` picks the image and its scrim (globals.css),
 * `data-glass` and three 0–1 custom properties set the glass strength (see `apply.ts`).
 * "tone" is how bright the picture is; it drives the scrim and the theme hint in Settings.
 */

export type Tone = "dark" | "mid" | "light";

export interface Background {
  id: BackgroundId;
  label: string;
  /** File in `public/assets`. */
  file: string;
  tone: Tone;
}

export const BACKGROUNDS: Background[] = [
  { id: "starry-moss", label: "Starry moss", file: "bg-2.png", tone: "dark" },
  { id: "forest", label: "Sunlit forest", file: "bg-1.png", tone: "mid" },
  { id: "mountain-lake", label: "Mountain lake", file: "bg-4.png", tone: "light" },
  { id: "meadow", label: "Meadow sky", file: "bg-5.png", tone: "light" },
  { id: "mossy-branch", label: "Mossy branch", file: "bg-3.png", tone: "light" },
];

export const DEFAULT_APPEARANCE: Appearance = {
  background: "starry-moss",
  glass: "medium",
  blur: null,
  opacity: null,
  border: null,
};

export const backgroundById = (id: BackgroundId): Background => BACKGROUNDS.find((b) => b.id === id) ?? BACKGROUNDS[0]!;

/** The image served through Next's optimiser (sized WebP), never the multi-megabyte original. */
export const imageUrl = (bg: Background, width: 384 | 1080 | 1920) => `/_next/image?url=${encodeURIComponent(`/assets/${bg.file}`)}&w=${width}&q=75`;

/** What each glass level means, as 0–100 values for the three fine-tune sliders. */
export const GLASS_LEVELS: Record<GlassLevel, { label: string; hint: string; blur: number; opacity: number; border: number }> = {
  off: { label: "Off", hint: "Solid surfaces, no blur. Easiest to read, lightest on battery.", blur: 0, opacity: 100, border: 50 },
  subtle: { label: "Subtle", hint: "Mostly solid, with a hint of the background.", blur: 35, opacity: 80, border: 45 },
  medium: { label: "Medium", hint: "Balanced frosted glass. The default.", blur: 60, opacity: 55, border: 55 },
  strong: { label: "Strong", hint: "Clearer glass that lets the background lead.", blur: 85, opacity: 30, border: 70 },
};

export interface ResolvedLook {
  background: BackgroundId;
  glass: GlassLevel;
  blur: number;
  opacity: number;
  border: number;
}

/** Turn a saved preference into what the page needs. */
export function resolve(a: Appearance): ResolvedLook {
  const level = GLASS_LEVELS[a.glass];
  const border = a.border ?? level.border;
  if (a.glass === "off") return { background: a.background, glass: "off", blur: 0, opacity: 100, border };
  return { background: a.background, glass: a.glass, blur: a.blur ?? level.blur, opacity: a.opacity ?? level.opacity, border };
}
