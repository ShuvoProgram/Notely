import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// A minimal Web Audio double: enough to see what the player schedules and how it cleans up.
class FakeGain {
  gain = { value: 1, setTargetAtTime: vi.fn((v: number) => (this.gain.value = v)) };
  connect = vi.fn(() => this);
  disconnect = vi.fn();
}
class FakeSource {
  buffer: unknown = null;
  onended: (() => void) | null = null;
  connect = vi.fn((node: FakeGain) => node);
  disconnect = vi.fn();
  start = vi.fn(() => this.onended?.());
}
const created: FakeSource[] = [];
class FakeAudioContext {
  state: AudioContextState = "suspended";
  currentTime = 0;
  destination = {};
  resume = vi.fn(async () => {
    this.state = "running";
  });
  close = vi.fn(async () => undefined);
  createGain = () => new FakeGain();
  createBufferSource = () => {
    const s = new FakeSource();
    created.push(s);
    return s;
  };
  decodeAudioData = vi.fn(async (bytes: ArrayBuffer) => ({ length: bytes.byteLength }));
}

async function load() {
  vi.resetModules();
  return import("@/lib/sfx/player");
}

const flush = () => new Promise((r) => setTimeout(r, 0));

describe("sfx player", () => {
  beforeEach(() => {
    created.length = 0;
    localStorage.clear();
    Object.assign(window, { AudioContext: FakeAudioContext });
    vi.stubGlobal("fetch", vi.fn(async () => new Response(new ArrayBuffer(8), { status: 200 })));
    let t = 0;
    vi.spyOn(performance, "now").mockImplementation(() => (t += 1000)); // a second passes per call
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("stays silent until the user has interacted with the page", async () => {
    const { playSfx } = await load();
    expect(playSfx("success")).toBe(false);
    window.dispatchEvent(new Event("pointerdown"));
    expect(playSfx("success")).toBe(true);
    await flush();
    await flush();
    expect(created).toHaveLength(1);
    expect(created[0]!.disconnect).toHaveBeenCalled(); // released once it ended
  });

  it("is a no-op when sound is switched off, and honours the volume curve when on", async () => {
    const { playSfx, sfx } = await load();
    window.dispatchEvent(new Event("keydown"));
    sfx.configure({ enabled: false });
    expect(playSfx("task-complete")).toBe(false);
    sfx.configure({ enabled: true, volume: 0.5 });
    expect(playSfx("task-complete")).toBe(true);
    expect(JSON.parse(localStorage.getItem("notely.sound") ?? "{}")).toEqual({ enabled: true, volume: 0.5 });
  });

  it("throttles the same cue and never lets a missing file throw", async () => {
    vi.spyOn(performance, "now").mockImplementation(() => 5000); // time stands still
    vi.stubGlobal("fetch", vi.fn(async () => new Response(null, { status: 404 })));
    const { playSfx } = await load();
    window.dispatchEvent(new Event("pointerdown"));
    expect(playSfx("save")).toBe(true);
    expect(playSfx("save")).toBe(false); // inside minGap
    expect(playSfx("error")).toBe(false); // inside the global gap
    await flush();
    await flush();
    expect(created).toHaveLength(0); // 404 → nothing scheduled, no exception
  });
});
