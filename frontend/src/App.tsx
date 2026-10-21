import { useEffect, useState } from "react";
import { NavLink, Route, Routes, useLocation } from "react-router-dom";
import { LANGS, t } from "./i18n";
import { getBundle, getOutbox } from "./offline/store";
import AdminSchemes from "./pages/AdminSchemes";
import CaseStatus from "./pages/CaseStatus";
import Documents from "./pages/Documents";
import DraftPage from "./pages/Draft";
import Journey from "./pages/Journey";
import Landing from "./pages/Landing";
import Passport from "./pages/Passport";
import Reviewer from "./pages/Reviewer";
import ReviewerCase from "./pages/ReviewerCase";
import TestRuns from "./pages/TestRuns";
import { useApp } from "./state";

function StatusBar() {
  const { online, simulateOffline, setSimulateOffline, lang, setLang, mode, sessionId } = useApp();
  const loc = useLocation();
  const [tick, setTick] = useState(0);
  useEffect(() => { const i = setInterval(() => setTick((x) => x + 1), 2000); return () => clearInterval(i); }, []);
  const bundle = getBundle();
  const pending = getOutbox().filter((e) => e.sync.state !== "SYNCED").length;
  void tick;
  const staffPage = /^\/(reviewer|admin|test-runs)/.test(loc.pathname);
  return (
    <div className="statusbar" role="status" aria-live="polite">
      <span className={`chip dot ${online ? "on" : "off"}`}>{online ? t("online", lang) : t("offline", lang)}</span>
      {mode === "kiosk" && !staffPage && (
        <label className="row small" style={{ gap: ".3rem" }}>
          <input type="checkbox" checked={simulateOffline} onChange={(e) => setSimulateOffline(e.target.checked)} /> simulate network loss
        </label>
      )}
      <span className="chip">bundle {bundle ? `${bundle.bundle_version} · ${bundle.rules.length} rules · ${new Date(bundle.generated_at).toLocaleString()}` : "not cached"}</span>
      {pending > 0 && <span className="chip s-SYNC_PENDING">outbox: {pending} SYNC_PENDING</span>}
      {sessionId && !staffPage && <span className="chip mono">{sessionId}</span>}
      {!staffPage && (
        <span className="row" style={{ marginLeft: "auto", gap: ".25rem" }}>
          {LANGS.map((l) => (
            <button key={l.code} className="btn small ghost" aria-pressed={lang === l.code} onClick={() => setLang(l.code)}
              style={lang === l.code ? { background: "var(--primary-soft)" } : undefined}>{l.name}</button>
          ))}
        </span>
      )}
    </div>
  );
}

export default function App() {
  const { mode } = useApp();
  return (
    <>
      <header className="topbar">
        <div className="topbar-inner">
          <NavLink to="/" className="brand"><img src="/icon.svg" alt="" />Anvaya AI</NavLink>
          <nav className="nav" aria-label="Main">
            <NavLink to={mode === "kiosk" ? "/kiosk" : "/citizen"}>Citizen</NavLink>
            <NavLink to="/case">Case status</NavLink>
            <NavLink to="/reviewer">Reviewer</NavLink>
            <NavLink to="/admin/schemes">Catalogue</NavLink>
            <NavLink to="/test-runs">TC1–TC4</NavLink>
          </nav>
        </div>
        <StatusBar />
      </header>
      <main>
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/citizen" element={<Journey mode="personal" />} />
          <Route path="/kiosk" element={<Journey mode="kiosk" />} />
          <Route path="/citizen/schemes" element={<Passport />} />
          <Route path="/citizen/documents" element={<Documents />} />
          <Route path="/citizen/draft/:id" element={<DraftPage />} />
          <Route path="/case" element={<CaseStatus />} />
          <Route path="/case/:code" element={<CaseStatus />} />
          <Route path="/reviewer" element={<Reviewer />} />
          <Route path="/reviewer/case/:id" element={<ReviewerCase />} />
          <Route path="/admin/schemes" element={<AdminSchemes />} />
          <Route path="/test-runs" element={<TestRuns />} />
          <Route path="*" element={<div className="card">Page not found.</div>} />
        </Routes>
      </main>
    </>
  );
}
