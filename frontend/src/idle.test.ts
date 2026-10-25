import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createIdleTimer } from "./idle";

describe("kiosk idle timeout", () => {
  beforeEach(() => { vi.useFakeTimers(); });
  afterEach(() => { vi.useRealTimers(); });

  const make = () => {
    const ev: string[] = [];
    const timer = createIdleTimer({ idleSeconds: 180, warningSeconds: 30, onWarn: () => ev.push("warn"),
      onActive: () => ev.push("active"), onTimeout: () => ev.push("end") });
    return { ev, timer };
  };

  it("warns 30 s before the end and then ends the session", () => {
    const { ev } = make();
    vi.advanceTimersByTime(149_000);
    expect(ev).toEqual([]);
    vi.advanceTimersByTime(1_000);
    expect(ev).toEqual(["warn"]);
    vi.advanceTimersByTime(29_000);
    expect(ev).toEqual(["warn"]);
    vi.advanceTimersByTime(1_000);
    expect(ev).toEqual(["warn", "end"]);
  });

  it("any input resets the countdown, also during the warning", () => {
    const { ev, timer } = make();
    vi.advanceTimersByTime(140_000);
    timer.activity();
    vi.advanceTimersByTime(149_000);
    expect(ev).toEqual([]);
    vi.advanceTimersByTime(1_000 + 20_000);
    timer.activity();
    expect(ev).toEqual(["warn", "active"]);
    vi.advanceTimersByTime(179_000);
    expect(ev).toEqual(["warn", "active", "warn"]);
  });

  it("does nothing after stop (session ended by the button)", () => {
    const { ev, timer } = make();
    timer.stop();
    vi.advanceTimersByTime(600_000);
    timer.activity();
    expect(ev).toEqual([]);
  });
});
