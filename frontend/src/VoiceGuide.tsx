import { useEffect, useRef, useState, type ReactNode } from "react";
import type { Lang } from "./i18n";
import { MicIcon } from "./landing/DemoCard";
import { listen, speak, stopSpeaking, voiceProvider, type Provider, type Recorder } from "./speech";

// A guided voice card: it asks one question at a time (aloud and on screen), listens, shows what it understood, and moves on. Typing
// always works. Used to fill a draft and to check documents. Nothing is saved here: the caller's `answer` decides what a reply means.

/** `question` is read aloud and shown; `hint` (optional) is only shown, small, under it. */
export type GuideStep = { key: string; label: string; question: string; hint?: string };
export type GuideResult = { ok: boolean; message: string; apply?: () => void };

const TEXT = {
  of: { en: "Question {n} of {m}", hi: "प्रश्न {n} / {m}", te: "ప్రశ్న {n} / {m}" },
  tap: { en: "Tap the microphone and answer", hi: "माइक दबाकर जवाब दीजिए", te: "మైక్ నొక్కి సమాధానం చెప్పండి" },
  listening: { en: "Listening… tap to stop", hi: "सुन रहे हैं… रोकने के लिए दबाएँ", te: "వింటున్నాం… ఆపడానికి నొక్కండి" },
  working: { en: "One moment…", hi: "एक क्षण…", te: "ఒక్క క్షణం…" },
  heard: { en: "You said", hi: "आपने कहा", te: "మీరు చెప్పారు" },
  use: { en: "Use this", hi: "यह ठीक है", te: "ఇది సరైనది" },
  again: { en: "Say it again", hi: "फिर से बोलिए", te: "మళ్ళీ చెప్పండి" },
  skip: { en: "Skip", hi: "छोड़ें", te: "వదిలేయండి" },
  close: { en: "Close", hi: "बंद करें", te: "మూసివేయండి" },
  type: { en: "Or type your answer", hi: "या लिखकर बताइए", te: "లేదా టైప్ చేయండి" },
  send: { en: "Send", hi: "भेजें", te: "పంపండి" },
  repeat: { en: "Ask again", hi: "फिर से पूछें", te: "మళ్ళీ అడగండి" },
} satisfies Record<string, Record<Lang, string>>;
const tx = (k: keyof typeof TEXT, lang: Lang) => TEXT[k][lang];

type Phase = "ask" | "listening" | "working" | "result" | "done";

export function VoiceGuide({ lang, sessionId, title, steps, confirm, answer, onClose, done }: {
  lang: Lang; sessionId: string; title: string; steps: GuideStep[];
  /** true: show what was understood and wait for "Use this" (names, where a mishearing matters); false: apply and move on by itself. */
  confirm: boolean;
  answer: (step: GuideStep, utterance: string) => Promise<GuideResult>;
  onClose: () => void;
  /** What to show after the last step. */
  done: (close: () => void) => ReactNode;
}) {
  const [idx, setIdx] = useState(0);
  const [phase, setPhase] = useState<Phase>("ask");
  const [heard, setHeard] = useState("");
  const [result, setResult] = useState<GuideResult | null>(null);
  const [typed, setTyped] = useState("");
  const [note, setNote] = useState("");
  const [provider, setProvider] = useState<Provider>("none");
  const rec = useRef<Recorder | null>(null);
  const timer = useRef<number | undefined>(undefined);
  const step = steps[idx];

  useEffect(() => { voiceProvider().then(setProvider); return () => { rec.current?.stop(); stopSpeaking(); window.clearTimeout(timer.current); }; }, []);
  // Each question is read aloud when it comes up (and when the language changes); the text is on screen either way.
  useEffect(() => {
    if (phase === "ask" && step) void speak(provider, sessionId, step.question, lang);
  }, [idx, phase === "ask", provider, lang]); // eslint-disable-line react-hooks/exhaustive-deps

  const close = () => { rec.current?.stop(); stopSpeaking(); window.clearTimeout(timer.current); onClose(); };
  const next = () => {
    window.clearTimeout(timer.current);
    setHeard(""); setResult(null); setTyped(""); setNote("");
    if (idx + 1 < steps.length) { setIdx(idx + 1); setPhase("ask"); } else { stopSpeaking(); setPhase("done"); }
  };

  const submit = async (text: string) => {
    const said = text.trim();
    if (!said || !step) return;
    stopSpeaking(); setHeard(said); setPhase("working"); setNote("");
    let r: GuideResult;
    try { r = await answer(step, said); } catch (e: any) { r = { ok: false, message: e?.message ?? String(e) }; }
    setResult(r); setPhase("result");
    if (r.ok && !confirm) { r.apply?.(); timer.current = window.setTimeout(next, 1400); }
  };

  const mic = () => {
    if (rec.current) { rec.current.stop(); rec.current = null; return; }
    stopSpeaking(); setNote(""); setPhase("listening");
    rec.current = listen(provider, sessionId, lang, (txt) => { rec.current = null; void submit(txt); }, (m) => { setNote(m); setPhase("ask"); },
      () => { rec.current = null; setPhase((p) => (p === "listening" ? "ask" : p)); });
    if (!rec.current) setPhase("ask");
  };

  if (phase === "done") return <section className="voice-guide" aria-live="polite"><h2>{title}</h2>{done(close)}</section>;
  if (!step) return null;
  return (
    <section className="voice-guide" aria-live="polite" aria-label={title}>
      <div className="vg-head">
        <h2>{title}</h2>
        <button type="button" className="btn small ghost" onClick={close}>{tx("close", lang)}</button>
      </div>
      <div className="vg-dots" aria-hidden="true">{steps.map((s, i) => <i key={s.key} className={i < idx ? "done" : i === idx ? "now" : ""} />)}</div>
      <p className="tiny muted">{tx("of", lang).replace("{n}", String(idx + 1)).replace("{m}", String(steps.length))} · {step.label}</p>
      <p className="vg-question">{step.question}</p>
      {step.hint && <p className="tiny muted vg-hint">{step.hint}</p>}

      <div className="vg-mic-row">
        <button type="button" className={`orb-mic ${phase === "listening" ? "rec" : ""}`} onClick={mic} disabled={phase === "working" || provider === "none"}
          aria-label={phase === "listening" ? tx("listening", lang) : tx("tap", lang)} aria-pressed={phase === "listening"}>
          <span className="orb-ring" aria-hidden="true" /><span className="orb-ring r2" aria-hidden="true" /><MicIcon size={28} />
        </button>
        <span className="small">{phase === "listening" ? tx("listening", lang) : phase === "working" ? tx("working", lang) : provider === "none" ? "" : tx("tap", lang)}</span>
        <button type="button" className="btn small ghost" onClick={() => void speak(provider, sessionId, step.question, lang)}>🔊 {tx("repeat", lang)}</button>
      </div>
      {note && <p className="notice small">{note}</p>}

      {phase === "result" && result && (
        <div className={`vg-result ${result.ok ? "ok" : "no"}`}>
          {heard && <div className="tiny">{tx("heard", lang)}: “{heard}”</div>}
          <div>{result.message}</div>
          <div className="row">
            {result.ok && confirm && <button type="button" className="btn primary small" onClick={() => { result.apply?.(); next(); }}>✓ {tx("use", lang)}</button>}
            <button type="button" className="btn small" onClick={() => { setPhase("ask"); setResult(null); setHeard(""); }}>↻ {tx("again", lang)}</button>
            <button type="button" className="btn small ghost" onClick={next}>{tx("skip", lang)} →</button>
          </div>
        </div>
      )}
      {phase !== "result" && (
        <form className="vg-type" onSubmit={(e) => { e.preventDefault(); void submit(typed); setTyped(""); }}>
          <input type="text" value={typed} onChange={(e) => setTyped(e.target.value)} placeholder={tx("type", lang)} aria-label={tx("type", lang)} disabled={phase === "working"} />
          <button className="btn small" type="submit" disabled={!typed.trim() || phase === "working"}>{tx("send", lang)}</button>
          <button type="button" className="btn small ghost" onClick={next}>{tx("skip", lang)} →</button>
        </form>
      )}
    </section>
  );
}
