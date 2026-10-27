// Voice-activity detection for the hands-free call: turns a stream of microphone loudness readings into
// "the person started talking" / "finished" / "talked over the bot" events. Pure logic, no audio APIs, so it is tested
// with synthetic loudness traces. The loudness floor adapts to the room, and while the bot is speaking the bar is
// higher and the onset longer, so the bot's own voice leaking into the microphone does not cut itself off.

export type VadEvent = "start" | "end" | "discard" | "barge";

export type VadConfig = {
  minThreshold: number;     // never treat anything quieter than this as speech
  floorMultiple: number;    // speech must be this many times louder than the room's noise floor
  botMultiple: number;      // extra bar to clear while the bot is speaking (its own echo)
  onsetMs: number;          // loud for this long = the person started
  botOnsetMs: number;       // same, while the bot is speaking (talking over it must be deliberate)
  hangMs: number;           // quiet for this long = the person finished
  minSpeechMs: number;      // shorter than this is a cough or a click, dropped
  maxUtteranceMs: number;   // cut very long stretches so they are transcribed
};

export const DEFAULT_VAD: VadConfig = {
  minThreshold: 0.02, floorMultiple: 3.5, botMultiple: 1.8, onsetMs: 120, botOnsetMs: 260,
  hangMs: 1000, minSpeechMs: 300, maxUtteranceMs: 30000,
};

export class Vad {
  private cfg: VadConfig;
  private floor = 0.01;
  private aboveSince: number | null = null;
  private lastLoud = 0;
  private startedAt = 0;
  private inSpeech = false;

  constructor(cfg: Partial<VadConfig> = {}) { this.cfg = { ...DEFAULT_VAD, ...cfg }; }

  get speaking() { return this.inSpeech; }
  get noiseFloor() { return this.floor; }

  reset() { this.aboveSince = null; this.inSpeech = false; }

  /** Feed one loudness reading (0..1 RMS) taken at `now` ms; returns the events it caused, in order. */
  push(level: number, now: number, botSpeaking = false): VadEvent[] {
    const c = this.cfg;
    const bar = Math.max(c.minThreshold, this.floor * c.floorMultiple) * (botSpeaking ? c.botMultiple : 1);
    const events: VadEvent[] = [];
    if (!this.inSpeech) {
      if (level > bar) {
        if (this.aboveSince === null) this.aboveSince = now;
        if (now - this.aboveSince >= (botSpeaking ? c.botOnsetMs : c.onsetMs)) {
          this.inSpeech = true;
          this.startedAt = this.aboveSince;
          this.lastLoud = now;
          events.push("start");
          if (botSpeaking) events.push("barge");
        }
      } else {
        this.aboveSince = null;
        // Only quiet readings teach the floor, and slowly, so speech does not raise it.
        this.floor = Math.min(0.05, Math.max(0.002, this.floor * 0.95 + level * 0.05));
      }
      return events;
    }
    if (level > bar * 0.6) this.lastLoud = now;
    const forced = now - this.startedAt >= c.maxUtteranceMs;
    if (forced || now - this.lastLoud >= c.hangMs) {
      this.inSpeech = false;
      this.aboveSince = null;
      events.push(this.lastLoud - this.startedAt >= c.minSpeechMs ? "end" : "discard");
    }
    return events;
  }
}
