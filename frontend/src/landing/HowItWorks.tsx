import { useEffect, useRef, useState, type ReactNode } from "react";
import { MicIcon } from "./DemoCard";

const STEPS: { n: string; title: ReactNode; body: string }[] = [
  { n: "01", title: <>Speak <em className="l-em">naturally.</em></>, body: "Ramble, pause, switch languages. Anvaya gets what you mean." },
  { n: "02", title: <>Anvaya <em className="l-em">understands.</em></>, body: "It pulls out age, state, income and occupation, and asks only what’s missing." },
  { n: "03", title: <>Get <em className="l-em">your</em> schemes.</>, body: "Eligibility, documents and where to apply, read aloud and on screen." },
];

const WAVE = [6, 12, 20, 30, 22, 14, 26, 36, 28, 18, 10, 24, 34, 40, 30, 18, 12, 22, 28, 16, 10, 14, 8, 5];

function ScreenSpeak() {
  return (
    <div className="ph-screen">
      <div className="ph-top"><b>Anvaya</b><span className="ph-pill">Auto-detect</span></div>
      <div className="ph-bubbles">
        <div className="ph-me"><span>Main Gaya se hoon… umar 58 hai</span><small>Hinglish</small></div>
        <div className="ph-me"><span>I do farming, two acres.</span><small>English</small></div>
        <div className="ph-me"><span lang="hi">पेंशन नहीं मिलती।</span><small>हिंदी</small></div>
      </div>
      <div className="ph-wave" aria-hidden="true">{WAVE.map((h, i) => <span key={i} style={{ transform: `scaleY(${h / 40})` }} />)}</div>
      <div className="ph-mic"><span><MicIcon size={22} /></span><small>Sun raha hoon…</small></div>
    </div>
  );
}
function ScreenUnderstand() {
  const chips: [string, string][] = [["Age", "58"], ["District", "Gaya"], ["State", "Bihar"], ["Work", "Farmer"], ["Land", "2 acre"], ["Pension", "None"]];
  return (
    <div className="ph-screen">
      <div className="ph-top"><b>Samjha</b><small>from what you said</small></div>
      <div className="ph-chips">
        {chips.map(([k, v]) => <span key={k}><i>{k}</i> <b>{v}</b></span>)}
        <span className="ask"><i>Income</i> <b>?</b></span>
      </div>
      <div className="ph-spacer" />
      <div className="ph-bot">Ek baat aur — kya aapke paas BPL card hai?</div>
      <div className="ph-answers">
        <span>Haan</span><span>Nahi</span><span>Pata nahi</span>
      </div>
    </div>
  );
}
function ScreenSchemes() {
  return (
    <div className="ph-screen">
      <div className="ph-top"><b>3 yojanayein mili</b><span className="ph-ok" /></div>
      <div className="ph-card"><div><b>PM-KISAN</b><span className="b ok">Eligible</span></div><small><b>₹6,000 a year</b> · Aadhaar, land record, passbook</small></div>
      <div className="ph-card"><div><b>PM Fasal Bima</b><span className="b ok">Eligible</span></div><small><b>2% premium</b> · apply via bank or CSC</small></div>
      <div className="ph-card"><div><b>Vridhjan Pension</b><span className="b later">From 60</span></div><small>Bihar · you can apply in 2 years</small></div>
      <div className="ph-spacer" />
      <div className="ph-listen">Phir se suniye</div>
      <small className="ph-disc">Pre-screening only. Final approval by department.</small>
    </div>
  );
}

/**
 * Three steps. On ≥768px the section is pinned: the phone stays centred and scrolling advances the steps.
 * Below 768px it is a plain vertical stepper, each step with its own screen.
 */
export default function HowItWorks() {
  const wrap = useRef<HTMLDivElement>(null);
  const [step, setStep] = useState(0);
  const [pinned, setPinned] = useState(false);

  useEffect(() => {
    const mq = window.matchMedia?.("(min-width: 768px)");
    let raf = 0;
    const measure = () => {
      raf = 0;
      const el = wrap.current;
      const isPinned = !!mq?.matches;
      setPinned(isPinned);
      if (!el || !isPinned) return;
      const r = el.getBoundingClientRect();
      const total = r.height - window.innerHeight;
      if (total <= 0) return;
      const p = Math.min(0.999, Math.max(0, -r.top / total));
      setStep(Math.floor(p * STEPS.length));
    };
    const onScroll = () => { if (!raf) raf = requestAnimationFrame(measure); };
    measure();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    mq?.addEventListener?.("change", onScroll);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
      mq?.removeEventListener?.("change", onScroll);
    };
  }, []);

  // Clicking a step scrolls to the part of the pinned section that shows it.
  const go = (i: number) => {
    const el = wrap.current;
    if (!el || !pinned) { setStep(i); return; }
    const top = el.getBoundingClientRect().top + window.scrollY;
    const total = el.offsetHeight - window.innerHeight;
    window.scrollTo({ top: top + ((i + 0.5) / STEPS.length) * total, behavior: "smooth" });
  };
  const screens = [<ScreenSpeak key="0" />, <ScreenUnderstand key="1" />, <ScreenSchemes key="2" />];

  return (
    <div className="how-pin" ref={wrap}>
      <div className="how-sticky">
        <div className="l-wrap how-grid">
          <div className="how-head">
            <span className="l-kicker">How it works</span>
            <h2 className="l-h2">Teen kadam. <em className="l-em">Bas.</em></h2>
          </div>
          <ol className="how-steps">
            {STEPS.map((s, i) => (
              <li key={s.n} className="how-step" data-active={i === step || undefined}>
                <button type="button" onClick={() => go(i)} aria-current={i === step ? "step" : undefined}>
                  <span className="how-n">{s.n}</span>
                  <span className="how-text">
                    <span className="how-title">{s.title}</span>
                    <span className="how-body">{s.body}</span>
                  </span>
                </button>
                <div className="how-inline-screen" aria-hidden="true">{screens[i]}</div>
              </li>
            ))}
          </ol>
          <div className="how-phone-col" aria-hidden="true">
            <div className="phone">
              {screens.map((sc, i) => <div key={i} className="phone-layer" data-on={i === step || undefined}>{sc}</div>)}
            </div>
            <div className="how-dots">{STEPS.map((s, i) => <span key={s.n} data-on={i === step || undefined} />)}</div>
          </div>
        </div>
      </div>
    </div>
  );
}
