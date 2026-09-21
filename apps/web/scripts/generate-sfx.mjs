// Generates the UI sound cues in public/sounds/ from a small synth, so every cue shares one
// sound design language (soft sine "glass" tones in E major pentatonic, fast attack,
// exponential decay, peaks around -12 dBFS). Run `node scripts/generate-sfx.mjs`; it writes
// 16-bit WAV masters and, when ffmpeg is on PATH, the MP3s the app actually loads.
import { execFileSync } from "node:child_process";
import { mkdirSync, writeFileSync, unlinkSync, statSync } from "node:fs";
import { join } from "node:path";

const RATE = 32_000;
const OUT = join(import.meta.dirname, "..", "public", "sounds");

// E major pentatonic — one key for the whole app keeps cues from clashing when they overlap.
const N = { E4: 329.63, F4: 349.23, GS4: 415.3, B4: 493.88, E5: 659.25, GS5: 830.61, B5: 987.77, E6: 1318.51, GS6: 1661.22 };

/** Additive sine tone with a touch of 2nd harmonic; `glideTo` slides the pitch over the note. */
function tone(buf, { at, freq, dur, gain = 0.5, attack = 0.004, decay = 0.25, harmonic = 0.18, glideTo = null, wave = "sine" }) {
  const start = Math.floor(at * RATE);
  const len = Math.floor(dur * RATE);
  let phase = 0;
  for (let i = 0; i < len && start + i < buf.length; i++) {
    const t = i / RATE;
    const f = glideTo === null ? freq : freq + (glideTo - freq) * Math.min(1, t / dur);
    phase += (2 * Math.PI * f) / RATE;
    const env = Math.min(1, t / attack) * Math.exp(-t / decay);
    let s = Math.sin(phase) + harmonic * Math.sin(2 * phase);
    if (wave === "triangle") s = (2 / Math.PI) * Math.asin(Math.sin(phase)) + harmonic * Math.sin(2 * phase);
    buf[start + i] += gain * env * s;
  }
}

/** Short filtered noise transient — the "touch" of a pop or a tick. */
function noise(buf, { at, dur, gain = 0.2, decay = 0.02 }) {
  const start = Math.floor(at * RATE);
  const len = Math.floor(dur * RATE);
  let lp = 0;
  for (let i = 0; i < len && start + i < buf.length; i++) {
    const t = i / RATE;
    lp += 0.25 * ((Math.random() * 2 - 1) - lp); // cheap one-pole low-pass
    buf[start + i] += gain * Math.exp(-t / decay) * lp;
  }
}

function render(seconds, draw) {
  const buf = new Float32Array(Math.ceil(seconds * RATE));
  draw(buf);
  // Normalise to -12 dBFS and add a 6 ms fade-out so nothing clicks at the tail.
  let peak = 1e-6;
  for (const v of buf) peak = Math.max(peak, Math.abs(v));
  const k = 0.25 / peak;
  const fade = Math.floor(0.006 * RATE);
  for (let i = 0; i < buf.length; i++) {
    const tail = buf.length - i;
    buf[i] = buf[i] * k * (tail < fade ? tail / fade : 1);
  }
  return buf;
}

function wav(samples) {
  const data = Buffer.alloc(samples.length * 2);
  for (let i = 0; i < samples.length; i++) data.writeInt16LE(Math.max(-32768, Math.min(32767, Math.round(samples[i] * 32767))), i * 2);
  const h = Buffer.alloc(44);
  h.write("RIFF", 0); h.writeUInt32LE(36 + data.length, 4); h.write("WAVE", 8);
  h.write("fmt ", 12); h.writeUInt32LE(16, 16); h.writeUInt16LE(1, 20); h.writeUInt16LE(1, 22);
  h.writeUInt32LE(RATE, 24); h.writeUInt32LE(RATE * 2, 28); h.writeUInt16LE(2, 32); h.writeUInt16LE(16, 34);
  h.write("data", 36); h.writeUInt32LE(data.length, 40);
  return Buffer.concat([h, data]);
}

const CUES = {
  // A note or task comes into existence: a quick, bright two-note pluck.
  create: render(0.35, (b) => {
    tone(b, { at: 0, freq: N.GS5, dur: 0.3, decay: 0.12, gain: 0.5 });
    tone(b, { at: 0.07, freq: N.B5, dur: 0.28, decay: 0.16, gain: 0.55 });
  }),
  // Autosave landed: the quietest cue in the set, a single glassy tick.
  save: render(0.16, (b) => {
    noise(b, { at: 0, dur: 0.02, gain: 0.35, decay: 0.006 });
    tone(b, { at: 0, freq: N.E6, dur: 0.15, decay: 0.045, gain: 0.5, harmonic: 0.1 });
  }),
  // Something was confirmed: two rising notes.
  success: render(0.45, (b) => {
    tone(b, { at: 0, freq: N.E5, dur: 0.35, decay: 0.16 });
    tone(b, { at: 0.11, freq: N.B5, dur: 0.34, decay: 0.2, gain: 0.55 });
  }),
  // A checklist item ticked: a soft pop with a tiny downward pitch bend.
  check: render(0.14, (b) => {
    noise(b, { at: 0, dur: 0.015, gain: 0.3, decay: 0.005 });
    tone(b, { at: 0, freq: 720, glideTo: 440, dur: 0.13, decay: 0.05, gain: 0.6, harmonic: 0.05 });
  }),
  // A task done: a three-note arpeggio that lands.
  "task-complete": render(0.55, (b) => {
    tone(b, { at: 0, freq: N.E5, dur: 0.3, decay: 0.14, gain: 0.45 });
    tone(b, { at: 0.09, freq: N.GS5, dur: 0.3, decay: 0.16, gain: 0.5 });
    tone(b, { at: 0.18, freq: N.B5, dur: 0.37, decay: 0.24, gain: 0.6 });
  }),
  // Archived / trashed / removed: a muted downward step.
  delete: render(0.4, (b) => {
    tone(b, { at: 0, freq: N.B4, dur: 0.25, decay: 0.12, gain: 0.5, harmonic: 0.08 });
    tone(b, { at: 0.12, freq: N.E4, dur: 0.28, decay: 0.18, gain: 0.55, harmonic: 0.05 });
  }),
  // Brought back (restore, reopen, version restore): an upward glide.
  restore: render(0.45, (b) => {
    tone(b, { at: 0, freq: N.E4, glideTo: N.B4, dur: 0.16, decay: 0.2, gain: 0.45 });
    tone(b, { at: 0.13, freq: N.B4, glideTo: N.E5, dur: 0.3, decay: 0.22, gain: 0.55 });
  }),
  // Something arrived for you: a two-note chime with a longer tail.
  notification: render(0.75, (b) => {
    tone(b, { at: 0, freq: N.B5, dur: 0.6, decay: 0.28, gain: 0.5 });
    tone(b, { at: 0.16, freq: N.E6, dur: 0.59, decay: 0.34, gain: 0.5 });
  }),
  // Something failed: a low, muted descending pair (triangle for a little body).
  error: render(0.4, (b) => {
    tone(b, { at: 0, freq: N.GS4, dur: 0.25, decay: 0.11, gain: 0.5, wave: "triangle", harmonic: 0.06 });
    tone(b, { at: 0.13, freq: N.F4, dur: 0.27, decay: 0.15, gain: 0.55, wave: "triangle", harmonic: 0.06 });
  }),
  // A tool connected / OAuth finished: a quick upward bloom of four notes.
  connect: render(0.6, (b) => {
    tone(b, { at: 0, freq: N.E5, dur: 0.4, decay: 0.2, gain: 0.4 });
    tone(b, { at: 0.06, freq: N.GS5, dur: 0.4, decay: 0.22, gain: 0.42 });
    tone(b, { at: 0.12, freq: N.B5, dur: 0.42, decay: 0.24, gain: 0.45 });
    tone(b, { at: 0.18, freq: N.E6, dur: 0.42, decay: 0.28, gain: 0.5 });
  }),
  // A tool disconnected: the bloom in reverse, shorter.
  disconnect: render(0.45, (b) => {
    tone(b, { at: 0, freq: N.E6, dur: 0.3, decay: 0.14, gain: 0.4 });
    tone(b, { at: 0.08, freq: N.B5, dur: 0.3, decay: 0.16, gain: 0.42 });
    tone(b, { at: 0.16, freq: N.E5, dur: 0.29, decay: 0.2, gain: 0.5 });
  }),
  // The assistant started working: an airy swell, barely there.
  "ai-start": render(0.45, (b) => {
    tone(b, { at: 0, freq: N.E5, dur: 0.45, attack: 0.12, decay: 0.2, gain: 0.4, harmonic: 0.05 });
    tone(b, { at: 0, freq: N.B5, dur: 0.45, attack: 0.14, decay: 0.2, gain: 0.3, harmonic: 0.05 });
    tone(b, { at: 0.05, freq: N.E6, dur: 0.4, attack: 0.15, decay: 0.18, gain: 0.14, harmonic: 0 });
  }),
  // The assistant finished: a light sparkle run.
  "ai-done": render(0.5, (b) => {
    [N.E5, N.GS5, N.B5, N.E6, N.GS6].forEach((f, i) => tone(b, { at: i * 0.04, freq: f, dur: 0.3, decay: 0.12 + i * 0.02, gain: 0.32 + i * 0.05, harmonic: 0.08 }));
  }),
};

mkdirSync(OUT, { recursive: true });
let ffmpeg = true;
for (const [name, samples] of Object.entries(CUES)) {
  const wavPath = join(OUT, `${name}.wav`);
  writeFileSync(wavPath, wav(samples));
  if (!ffmpeg) continue;
  try {
    execFileSync("ffmpeg", ["-y", "-loglevel", "error", "-i", wavPath, "-codec:a", "libmp3lame", "-b:a", "48k", "-ac", "1", join(OUT, `${name}.mp3`)]);
    unlinkSync(wavPath);
    console.log(`${name}.mp3`.padEnd(20), `${statSync(join(OUT, `${name}.mp3`)).size} bytes`);
  } catch (error) {
    ffmpeg = false;
    console.warn("ffmpeg not available — leaving WAV masters in place:", error.message.split("\n")[0]);
  }
}
