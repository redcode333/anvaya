import { useNavigate } from "react-router-dom";
import { DemoCreds } from "../components";
import { LANGS, t } from "../i18n";
import { useApp } from "../state";

export default function Landing() {
  const { lang, setLang, setMode, resetCitizen } = useApp();
  const nav = useNavigate();
  const go = (m: "personal" | "kiosk") => { resetCitizen(); setMode(m); nav(m === "kiosk" ? "/kiosk" : "/citizen"); };
  return (
    <div className="grid two">
      <section className="hero stack">
        <h1>{t("tagline", lang)}</h1>
        <p className="muted" style={{ fontSize: "1.1rem" }}>{t("intro", lang)}</p>
        <div className="card stack">
          <h2>{t("chooseLang", lang)}</h2>
          <div className="lang-pick">
            {LANGS.map((l) => (
              <button key={l.code} aria-pressed={lang === l.code} onClick={() => setLang(l.code)}>{l.name}</button>
            ))}
          </div>
          <div className="row">
            <button className="btn primary" onClick={() => go("personal")}>{t("personal", lang)} →</button>
            <button className="btn" onClick={() => go("kiosk")}>{t("kiosk", lang)}</button>
            <button className="btn ghost" onClick={() => nav("/case")}>{t("checkStatus", lang)}</button>
          </div>
        </div>
        <p className="notice small">{t("notApproval", lang)}</p>
      </section>
      <section className="stack">
        <div className="card flat stack">
          <h2>How it works</h2>
          <ol className="small" style={{ margin: 0, paddingLeft: "1.2rem" }}>
            <li>Speak or type about your household. Anvaya extracts facts and shows exactly what it heard.</li>
            <li>You confirm or correct age, income, state and household size before anything is checked.</li>
            <li>Confirmed facts are compared against sourced, versioned rules — explicit comparisons, not AI guesses.</li>
            <li>The Scheme Passport shows matches, reasons, rule quotes, sources and missing documents.</li>
            <li>A draft is prepared from your confirmed facts; with your consent it goes to a reviewer.</li>
          </ol>
        </div>
        <div className="card flat stack small">
          <h3>For judges & staff</h3>
          <p className="muted">Run the official scenarios on <a href="/test-runs">TC1–TC4</a>, review cases on <a href="/reviewer">Reviewer</a>,
            inspect data freshness on <a href="/admin/schemes">Catalogue</a>. Kiosk mode needs an operator sign-in.
            {" "}<DemoCreds users={["reviewer", "admin", "operator"]} /></p>
        </div>
      </section>
    </div>
  );
}
