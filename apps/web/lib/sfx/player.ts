import { DEFAULT_SOUND, SFX, type SfxName, type SoundPreference } from "@/lib/sfx/catalog";

export type { SfxName, SoundPreference } from "@/lib/sfx/catalog";

const STORAGE_KEY = "notely.sound";
// Two different cues fired within this window collapse into the first one — a "save" landing
// while a "task-complete" is still ringing should not turn into a chord.
const GLOBAL_GAP_MS = 90;

/**
 * The one place audio is played from. Everything else calls `playSfx(name)`.
 *
 * - Lazy: no AudioContext exists until the first cue, and cues before the first user gesture
 *   are dropped rather than queued, so nothing ever plays on load.
 * - Quiet: per-cue and global throttles, a master gain from the user's preference, and a
 *   hard "enabled" switch that short-circuits before any work happens.
 * - Safe: a cue whose file cannot be fetched or decoded is remembered as missing and never
 *   retried in a loop; source nodes disconnect themselves when they end.
 */
class SfxPlayer {
  private ctx: AudioContext | null = null;
  private master: GainNode | null = null;
  private buffers = new Map<SfxName, Promise<AudioBuffer | null>>();
  private lastPlayed = new Map<SfxName, number>();
  private lastAny = 0;
  private prefs: SoundPreference = DEFAULT_SOUND;
  private unlocked = false;
  private listening = false;

  constructor() {
    if (typeof window !== "undefined") {
      this.prefs = readStored();
      this.listen();
    }
  }

  get preference(): SoundPreference {
    return this.prefs;
  }

  /** Apply a preference (from the signed-in user or the settings form) and remember it locally. */
  configure(prefs: Partial<SoundPreference>): void {
    this.prefs = { ...this.prefs, ...prefs, volume: clamp(prefs.volume ?? this.prefs.volume) };
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(this.prefs));
    } catch {
      // private mode / blocked storage: the in-memory value still applies for this session
    }
    if (this.master && this.ctx) this.master.gain.setTargetAtTime(this.prefs.enabled ? curve(this.prefs.volume) : 0, this.ctx.currentTime, 0.02);
  }

  /** Play a cue. Never throws; returns whether it was actually scheduled. */
  play(name: SfxName): boolean {
    if (typeof window === "undefined") return false;
    if (!this.prefs.enabled || this.prefs.volume <= 0) return false;
    if (!this.unlocked) return false; // browsers block audio before a gesture; don't queue it
    const now = performance.now();
    const cue = SFX[name];
    if (now - (this.lastPlayed.get(name) ?? -Infinity) < cue.minGapMs) return false;
    if (now - this.lastAny < GLOBAL_GAP_MS) return false;
    this.lastPlayed.set(name, now);
    this.lastAny = now;
    void this.schedule(name, cue.gain);
    return true;
  }

  /** Fetch the most common cues ahead of time so the first one is not late. */
  warm(names: SfxName[]): void {
    if (typeof window === "undefined" || !this.prefs.enabled) return;
    for (const n of names) void this.load(n);
  }

  /** Release the AudioContext (tests, hot reload). A later play() creates a new one. */
  dispose(): void {
    void this.ctx?.close().catch(() => undefined);
    this.ctx = null;
    this.master = null;
    this.buffers.clear();
  }

  private listen(): void {
    if (this.listening) return;
    this.listening = true;
    const unlock = () => {
      this.unlocked = true;
      // Resume an already-created context on the gesture the browser requires for it.
      if (this.ctx?.state === "suspended") void this.ctx.resume().catch(() => undefined);
    };
    for (const type of ["pointerdown", "keydown", "touchend"] as const) {
      window.addEventListener(type, unlock, { passive: true, capture: true });
    }
  }

  private context(): AudioContext | null {
    if (this.ctx) return this.ctx;
    const Ctor = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!Ctor) return null;
    try {
      this.ctx = new Ctor({ latencyHint: "interactive" });
    } catch {
      return null;
    }
    this.master = this.ctx.createGain();
    this.master.gain.value = this.prefs.enabled ? curve(this.prefs.volume) : 0;
    this.master.connect(this.ctx.destination);
    return this.ctx;
  }

  private load(name: SfxName): Promise<AudioBuffer | null> {
    const cached = this.buffers.get(name);
    if (cached) return cached;
    const ctx = this.context();
    if (!ctx) return Promise.resolve(null);
    const p = fetch(`/sounds/${name}.mp3`, { cache: "force-cache" })
      .then((r) => (r.ok ? r.arrayBuffer() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((bytes) => ctx.decodeAudioData(bytes))
      .catch((error: unknown) => {
        if (process.env.NODE_ENV !== "production") console.warn(`[sfx] could not load "${name}":`, error);
        return null;
      });
    this.buffers.set(name, p);
    return p;
  }

  private async schedule(name: SfxName, gain: number): Promise<void> {
    const ctx = this.context();
    if (!ctx || !this.master) return;
    if (ctx.state === "suspended") {
      try {
        await ctx.resume();
      } catch {
        return;
      }
      if ((ctx.state as AudioContextState) !== "running") return; // resume() can resolve while still blocked
    }
    const buffer = await this.load(name);
    if (!buffer || !this.prefs.enabled) return;
    const source = ctx.createBufferSource();
    source.buffer = buffer;
    const level = ctx.createGain();
    level.gain.value = gain;
    source.connect(level).connect(this.master);
    source.onended = () => {
      source.disconnect();
      level.disconnect();
    };
    source.start();
  }
}

/** Perceptual volume: a slider at 50% should sound about half as loud, not half the amplitude. */
function curve(volume: number): number {
  return clamp(volume) ** 2;
}

function clamp(v: number): number {
  return Number.isFinite(v) ? Math.min(1, Math.max(0, v)) : DEFAULT_SOUND.volume;
}

function readStored(): SoundPreference {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_SOUND;
    const parsed = JSON.parse(raw) as Partial<SoundPreference>;
    return { enabled: parsed.enabled ?? DEFAULT_SOUND.enabled, volume: clamp(parsed.volume ?? DEFAULT_SOUND.volume) };
  } catch {
    return DEFAULT_SOUND;
  }
}

export const sfx = new SfxPlayer();

/** `playSfx("task-complete")` — the whole public API for components. */
export function playSfx(name: SfxName): boolean {
  return sfx.play(name);
}
