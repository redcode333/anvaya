import { describe, expect, it } from "vitest";
import { Vad, type VadEvent } from "./vad";

/** Runs a loudness trace of [level, milliseconds] segments at 40 ms per reading and collects every event with its time. */
function run(vad: Vad, trace: [number, number][], bot: (t: number) => boolean = () => false) {
  const out: { at: number; ev: VadEvent }[] = [];
  let t = 0;
  for (const [level, ms] of trace) {
    for (let i = 0; i < ms / 40; i++, t += 40) for (const ev of vad.push(level, t, bot(t))) out.push({ at: t, ev });
  }
  return out;
}
const events = (r: { ev: VadEvent }[]) => r.map((x) => x.ev);

const QUIET = 0.004, TALK = 0.15;

describe("Vad", () => {
  it("hears one utterance: start after the onset, end after the pause", () => {
    const r = run(new Vad(), [[QUIET, 1000], [TALK, 1500], [QUIET, 1500]]);
    expect(events(r)).toEqual(["start", "end"]);
  });

  it("keeps a short pause inside one utterance (a breath between words)", () => {
    const r = run(new Vad(), [[QUIET, 800], [TALK, 800], [QUIET, 500], [TALK, 800], [QUIET, 1500]]);
    expect(events(r)).toEqual(["start", "end"]);
  });

  it("splits two utterances separated by a long silence", () => {
    const r = run(new Vad(), [[QUIET, 500], [TALK, 800], [QUIET, 1500], [TALK, 800], [QUIET, 1500]]);
    expect(events(r)).toEqual(["start", "end", "start", "end"]);
  });

  it("drops a click that is too short to be speech", () => {
    const r = run(new Vad(), [[QUIET, 800], [TALK, 200], [QUIET, 1500]]);
    expect(events(r)).not.toContain("end");
  });

  it("ignores steady room noise and learns it as the floor", () => {
    const vad = new Vad();
    const r = run(vad, [[0.012, 5000]]);
    expect(events(r)).toEqual([]);
    expect(vad.noiseFloor).toBeGreaterThan(0.008);
  });

  it("does not take a noisy room for speech once the floor has risen", () => {
    const r = run(new Vad(), [[0.03, 4000], [0.035, 2000]]);
    expect(events(r)).not.toContain("end");
  });

  it("talking over the bot fires a barge-in together with the start", () => {
    const r = run(new Vad(), [[QUIET, 800], [TALK, 1200], [QUIET, 1500]], () => true);
    expect(events(r).slice(0, 2)).toEqual(["start", "barge"]);
  });

  it("the bot's own quieter echo does not count as talking over it", () => {
    const echo = 0.03;  // above the room bar, below the raised bar while the bot speaks
    const r = run(new Vad(), [[QUIET, 800], [echo, 3000]], () => true);
    expect(events(r)).toEqual([]);
  });

  it("a deliberate loud interruption needs a slightly longer onset than normal speech", () => {
    const talk = (bot: boolean) => run(new Vad(), [[QUIET, 800], [TALK, 1000], [QUIET, 1500]], () => bot).find((x) => x.ev === "start")!.at;
    expect(talk(true)).toBeGreaterThan(talk(false));
  });

  it("cuts a very long stretch of speech so it can be sent", () => {
    const r = run(new Vad({ maxUtteranceMs: 3000 }), [[QUIET, 800], [TALK, 6000]]);
    expect(events(r)).toContain("end");
  });

  it("after the person stops, nothing more fires until they talk again", () => {
    const vad = new Vad();
    run(vad, [[QUIET, 800], [TALK, 800], [QUIET, 1500]]);
    expect(vad.speaking).toBe(false);
    expect(events(run(vad, [[QUIET, 3000]]))).toEqual([]);
  });
});
