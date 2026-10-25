import { useEffect, useRef, useState } from "react";
import { startCrowd } from "./crowd";
import { startGateway } from "./gateway";
import { MicIcon } from "./DemoCard";
import { prefersReducedMotion, useOnScreen } from "./motion";

export function CrowdCanvas() {
  const cv = useRef<HTMLCanvasElement>(null);
  const eng = useRef<ReturnType<typeof startCrowd>>();
  const on = useOnScreen(cv);
  useEffect(() => {
    if (!cv.current) return;
    eng.current = startCrowd(cv.current, { reduced: prefersReducedMotion() });
    return () => eng.current?.destroy();
  }, []);
  useEffect(() => { eng.current?.setVisible(on); }, [on]);
  return (
    <div className="crowd">
      <canvas ref={cv} role="img"
        aria-label="An animated crowd of Indian citizens — farmers in dhoti and pagdi, women in sarees and salwar kameez, elders with walking sticks, students and workers — walking past, some asking about schemes in their own language." />
    </div>
  );
}

const RESULTS = [
  { name: "PM-KISAN", note: "Eligible · ₹6,000 a year", tone: "ok" },
  { name: "PM Fasal Bima", note: "Eligible · crop insurance", tone: "ok" },
  { name: "Post-matric scholarship", note: "Likely · 1 more detail", tone: "warn" },
  { name: "PM Ujjwala", note: "Eligible · LPG connection", tone: "ok" },
  { name: "Bihar Vridhjan Pension", note: "From age 60", tone: "later" },
  { name: "e-Shram card", note: "Eligible · free registration", tone: "ok" },
];

/** अन्वय: scattered words in many languages travel in and join into one answer. */
export function GatewaySection({ onMic }: { onMic: () => void }) {
  const cv = useRef<HTMLCanvasElement>(null);
  const eng = useRef<ReturnType<typeof startGateway>>();
  const on = useOnScreen(cv);
  const [ri, setRi] = useState(0);
  const [chipOn, setChipOn] = useState(true);

  useEffect(() => {
    if (!cv.current) return;
    eng.current = startGateway(cv.current, { reduced: prefersReducedMotion() });
    return () => eng.current?.destroy();
  }, []);
  useEffect(() => { eng.current?.setVisible(on); }, [on]);
  useEffect(() => {
    if (prefersReducedMotion() || !on) return;
    let t: number | undefined;
    const iv = window.setInterval(() => {
      setChipOn(false);
      t = window.setTimeout(() => { setRi((i) => i + 1); setChipOn(true); }, 380);
    }, 3200);
    return () => { window.clearInterval(iv); window.clearTimeout(t); };
  }, [on]);

  const scatter = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const el = e.currentTarget, r = el.getBoundingClientRect();
    eng.current?.burst(e.clientX - r.left, e.clientY - r.top);
  };
  const res = RESULTS[ri % RESULTS.length];

  return (
    <section className="gw" aria-labelledby="gw-title">
      <div className="l-wrap gw-head">
        <div className="gw-word">
          <span id="gw-title" lang="sa">अन्वय</span>
          <span>/ an·va·ya /</span>
          <span><i>noun, Sanskrit</i></span>
        </div>
        <p className="gw-def">the joining of scattered words into one meaning.</p>
        <p className="gw-sub">People speak in pieces, in whatever language comes first. Anvaya joins the pieces into one answer.</p>
      </div>
      <div className="gw-stage">
        <canvas ref={cv} onClick={scatter} aria-hidden="true" />
        <button type="button" className="gw-orb" aria-label="Tap and speak" onClick={() => { eng.current?.burstCenter(); window.setTimeout(onMic, 350); }}>
          <MicIcon size={32} />
        </button>
        <div className="gw-chip" aria-live="polite" style={{ opacity: chipOn ? 1 : 0 }}>
          <span className={`gw-dot ${res.tone}`} /><b>{res.name}</b><span>{res.note}</span>
        </div>
      </div>
      <p className="gw-hint">Tap anywhere. The words always find their way back.</p>
    </section>
  );
}
