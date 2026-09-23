import type { ResolvedLook } from "@/lib/appearance/model";

/*
 * Writing a look onto the page: data attributes and three custom properties on <html>, which the
 * stylesheet reads. No component re-renders when the look changes.
 *
 * The look is also cached in this browser so the pre-paint script in the root layout can apply
 * it before first paint (no flash of the default background on refresh).
 */

export const LOOK_KEY = "notely.appearance.v2";
/** Storage used by the retired background system (custom uploads, CSS presets). */
const RETIRED_KEYS = ["notely.appearance.look", "notely.appearance.image"];

export function applyLook(look: ResolvedLook): void {
  const root = document.documentElement;
  root.dataset.bg = look.background;
  root.dataset.glass = look.glass;
  root.style.setProperty("--glass-blur", String(look.blur / 100));
  root.style.setProperty("--glass-opacity", String(look.opacity / 100));
  root.style.setProperty("--glass-edge", String(look.border / 100));
  try {
    window.localStorage.setItem(LOOK_KEY, JSON.stringify(look));
  } catch {
    // Private mode or full storage: the look still applies, it just isn't pre-painted next time.
  }
}

/** Remove what the old background system left in this browser (including uploaded images). */
export function forgetRetiredStorage(): void {
  try {
    for (let i = window.localStorage.length - 1; i >= 0; i--) {
      const key = window.localStorage.key(i);
      if (key && RETIRED_KEYS.some((k) => key === k || key.startsWith(`${k}.`))) window.localStorage.removeItem(key);
    }
  } catch {
    // Storage unavailable: nothing to clean.
  }
}

/**
 * Runs before hydration. Keep it tiny, dependency-free and defensive: any failure simply leaves
 * the stylesheet defaults (the default background, medium glass) in place.
 */
export const PREPAINT_SCRIPT = `(function(){try{var l=JSON.parse(localStorage.getItem(${JSON.stringify(LOOK_KEY)})||"null");if(!l)return;var r=document.documentElement;r.dataset.bg=l.background;r.dataset.glass=l.glass;r.style.setProperty("--glass-blur",l.blur/100);r.style.setProperty("--glass-opacity",l.opacity/100);r.style.setProperty("--glass-edge",l.border/100)}catch(e){}})();`;
