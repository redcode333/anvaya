// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const audio = vi.hoisted(() => {
  const subs = new Set<() => void>();
  return { on: false, stop: vi.fn(), subs, set(v: boolean) { this.on = v; subs.forEach((f) => f()); } };
});
vi.mock("./speech", () => ({
  isSpeaking: () => audio.on, subscribeSpeaking: (f: () => void) => { audio.subs.add(f); return () => audio.subs.delete(f); },
  stopSpeaking: () => { audio.stop(); audio.set(false); },
}));
vi.mock("./state", () => ({ useApp: () => ({ lang: "en" }) }));

import { CopyButton, ListenButton, StopAudioPill } from "./ListenControls";

afterEach(() => { cleanup(); audio.on = false; audio.stop.mockClear(); });

describe("read-aloud controls", () => {
  it("a listen button plays, becomes Stop while audio runs, and stops it on the next tap", () => {
    const play = vi.fn(() => audio.set(true));
    render(<ListenButton label="Listen to summary" onPlay={play} />);
    fireEvent.click(screen.getByRole("button", { name: /Listen to summary/ }));
    expect(play).toHaveBeenCalledTimes(1);
    const stop = screen.getByRole("button", { name: /Stop/ });
    expect(stop.getAttribute("aria-pressed")).toBe("true");
    fireEvent.click(stop);
    expect(audio.stop).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: /Listen to summary/ })).toBeTruthy();
    expect(play).toHaveBeenCalledTimes(1);  // the stop tap did not start it again
  });

  it("the floating Stop pill shows only while something is playing, and stops it", () => {
    render(<StopAudioPill />);
    expect(screen.queryByRole("button", { name: /Stop/ })).toBeNull();
    act(() => audio.set(true));
    fireEvent.click(screen.getByRole("button", { name: /Stop/ }));
    expect(audio.stop).toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: /Stop/ })).toBeNull();
  });

  it("every listen button on the page flips to Stop when any audio plays", () => {
    render(<><ListenButton label="One" onPlay={() => {}} /><ListenButton label="Two" onPlay={() => {}} /></>);
    act(() => audio.set(true));
    expect(screen.getAllByRole("button", { name: /Stop/ })).toHaveLength(2);
  });
});

describe("copy button", () => {
  it("copies the text and confirms", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    render(<CopyButton text="PSP-E19B-ZWJD" label="Copy code" />);
    fireEvent.click(screen.getByRole("button", { name: /Copy code/ }));
    await waitFor(() => expect(screen.getByRole("button").textContent).toMatch(/Copied/));
    expect(writeText).toHaveBeenCalledWith("PSP-E19B-ZWJD");
  });
});
