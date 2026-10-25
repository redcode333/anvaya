import { useEffect, useRef, useState, type CSSProperties } from "react";
import { HERO_LINES, heroIndexForLang, heroText, t, type HeroLine } from "../i18n";
import { useApp } from "../state";
import { usePrefersReducedMotion } from "../landing/motion";
import { useHeadlineRotation } from "./useHeadlineRotation";

type Word = { t: string; em: boolean };

// Latin scripts animate word by word. Devanagari and Telugu animate as one whole line: splitting them breaks
// conjuncts and vowel signs (matras).
function units(line: HeroLine): Word[][] {
  if (line.script === "indic") return [line.parts.map((p) => ({ t: p.t, em: !!p.em }))];
  const out: Word[][] = [];
  line.parts.forEach((p) => p.t.split(/\s+/).filter(Boolean).forEach((w) => out.push([{ t: w, em: !!p.em }])));
  return out;
}

/**
 * Rotating multilingual headline: Hinglish → हिंदी → English → తెలుగు.
 * The real <h1> is static (the visitor's language) and visually hidden; the rotating copy is aria-hidden so screen
 * readers don't hear it every few seconds. All lines share one grid cell, so the block is always as tall as the
 * tallest line at the current width: no measuring, no layout shift.
 */
export default function HeroHeadline({ onLineChange }: { onLineChange?: (line: HeroLine) => void }) {
  const { lang, setLang } = useApp();
  const reduced = usePrefersReducedMotion();
  const rot = useHeadlineRotation({ count: HERO_LINES.length, initial: heroIndexForLang(lang), reduced });
  const shown = reduced ? heroIndexForLang(lang) : rot.index;
  const [entered, setEntered] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const { pause, resume } = rot;

  useEffect(() => { const r = requestAnimationFrame(() => setEntered(true)); return () => cancelAnimationFrame(r); }, []);
  useEffect(() => { onLineChange?.(HERO_LINES[shown]); }, [shown, onLineChange]);

  useEffect(() => {
    const vis = () => (document.visibilityState === "hidden" ? pause("hidden") : resume("hidden"));
    vis();
    document.addEventListener("visibilitychange", vis);
    return () => document.removeEventListener("visibilitychange", vis);
  }, [pause, resume]);

  useEffect(() => {
    const el = box.current;
    if (!el || typeof IntersectionObserver === "undefined") return;
    const io = new IntersectionObserver((es) => (es.some((e) => e.isIntersecting) ? resume("offscreen") : pause("offscreen")));
    io.observe(el);
    return () => io.disconnect();
  }, [pause, resume]);

  // The site language changed elsewhere (top bar): a pinned headline follows it. Hinglish stays put for Hindi.
  const { pin, pinned } = rot;
  useEffect(() => {
    if (pinned && HERO_LINES[rot.index].uiLang !== lang) pin(heroIndexForLang(lang));
  }, [lang]); // eslint-disable-line react-hooks/exhaustive-deps

  const pick = (i: number) => { rot.pin(i); setLang(HERO_LINES[i].uiLang); };
  const playing = !reduced && !rot.pinned;

  return (
    <div className="hl" ref={box}
      onMouseEnter={() => pause("hover")} onMouseLeave={() => resume("hover")}
      onFocus={() => pause("focus")} onBlur={(e) => { if (!e.currentTarget.contains(e.relatedTarget as Node)) resume("focus"); }}>
      <h1 className="sr-only" lang={HERO_LINES[heroIndexForLang(lang)].lang}>{heroText(HERO_LINES[heroIndexForLang(lang)])}</h1>
      <div className="hl-stage" aria-hidden="true" data-testid="hl-stage">
        {HERO_LINES.map((line, i) => {
          const state = i !== shown || !entered ? "idle" : rot.phase === "out" && !reduced ? "out" : "in";
          const us = units(line);
          return (
            <div key={line.id} lang={line.lang} className={`hl-line hl-${line.script}`} data-state={state} data-line={line.id}>
              {us.map((u, k) => (
                <span key={k} className="hl-unit"
                  style={{ transitionDelay: state === "in" ? `${k * 50}ms` : state === "out" ? `${k * 40}ms` : "0ms" } as CSSProperties}>
                  {u.map((w, j) => <span key={j} className={w.em ? "hl-em" : undefined}>{w.t}</span>)}
                </span>
              ))}
            </div>
          );
        })}
      </div>
      <div className="hl-langs" role="group" aria-label={t("headlineLanguages", lang)}>
        {HERO_LINES.map((line, i) => {
          const active = i === shown;
          return (
            <button key={line.id} type="button" lang={line.lang} className="hl-lang" aria-pressed={active && rot.pinned}
              data-active={active || undefined} onClick={() => pick(i)}>
              {line.label}
              <span className="hl-track" aria-hidden="true" />
              {active && (
                <span key={rot.cycle} className="hl-bar" aria-hidden="true"
                  data-mode={rot.running ? "run" : rot.pinned || reduced ? "full" : "empty"} />
              )}
            </button>
          );
        })}
        {!reduced && (
          <button type="button" className="hl-play" onClick={rot.togglePlay}
            aria-label={playing ? t("pauseRotation", lang) : t("playRotation", lang)}>
            {playing
              ? <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><rect x="6" y="5" width="4" height="14" rx="1" /><rect x="14" y="5" width="4" height="14" rx="1" /></svg>
              : <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M7 5l12 7-12 7z" /></svg>}
          </button>
        )}
      </div>
    </div>
  );
}
