import { useEffect, useState, type CSSProperties } from "react";
import { usePrefersReducedMotion } from "./motion";

// Scripted demo (not a live session): a messy spoken sentence → fillers struck → facts → schemes.
type W = [string, boolean]; // [word, filler]
type Chip = { k: string; v: string; src: number[] };
type Card = { name: string; amount: string; rest: string; badge: string; tone: "ok" | "later"; docs: string[]; where: string };
type Demo = { langName: string; lang: string; said: string; status: [string, string, string]; disc: string; words: W[]; chips: Chip[]; cards: Card[] };

const DEMOS: Record<"hinglish" | "te", Demo> = {
  hinglish: {
    langName: "Hinglish", lang: "hi-Latn", said: "Aapne kaha",
    status: ["Sun raha hoon…", "Samajh raha hoon…", "3 yojanayein mili"],
    disc: "Pre-screening only. Final approval by the department.",
    words: [["haan", true], ["toh", true], ["main", false], ["woh…", true], ["Gaya", false], ["district", false], ["se", false], ["hoon,", false],
      ["umar", false], ["58", false], ["hai,", false], ["kheti", false], ["karta", false], ["hoon,", false], ["do", false], ["acre", false],
      ["zameen", false], ["hai,", false], ["matlab", true], ["ghar", false], ["mein", false], ["koi", false], ["pension", false], ["nahi", false], ["milta…", false]],
    chips: [{ k: "Age", v: "58", src: [8, 9] }, { k: "District", v: "Gaya", src: [4] }, { k: "State", v: "Bihar", src: [4, 5] },
      { k: "Occupation", v: "Farmer", src: [11, 12] }, { k: "Land", v: "2 acre", src: [14, 15, 16] }, { k: "Pension", v: "None", src: [22, 23] }],
    cards: [
      { name: "PM-KISAN", amount: "₹6,000 a year", rest: " · 3 instalments to your bank", badge: "Eligible", tone: "ok", docs: ["Aadhaar", "Land record", "Bank passbook"], where: "Apply at your nearest CSC or pmkisan.gov.in" },
      { name: "PM Fasal Bima Yojana", amount: "2% premium", rest: " · crop insurance for kharif", badge: "Eligible", tone: "ok", docs: ["Aadhaar", "Land record", "Sowing certificate"], where: "Apply via your bank, CSC or pmfby.gov.in" },
      { name: "Bihar Vridhjan Pension", amount: "Monthly pension", rest: " · for residents aged 60+", badge: "From age 60", tone: "later", docs: ["Aadhaar", "Age proof"], where: "Not yet — apply at 60 at the block office" },
    ],
  },
  te: {
    langName: "తెలుగు", lang: "te", said: "మీరు చెప్పింది",
    status: ["వింటున్నాను…", "అర్థం చేసుకుంటున్నాను…", "3 పథకాలు దొరికాయి"],
    disc: "ఇది ముందస్తు పరిశీలన మాత్రమే. తుది ఆమోదం సంబంధిత శాఖదే.",
    words: [["ఆ…", true], ["అంటే…", true], ["నేను", false], ["గుంటూరు", false], ["జిల్లా", false], ["నుంచి,", false], ["నా", false], ["వయసు", false], ["58,", false],
      ["వ్యవసాయం", false], ["చేస్తాను,", false], ["రెండు", false], ["ఎకరాల", false], ["భూమి", false], ["ఉంది,", false], ["అదీ…", true], ["ఇంట్లో", false],
      ["ఎవరికీ", false], ["పింఛను", false], ["రావట్లేదు…", false]],
    chips: [{ k: "వయసు", v: "58", src: [7, 8] }, { k: "జిల్లా", v: "గుంటూరు", src: [3, 4] }, { k: "రాష్ట్రం", v: "ఆంధ్రప్రదేశ్", src: [3] },
      { k: "వృత్తి", v: "రైతు", src: [9, 10] }, { k: "భూమి", v: "2 ఎకరాలు", src: [11, 12, 13] }, { k: "పింఛను", v: "లేదు", src: [18, 19] }],
    cards: [
      { name: "PM-KISAN", amount: "₹6,000 / సంవత్సరం", rest: " · 3 విడతల్లో బ్యాంకు ఖాతాకు", badge: "అర్హులు", tone: "ok", docs: ["ఆధార్", "భూమి పత్రాలు", "బ్యాంకు పాస్‌బుక్"], where: "దగ్గరలోని CSC లేదా pmkisan.gov.in లో దరఖాస్తు" },
      { name: "PM Fasal Bima Yojana", amount: "2% ప్రీమియం", rest: " · ఖరీఫ్ పంట బీమా", badge: "అర్హులు", tone: "ok", docs: ["ఆధార్", "భూమి పత్రాలు", "విత్తన ధృవీకరణ"], where: "బ్యాంకు, CSC లేదా pmfby.gov.in ద్వారా" },
      { name: "NTR Bharosa Pension", amount: "నెలవారీ పింఛను", rest: " · 60 ఏళ్లు పైబడినవారికి", badge: "60 ఏళ్ల నుంచి", tone: "later", docs: ["ఆధార్", "వయసు రుజువు"], where: "ఇప్పుడు కాదు — 60 ఏళ్లు నిండాక గ్రామ సచివాలయంలో" },
    ],
  },
};

const LOOP = 175; // ticks of 100 ms

export default function DemoCard({ speech, run }: { speech: "hinglish" | "te"; run: number }) {
  const reduced = usePrefersReducedMotion();
  const [tick, setTick] = useState(0);
  const D = DEMOS[speech];

  useEffect(() => { setTick(reduced ? 120 : 0); }, [speech, run, reduced]);
  useEffect(() => {
    if (reduced) return;
    const iv = setInterval(() => setTick((t) => (t >= LOOP ? 0 : t + 1)), 100);
    return () => clearInterval(iv);
  }, [reduced]);

  const t = tick;
  const listen = t < 46, think = t >= 46 && t < 80;
  const active = new Set<number>();
  const chipOn = D.chips.map((c, k) => { const on = t >= 52 + k * 4; if (on) c.src.forEach((i) => active.add(i)); return on; });
  const phase = listen ? 0 : think ? 1 : 2;

  return (
    <div className="demo" aria-label="Live demo, scripted">
      <div className="demo-head">
        <span className="demo-live"><span className="demo-dot" data-phase={listen ? "listen" : think ? "think" : "done"} />Live demo · {D.langName}</span>
        <button type="button" className="demo-replay" onClick={() => setTick(0)}>Replay</button>
      </div>
      <div className="demo-mic">
        <span className="demo-mic-btn" aria-hidden="true">
          {listen ? <MicIcon size={20} /> : think ? <span className="spin-ring" /> : <CheckIcon size={22} />}
        </span>
        <span className="demo-wave" aria-hidden="true">
          {Array.from({ length: 28 }, (_, i) => {
            const live = listen && t >= 2;
            const h = live ? 6 + 26 * Math.abs(Math.sin(t * 0.9 + i * 0.7)) * (0.35 + 0.65 * Math.abs(Math.sin(i * 1.3 + t * 0.21))) : 4;
            return <span key={i} style={{ transform: `scaleY(${(h / 32).toFixed(3)})`, opacity: live ? 1 : 0.3 }} />;
          })}
        </span>
        <span className="demo-status" aria-live="polite">
          {/* all three labels share one cell, so the width never changes */}
          {D.status.map((s, i) => <span key={s} data-on={i === phase} aria-hidden={i !== phase || undefined}>{s}</span>)}
        </span>
      </div>
      <div>
        <span className="demo-label">{D.said}</span>
        <p className="demo-words" lang={D.lang}>
          {D.words.map(([w, filler], i) => {
            const shown = t >= 4 + i * 1.6, struck = filler && t >= 48, hi = active.has(i);
            return <span key={i} className={`dw${filler ? " filler" : ""}${struck ? " struck" : ""}${hi ? " hi" : ""}`} style={{ opacity: !shown ? 0 : struck ? 0.35 : 1 }}>{w}</span>;
          })}
        </p>
      </div>
      <div className="demo-chips">
        {D.chips.map((c, k) => (
          <span key={c.k} className="demo-chip" data-on={chipOn[k] || undefined}><span>{c.k}</span><b>{c.v}</b></span>
        ))}
      </div>
      <div className="demo-cards">
        {D.cards.map((c, k) => (
          <article key={c.name} className="demo-card" data-on={t >= 80 + k * 9 || undefined}>
            <div className="demo-card-top">
              <div>
                <div className="demo-card-name">{c.name}</div>
                <div className="demo-card-sub"><b>{c.amount}</b>{c.rest}</div>
              </div>
              <span className={`demo-badge ${c.tone}`}>{c.badge}</span>
            </div>
            <div className="demo-docs">{c.docs.map((d) => <span key={d}>{d}</span>)}</div>
            <div className="demo-where">{c.where}</div>
          </article>
        ))}
      </div>
      <div className="demo-disc">{D.disc}</div>
    </div>
  );
}

export function MicIcon({ size = 24, style }: { size?: number; style?: CSSProperties }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" style={style}>
      <rect x="9" y="2" width="6" height="12" rx="3" /><path d="M19 10v1a7 7 0 0 1-14 0v-1" /><path d="M12 18v4" />
    </svg>
  );
}
export function CheckIcon({ size = 24 }: { size?: number }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5" /></svg>;
}
