// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, renderHook, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { HERO_LINES } from "../i18n";
import { AppProvider, useApp } from "../state";
import HeroHeadline from "./HeroHeadline";
import { HOLD_MS, OUT_MS, useHeadlineRotation } from "./useHeadlineRotation";

const STEP = HOLD_MS + OUT_MS;

function setReducedMotion(on: boolean) {
  window.matchMedia = ((q: string) => ({
    matches: on && q.includes("reduce"), media: q, addEventListener: () => {}, removeEventListener: () => {},
  })) as any;
}
function setVisibility(v: "visible" | "hidden") {
  Object.defineProperty(document, "visibilityState", { value: v, configurable: true });
  document.dispatchEvent(new Event("visibilitychange"));
}
const shown = () => document.querySelector('.hl-line[data-state="in"], .hl-line[data-state="out"]')?.getAttribute("data-line");

beforeEach(() => { vi.useFakeTimers(); sessionStorage.clear(); setReducedMotion(false); setVisibility("visible"); });
afterEach(() => { cleanup(); vi.useRealTimers(); });

describe("useHeadlineRotation", () => {
  it("rotates Hinglish → Hindi → English → Telugu → Hinglish", () => {
    expect(HERO_LINES.map((l) => l.id)).toEqual(["hinglish", "hi", "en", "te"]);
    const { result } = renderHook(() => useHeadlineRotation({ count: 4, initial: 0, reduced: false }));
    const seen = [result.current.index];
    for (let i = 0; i < 4; i++) { act(() => { vi.advanceTimersByTime(STEP); }); seen.push(result.current.index); }
    expect(seen).toEqual([0, 1, 2, 3, 0]);
  });

  it("holds each line 3.2 s before it leaves", () => {
    const { result } = renderHook(() => useHeadlineRotation({ count: 4, reduced: false }));
    act(() => { vi.advanceTimersByTime(HOLD_MS - 10); });
    expect(result.current.phase).toBe("in");
    act(() => { vi.advanceTimersByTime(20); });
    expect(result.current.phase).toBe("out");
  });

  it("does not move while paused and resumes after", () => {
    const { result } = renderHook(() => useHeadlineRotation({ count: 4, reduced: false }));
    act(() => { result.current.pause("hidden"); });
    act(() => { vi.advanceTimersByTime(STEP * 3); });
    expect(result.current.index).toBe(0);
    act(() => { result.current.resume("hidden"); });
    act(() => { vi.advanceTimersByTime(STEP); });
    expect(result.current.index).toBe(1);
  });

  it("never rotates with reduced motion", () => {
    const { result } = renderHook(() => useHeadlineRotation({ count: 4, initial: 2, reduced: true }));
    act(() => { vi.advanceTimersByTime(STEP * 5); });
    expect(result.current.index).toBe(2);
  });
});

function LangProbe() { const { lang } = useApp(); return <output data-testid="ui-lang">{lang}</output>; }
const renderHero = () => render(<AppProvider><HeroHeadline /><LangProbe /></AppProvider>);

describe("HeroHeadline", () => {
  it("pauses when the tab is hidden", () => {
    sessionStorage.setItem("anvaya.lang", "hi"); // hi has no Hinglish UI; the visitor's line is हिंदी (index 1)
    renderHero();
    act(() => { vi.advanceTimersByTime(50); });
    expect(shown()).toBe("hi");
    act(() => { setVisibility("hidden"); });
    act(() => { vi.advanceTimersByTime(STEP * 3); });
    expect(shown()).toBe("hi");
    act(() => { setVisibility("visible"); });
    act(() => { vi.advanceTimersByTime(STEP); });
    expect(shown()).toBe("en");
  });

  it("clicking a language pins the headline on it and switches the UI language", () => {
    sessionStorage.setItem("anvaya.lang", "en");
    renderHero();
    fireEvent.click(screen.getByRole("button", { name: "తెలుగు" }));
    expect(screen.getByTestId("ui-lang").textContent).toBe("te");
    act(() => { vi.advanceTimersByTime(STEP * 3); });
    expect(shown()).toBe("te");
    expect(screen.getByRole("button", { name: "తెలుగు" }).getAttribute("aria-pressed")).toBe("true");
  });

  it("reduced motion shows only the visitor's language, without rotating", () => {
    setReducedMotion(true);
    sessionStorage.setItem("anvaya.lang", "te");
    renderHero();
    act(() => { vi.advanceTimersByTime(STEP * 4); });
    expect(shown()).toBe("te");
    expect(document.querySelectorAll('.hl-line[data-state="in"]').length).toBe(1);
    expect(screen.queryByRole("button", { name: /headline rotation/i })).toBeNull();
  });

  it("keeps a static, visually hidden h1 and hides the rotating copy from screen readers", () => {
    sessionStorage.setItem("anvaya.lang", "en");
    renderHero();
    const h1 = screen.getByRole("heading", { level: 1 });
    expect(h1.textContent).toBe("Speak, and find the schemes that are yours.");
    expect(h1.getAttribute("lang")).toBe("en");
    expect(screen.getByTestId("hl-stage").getAttribute("aria-hidden")).toBe("true");
    act(() => { vi.advanceTimersByTime(STEP); });
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("Speak, and find the schemes that are yours.");
  });

  it("gives every line its lang attribute and keeps Indic lines whole", () => {
    renderHero();
    const te = document.querySelector('.hl-line[data-line="te"]')!;
    expect(te.getAttribute("lang")).toBe("te");
    expect(te.querySelectorAll(".hl-unit").length).toBe(1); // no per-character / per-word splitting for Telugu
    expect(document.querySelector('.hl-line[data-line="hinglish"]')!.getAttribute("lang")).toBe("hi-Latn");
  });
});
