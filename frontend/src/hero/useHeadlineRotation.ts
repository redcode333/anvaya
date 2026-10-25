import { useCallback, useEffect, useState } from "react";

/** Why the rotation is paused. It runs only while there is no reason at all. */
export type PauseReason = "hover" | "focus" | "hidden" | "offscreen" | "user";

export const HOLD_MS = 3200; // each line stays this long
export const OUT_MS = 620; // outgoing words: 360 ms fade + 40 ms stagger, then the next line starts

type Opts = { count: number; initial?: number; reduced: boolean; holdMs?: number; outMs?: number };

/**
 * Drives the rotating hero headline: index of the visible line, its phase ("in" = shown, "out" = leaving),
 * and a `cycle` counter that changes whenever a new hold starts (used to restart the progress bar).
 * Reduced motion never rotates; a user pin ("user" reason) holds the line until play is pressed.
 */
export function useHeadlineRotation({ count, initial = 0, reduced, holdMs = HOLD_MS, outMs = OUT_MS }: Opts) {
  const [index, setIndex] = useState(initial);
  const [phase, setPhase] = useState<"in" | "out">("in");
  const [reasons, setReasons] = useState<ReadonlySet<PauseReason>>(() => new Set());
  const [cycle, setCycle] = useState(0);
  const running = !reduced && reasons.size === 0 && count > 1;

  useEffect(() => {
    if (!running) { setPhase("in"); return; }
    setCycle((c) => c + 1);
    const out = setTimeout(() => setPhase("out"), holdMs);
    const next = setTimeout(() => { setIndex((i) => (i + 1) % count); setPhase("in"); }, holdMs + outMs);
    return () => { clearTimeout(out); clearTimeout(next); };
  }, [running, index, count, holdMs, outMs]);

  const pause = useCallback((r: PauseReason) => setReasons((s) => (s.has(r) ? s : new Set(s).add(r))), []);
  const resume = useCallback((r: PauseReason) => setReasons((s) => {
    if (!s.has(r)) return s;
    const n = new Set(s); n.delete(r); return n;
  }), []);
  /** Show line i and hold it there (a click on the language indicator). */
  const pin = useCallback((i: number) => { setIndex(i); setPhase("in"); pause("user"); }, [pause]);
  const togglePlay = useCallback(() => setReasons((s) => {
    const n = new Set(s);
    if (n.has("user")) n.delete("user"); else n.add("user");
    return n;
  }), []);

  return { index, phase, running, cycle, pinned: reasons.has("user"), pause, resume, pin, togglePlay };
}
