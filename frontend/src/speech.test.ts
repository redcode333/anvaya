import { beforeAll, describe, expect, it, vi } from "vitest";

let speech: typeof import("./speech");
let ApiError: typeof import("./api").ApiError;

beforeAll(async () => {
  // api.ts reads sessionStorage at import; speech.ts checks window for browser speech.
  vi.stubGlobal("sessionStorage", { getItem: () => null, setItem: () => undefined, removeItem: () => undefined });
  vi.stubGlobal("window", { webkitSpeechRecognition: function Rec() {} });
  vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, json: async () => ({ verbx_configured: true }) })));
  ({ ApiError } = await import("./api"));
  speech = await import("./speech");
});

describe("VerbX speech falls back to browser speech", () => {
  it("uses VerbX when the backend reports it configured", async () => {
    expect(await speech.voiceProvider()).toBe("verbx");
  });

  it("an empty clip (no_speech) keeps VerbX", async () => {
    expect(speech.noteVerbxError(new ApiError("VOICE_UNAVAILABLE", "No speech", 503, { reason: "no_speech" }))).toBe(false);
    expect(await speech.voiceProvider()).toBe("verbx");
  });

  it("an unintelligible clip (noise, wrong language) keeps VerbX too", async () => {
    expect(speech.noteVerbxError(new ApiError("VOICE_UNAVAILABLE", "unclear", 503, { reason: "unintelligible" }))).toBe(false);
    expect(await speech.voiceProvider()).toBe("verbx");
  });

  it("a VerbX outage switches to browser speech for the rest of the visit", async () => {
    expect(speech.noteVerbxError(new ApiError("VOICE_UNAVAILABLE", "down", 503, { reason: "http_500" }))).toBe(true);
    expect(speech.verbxFailedOver()).toBe(true);
    expect(await speech.voiceProvider()).toBe("browser");
  });
});

describe("read-aloud never blocks and degrades to text", () => {
  const played: string[] = [];
  class FakeAudio {
    onended: (() => void) | null = null;
    onerror: (() => void) | null = null;
    constructor(public src: string) {}
    play() { played.push(atob(this.src.split(",")[1])); setTimeout(() => this.onended?.(), 0); return Promise.resolve(); }
    pause() {}
  }
  const clip = (text: string) => ({ ok: true, json: async () => ({ audio_base64: btoa(text), mime_type: "audio/wav" }) });
  const textOf = (init: any) => JSON.parse(init.body).text as string;

  beforeAll(() => vi.stubGlobal("Audio", FakeAudio));

  it("plays every sentence in order, requesting them all at once", async () => {
    played.length = 0;
    const requested: string[] = [];
    vi.stubGlobal("fetch", vi.fn(async (_u: string, init: any) => {
      requested.push(textOf(init));
      // the first sentence is the slowest: playback order must still follow the text
      await new Promise((r) => setTimeout(r, textOf(init) === "One." ? 20 : 1));
      return clip(textOf(init));
    }));
    expect(await speech.speak("verbx", "S1", ["One.", "Two.", "Three."], "en")).toBe("verbx");
    expect(requested).toEqual(["One.", "Two.", "Three."]);
    expect(played).toEqual(["One.", "Two.", "Three."]);
  });

  it("a clip slower than 8 s ends playback as 'unavailable'", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("fetch", vi.fn((_u: string, init: any) => new Promise((_, reject) =>
      init.signal.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError"))))));
    const res = speech.speak("verbx", "S1", "Slow sentence.", "hi");
    await vi.advanceTimersByTimeAsync(speech.TTS_WAIT_MS + 10);
    expect(await res).toBe("unavailable");
    vi.useRealTimers();
  });

  it("a TTS error gives 'unavailable' (no browser voice, the text stays on screen)", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: false, status: 503, statusText: "x",
      json: async () => ({ error: { code: "VOICE_UNAVAILABLE", message: "down", details: { reason: "http_500" } } }) })));
    expect(await speech.speak("verbx", "S1", ["Hello."], "te")).toBe("unavailable");
  });

  it("starting new speech cancels the previous one", async () => {
    vi.stubGlobal("fetch", vi.fn(async (_u: string, init: any) => { await new Promise((r) => setTimeout(r, 5)); return clip(textOf(init)); }));
    const first = speech.speak("verbx", "S1", ["Old."], "en");
    const second = speech.speak("verbx", "S1", ["New."], "en");
    expect(await first).toBe("cancelled");
    expect(await second).toBe("verbx");
  });
});
