import { useEffect, useRef, useState } from "react";
import { prefersReducedMotion } from "./motion";

const STEP = 1700;
const END = 12400;
const ITEMS = ["Register with mobile number", "Create a password", "Log in", "Find the right department", "Search 800+ services", "Read eligibility PDFs", "Guess"];
const SENTENCE = "Gaya se hoon, umar 58, kheti karta hoon, pension nahi milti.";
const RESULTS = [
  { n: "PM-KISAN", b: "Eligible", tone: "ok" }, { n: "PM Fasal Bima", b: "Eligible", tone: "ok" }, { n: "Bihar Vridhjan Pension", b: "From age 60", tone: "later" },
];

/** Illustrative side-by-side: seven portal steps vs one spoken sentence. Starts when 40% is on screen. */
export default function PortalRace() {
  const root = useRef<HTMLDivElement>(null);
  const [ms, setMs] = useState(0);
  const iv = useRef<number>();

  const run = () => {
    window.clearInterval(iv.current);
    if (prefersReducedMotion()) { setMs(END); return; }
    setMs(0);
    iv.current = window.setInterval(() => setMs((m) => {
      const n = Math.min(END, m + 100);
      if (n >= END) window.clearInterval(iv.current);
      return n;
    }), 100);
  };

  useEffect(() => {
    const el = root.current;
    if (!el || typeof IntersectionObserver === "undefined") { run(); return; }
    const io = new IntersectionObserver((es) => { if (es.some((e) => e.isIntersecting)) { run(); io.disconnect(); } }, { threshold: 0.4 });
    io.observe(el);
    return () => { io.disconnect(); window.clearInterval(iv.current); };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const doneN = Math.min(7, Math.floor(ms / STEP));
  const listening = ms > 0 && ms < 1200;
  const chars = ms < 1200 ? 0 : Math.min(SENTENCE.length, Math.floor((SENTENCE.length * (ms - 1200)) / 1400));
  const rightDone = ms >= 2700;
  const leftDone = doneN >= 7;

  return (
    <div className="race" ref={root}>
      <div className="race-grid">
        <article className="race-card portal">
          <header><div><span className="race-k">The usual way</span><h3>Sarkari portal</h3></div><span className="race-pill">English-first</span></header>
          <ol>
            {ITEMS.map((t, k) => {
              const done = k < doneN, active = k === doneN && ms > 0 && !leftDone;
              return (
                <li key={t} data-state={done ? "done" : active ? "active" : "todo"}>
                  <span className="race-ic" aria-hidden="true">{done ? "✓" : active ? <span className="spin-ring small" /> : <span className="race-todo" />}</span>
                  <span>{t}</span>
                </li>
              );
            })}
          </ol>
          <footer><b>{ms === 0 ? "Ready" : leftDone ? "All 7 steps — still guessing" : `Step ${doneN + 1} of 7`}</b><span>~7 steps, English-first</span></footer>
        </article>
        <article className="race-card anvaya">
          <header><div><span className="race-k em">The Anvaya way</span><h3>Anvaya</h3></div><span className="race-pill warm">Your language</span></header>
          <div className="race-wave" aria-hidden="true">
            {Array.from({ length: 22 }, (_, i) => {
              const h = listening ? 5 + 22 * Math.abs(Math.sin(ms / 90 + i * 0.8)) * (0.4 + 0.6 * Math.abs(Math.sin(i * 1.7 + ms / 400))) : 4;
              return <span key={i} style={{ transform: `scaleY(${(h / 28).toFixed(3)})`, opacity: listening ? 1 : 0.3 }} />;
            })}
          </div>
          <p className="race-sentence">{SENTENCE.slice(0, chars)}<span className="race-caret" style={{ opacity: ms > 0 && ms < 2600 ? 1 : 0 }} /></p>
          <div className="race-results">
            {RESULTS.map((r, k) => (
              <div key={r.n} data-on={ms >= 2700 + k * 160 || undefined}><b>✓ {r.n}</b><span className={`demo-badge ${r.tone}`}>{r.b}</span></div>
            ))}
          </div>
          <footer>
            <b>{ms === 0 ? "Ready" : rightDone ? "Done — 3 schemes found" : listening ? "Listening…" : "Understanding…"}</b>
            <span>1 sentence, your language</span>
            <span className="race-lag" style={{ opacity: rightDone ? 1 : 0 }}>{leftDone ? "Anvaya was done back at step 2." : `The portal is still on step ${doneN + 1}.`}</span>
          </footer>
        </article>
      </div>
      <div className="race-foot">
        <span>Illustrative timing, not a benchmark.</span>
        <button type="button" className="l-btn ghost" onClick={run}>Replay the race</button>
      </div>
    </div>
  );
}
