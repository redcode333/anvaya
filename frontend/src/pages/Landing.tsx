import { useState, type ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";
import HeroHeadline from "../hero/HeroHeadline";
import { HERO_LINES, heroIndexForLang, t, type HeroLine } from "../i18n";
import { CrowdCanvas, GatewaySection } from "../landing/Canvases";
import DemoCard, { CheckIcon, MicIcon } from "../landing/DemoCard";
import HowItWorks from "../landing/HowItWorks";
import { useReveal } from "../landing/motion";
import PortalRace from "../landing/PortalRace";
import { useApp } from "../state";
import "../landing/landing.css";

const GREETINGS: [string, string][] = [
  ["नमस्ते", "hi"], ["నమస్కారం", "te"], ["নমস্কাৰ", "as"], ["നമസ്കാരം", "ml"], ["வணக்கம்", "ta"], ["ਸਤ ਸ੍ਰੀ ਅਕਾਲ", "pa"],
  ["નમસ્તે", "gu"], ["ನಮಸ್ಕಾರ", "kn"], ["ନମସ୍କାର", "or"], ["नमस्कार", "mr"], ["آداب", "ur"], ["Hello", "en"],
];

function Reveal({ children, className = "" }: { children: ReactNode; className?: string }) {
  const r = useReveal<HTMLDivElement>();
  return <div ref={r.ref} className={`${r.className} ${className}`}>{children}</div>;
}

export function Ticker({ big = false }: { big?: boolean }) {
  const row = (hidden: boolean) => (
    <div className="ticker-row" aria-hidden={hidden || undefined}>
      {GREETINGS.map(([g, l]) => <span key={g} lang={l}>{g}<i aria-hidden="true" /></span>)}
    </div>
  );
  return (
    <div className={`ticker${big ? " big" : ""}`} aria-label="Greetings in Indian languages">
      <div className="ticker-track">{row(false)}{row(true)}</div>
    </div>
  );
}

const TILES: { name: string; en: string; ex: string; icon: ReactNode }[] = [
  { name: "Kisan", en: "Farmers", ex: "PM-KISAN, PM Fasal Bima, Kisan Credit Card", icon: <><path d="M12 21v-8" /><path d="M12 13c0-4 3-6 7-6 0 4-3 6-7 6z" /><path d="M12 15c0-3-2.5-5-6-5 0 3 2.5 5 6 5z" /><path d="M5 21h14" /></> },
  { name: "Mahila", en: "Women", ex: "Ujjwala LPG, Matru Vandana, Sukanya Samriddhi", icon: <><circle cx="12" cy="5.5" r="3" /><path d="M7 21l2.2-10h5.6L17 21" /><path d="M9.2 11c1.4 2.6 4.2 2.6 5.6 0" /><path d="M8.5 16h7" /></> },
  { name: "Vidyarthi", en: "Students", ex: "Post-matric scholarships, National Scholarship Portal", icon: <><path d="M3 5h6a3 3 0 0 1 3 3v12a2 2 0 0 0-2-2H3z" /><path d="M21 5h-6a3 3 0 0 0-3 3v12a2 2 0 0 1 2-2h7z" /></> },
  { name: "Buzurg", en: "Elders", ex: "Old-age pension, Ayushman Vay Vandana", icon: <><circle cx="10" cy="4.5" r="2.5" /><path d="M10 7.5v6.5l-3 7" /><path d="M10 14l3.2 7" /><path d="M10 9.5l4.5 2.5" /><path d="M16.5 12v9" /></> },
  { name: "Shramik", en: "Workers", ex: "e-Shram, PM Shram Yogi Maandhan, BOCW welfare", icon: <><path d="M5 16a7 7 0 0 1 14 0" /><path d="M10 9.4V6h4v3.4" /><path d="M3 16h18v2.5H3z" /></> },
  { name: "Divyang", en: "Persons with disability", ex: "UDID card, disability pension, ADIP aids", icon: <><circle cx="11" cy="4.5" r="2" /><path d="M11 7.5v6h5l2.2 5" /><path d="M8 10.5a5.2 5.2 0 1 0 7.4 6.3" /></> },
];

const DOCS = ["Aadhaar card", "Land record (khatauni / jamabandi)", "Bank passbook, linked to Aadhaar"];

export default function Landing() {
  const { lang, setMode, resetCitizen } = useApp();
  const nav = useNavigate();
  const go = (m: "personal" | "kiosk") => { resetCitizen(); setMode(m); nav(m === "kiosk" ? "/kiosk" : "/citizen"); };
  const [line, setLine] = useState<HeroLine>(HERO_LINES[heroIndexForLang(lang)]);
  const [docs, setDocs] = useState([true, true, false]);
  const walk = useReveal<HTMLDivElement>();

  return (
    <div className="landing">
      <section className="l-hero">
        <div className="l-wrap l-hero-grid">
          <div className="l-hero-copy">
            <span className="l-eyebrow"><i aria-hidden="true" />{t("heroEyebrow", lang)}</span>
            <HeroHeadline onLineChange={setLine} />
            <p className="l-sub">{t("heroSub", lang)}</p>
            <div className="l-cta-row">
              <div className="l-mic-wrap">
                <button type="button" className="l-mic" onClick={() => go("personal")} aria-label={line.mic} lang={line.lang}>
                  <span className="l-ring" aria-hidden="true" /><span className="l-ring r2" aria-hidden="true" />
                  <MicIcon size={36} />
                </button>
                <MicLabel active={line.id} />
              </div>
              <div className="l-cta-side">
                <button type="button" className="l-link" onClick={() => go("personal")}>{t("typeInstead", lang)}</button>
                <div className="l-alt">
                  <button type="button" className="btn small" onClick={() => go("kiosk")}>{t("kiosk", lang)}</button>
                  <button type="button" className="btn small ghost" onClick={() => nav("/case")}>{t("checkStatus", lang)}</button>
                  <button type="button" className="btn small ghost" onClick={() => nav("/resume")}>{t("resume", lang)}</button>
                  <button type="button" className="btn small ghost" onClick={() => nav("/citizen/passports")}>{t("myPassports", lang)}</button>
                </div>
                <span className="l-trust">{t("heroTrust", lang)}</span>
              </div>
            </div>
          </div>
          <div className="l-hero-demo"><DemoCard speech={lang === "te" ? "te" : "hinglish"} run={0} /></div>
        </div>
        <CrowdCanvas />
      </section>

      <Ticker />

      <Reveal><GatewaySection onMic={() => go("personal")} /></Reveal>

      <section className="l-how" aria-label="How it works"><HowItWorks /></section>

      <section className="l-band white">
        <Reveal className="l-wrap l-stack">
          <div className="l-intro">
            <h2 className="l-h2">Seven steps, or <em className="l-em">one sentence.</em></h2>
            <p>The portal expects you to know the system; Anvaya expects you to talk.</p>
          </div>
          <PortalRace />
        </Reveal>
      </section>

      <section className="l-band">
        <Reveal className="l-wrap l-stack">
          <div className="l-intro">
            <h2 className="l-h2">Start with <em className="l-em">who you are.</em></h2>
            <p>Tap one and Anvaya starts with you.</p>
          </div>
          <div className="tiles">
            {TILES.map((tile) => (
              <button key={tile.name} type="button" className="tile" onClick={() => go("personal")}>
                <span className="tile-ic"><svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{tile.icon}</svg></span>
                <span className="tile-name"><b>{tile.name}</b><span>{tile.en}</span></span>
                <span className="tile-ex">{tile.ex}</span>
              </button>
            ))}
          </div>
        </Reveal>
      </section>

      <section className="l-band white">
        <div ref={walk.ref} className={`l-wrap l-stack ${walk.className}`}>
          <div className="l-intro center">
            <h2 className="l-h2">What you <em className="l-em">walk away</em> with.</h2>
            <p>One card per scheme, written for you, not for the department.</p>
          </div>
          <div className="wa">
            <div className="wa-col wa-l">
              <Callout n={1} title="Why you qualify" body="In plain words. No jargon, no clause numbers." side="l" />
              <Callout n={2} title="Documents checklist" body="Tick off what you already have at home." side="l" />
            </div>
            <article className="wa-card">
              <header>
                <div><small>Central scheme · Agriculture</small><h3>PM-KISAN</h3><span>Pradhan Mantri Kisan Samman Nidhi</span></div>
                <span className="wa-elig"><CheckIcon size={14} />Eligible</span>
              </header>
              <p className="wa-benefit"><strong>₹6,000 a year</strong>, paid in three instalments straight to your bank account.</p>
              <div className="wa-row"><Num n={1} /><div><small>Why you qualify</small><p>You own 2 acres of farmland in Gaya, Bihar, and farm it yourself.</p></div></div>
              <div className="wa-row"><Num n={2} /><div>
                <small className="wa-split">Documents <span className="ok">{docs.filter(Boolean).length} of 3 ready</span></small>
                {DOCS.map((d, i) => (
                  <label key={d} className="wa-check">
                    <input type="checkbox" checked={docs[i]} onChange={() => setDocs((x) => x.map((v, j) => (j === i ? !v : v)))} />{d}
                  </label>
                ))}
              </div></div>
              <div className="wa-row"><Num n={3} /><div><small>Where to apply</small>
                <ul><li>Common Service Centre (CSC) near you</li><li>Online — <a href="https://pmkisan.gov.in" target="_blank" rel="noreferrer">pmkisan.gov.in</a> → New Farmer Registration</li><li>Block agriculture office</li></ul>
              </div></div>
              <div className="wa-row center"><Num n={4} /><div><span className="l-btn ghost static">Hindi mein phir se suniye</span></div></div>
              <footer className="wa-row center"><Num n={5} /><span>Pre-screening only. Final approval by the department.</span></footer>
            </article>
            <div className="wa-col wa-r">
              <Callout n={3} title="Where to apply" body="Nearest CSC, the online link, or the office." side="r" />
              <Callout n={4} title="Hear it again" body="One tap replays it in your language." side="r" />
              <Callout n={5} title="Pre-screen, not approval" body="We never pretend to be the government." side="r" />
            </div>
          </div>
        </div>
      </section>

      <section className="l-band">
        <Reveal className="l-wrap l-stack">
          <h2 className="l-h2">Plain about <em className="l-em">what we are.</em></h2>
          <div className="trust">
            <div><TrustIcon d={<><rect x="4" y="11" width="16" height="10" rx="2" /><path d="M8 11V7a4 4 0 0 1 7.6-1.7" /><path d="M12 15v2" /></>} />
              <h3>No login needed</h3><p>No account and no password. Just tap the mic and speak.</p></div>
            <div><TrustIcon d={<><path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z" /><path d="M9 11v3" /><path d="M12 9v7" /><path d="M15 11v3" /></>} />
              <h3>Your recording isn’t stored</h3><p>Speech is turned into text; the audio itself is never saved. Leaving a kiosk session deletes anything you didn’t consent to share.</p></div>
            <div><TrustIcon d={<><path d="M6 3h9l4 4v14H6z" /><path d="M14 3v5h5" /><path d="M9 14l2 2 4-4" /></>} />
              <h3>Sourced from official rules</h3><p>Every result shows the rule, its source and when it was last checked.</p>
              <Link to="/admin/schemes">See the scheme catalogue →</Link></div>
          </div>
          <div className="staff-note">
            <b>For judges &amp; staff.</b> Run the official scenarios on <Link to="/test-runs">TC1–TC5</Link>, review cases on <Link to="/reviewer">Reviewer</Link>,
            inspect data freshness on <Link to="/admin/schemes">Catalogue</Link>. Kiosk mode needs an operator sign-in; staff use the email and password
            (and authenticator code) an administrator created for them.
          </div>
        </Reveal>
      </section>

      <section className="l-cta">
        <Reveal className="l-wrap l-cta-inner">
          <h2 className="l-h2 big" lang={lang}>{t("ctaA", lang)}<em className="l-em">{t("ctaEm", lang)}</em>{t("ctaB", lang)}</h2>
          <p>{t("ctaSub", lang)}</p>
          <div className="l-mic-wrap">
            <button type="button" className="l-mic big" onClick={() => go("personal")} aria-label={line.mic} lang={line.lang}>
              <span className="l-ring" aria-hidden="true" /><span className="l-ring r2" aria-hidden="true" /><MicIcon size={44} />
            </button>
            <MicLabel active={line.id} />
          </div>
        </Reveal>
        <Ticker big />
      </section>

      <footer className="l-foot">
        <div className="l-wrap l-foot-inner">
          <span className="l-foot-brand"><img src="/brand/anvaya-mark-white.svg" alt="" width="28" height="28" />Anvaya AI</span>
          <nav aria-label="Footer">
            <Link to="/case">Case status</Link><Link to="/admin/schemes">Scheme sources</Link><Link to="/signin">{t("signIn", lang)}</Link><Link to="/reviewer">Staff</Link>
          </nav>
          <p>{t("notApproval", lang)}</p>
        </div>
      </footer>
    </div>
  );
}

/** Every language's mic label shares one grid cell: the visible one swaps without moving anything (CLS 0). */
function MicLabel({ active }: { active: string }) {
  return (
    <span className="l-mic-label" aria-hidden="true">
      {HERO_LINES.map((l) => <span key={l.id} lang={l.lang} data-on={l.id === active}>{l.mic}</span>)}
    </span>
  );
}
function Num({ n }: { n: number }) { return <span className="wa-num" aria-hidden="true">{n}</span>; }
function Callout({ n, title, body, side }: { n: number; title: string; body: string; side: "l" | "r" }) {
  return (
    <div className={`wa-callout ${side}`}>
      {side === "r" && <span className="wa-line" aria-hidden="true"><i style={{ transitionDelay: `${n * 0.15}s` }} /></span>}
      <div className="wa-text"><span className="wa-dot" aria-hidden="true">{n}</span><div><b>{title}</b><span>{body}</span></div></div>
      {side === "l" && <span className="wa-line" aria-hidden="true"><i style={{ transitionDelay: `${n * 0.15}s` }} /></span>}
    </div>
  );
}
function TrustIcon({ d }: { d: ReactNode }) {
  return <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#1F4E79" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{d}</svg>;
}
