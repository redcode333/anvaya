import { useEffect, useState } from "react";
import { NavLink, Route, Routes, useLocation } from "react-router-dom";
import { KioskIdleGuard } from "./AccountUI";
import { LANGS, t } from "./i18n";
import { getBundle, getOutbox } from "./offline/store";
import AdminSchemes from "./pages/AdminSchemes";
import AdminSecurity from "./pages/AdminSecurity";
import CaseStatus from "./pages/CaseStatus";
import DigiLockerCallback from "./pages/DigiLockerCallback";
import Documents from "./pages/Documents";
import DraftPage from "./pages/Draft";
import Journey from "./pages/Journey";
import Landing from "./pages/Landing";
import MyPassports from "./pages/MyPassports";
import Passport from "./pages/Passport";
import Profile from "./pages/Profile";
import Reviewer from "./pages/Reviewer";
import Resume from "./pages/Resume";
import ReviewerCase from "./pages/ReviewerCase";
import SignIn from "./pages/SignIn";
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
      {sessionId && !staffPage && mode !== "kiosk" && <span className="chip mono" title="Session">{sessionId.slice(0, 8)}…</span>}
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
  const { mode, lang } = useApp();
  const loc = useLocation();
  return (
    <>
      <header className="topbar">
        <div className="topbar-inner">
          <NavLink to="/" className="brand">
            <img className="brand-mark light" src="/brand/anvaya-mark.svg" alt="" width="28" height="28" />
            <img className="brand-mark dark" src="/brand/anvaya-mark-white.svg" alt="" width="28" height="28" />
            Anvaya AI
          </NavLink>
          <nav className="nav" aria-label="Main">
            <NavLink to={mode === "kiosk" ? "/kiosk" : "/citizen"}>Citizen</NavLink>
            {mode !== "kiosk" && <NavLink to="/citizen/passports">{t("myPassports", lang)}</NavLink>}
            <NavLink to="/case">Case status</NavLink>
            <NavLink to="/reviewer">Reviewer</NavLink>
            <NavLink to="/admin/schemes">Catalogue</NavLink>
            <NavLink to="/admin/security">Security</NavLink>
            <NavLink to="/test-runs">TC1–TC5</NavLink>
            <NavLink to="/signin">Sign in</NavLink>
          </nav>
        </div>
        <StatusBar />
      </header>
      <main className={loc.pathname === "/" ? "main-landing" : undefined}>
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/citizen" element={<Journey mode="personal" />} />
          <Route path="/kiosk" element={<Journey mode="kiosk" />} />
          <Route path="/citizen/schemes" element={<Passport />} />
          <Route path="/citizen/documents" element={<Documents />} />
          <Route path="/citizen/draft/:id" element={<DraftPage />} />
          <Route path="/citizen/passports" element={<MyPassports />} />
          <Route path="/resume" element={<Resume />} />
          <Route path="/case" element={<CaseStatus />} />
          <Route path="/case/:code" element={<CaseStatus />} />
          <Route path="/reviewer" element={<Reviewer />} />
          <Route path="/reviewer/case/:id" element={<ReviewerCase />} />
          <Route path="/admin/schemes" element={<AdminSchemes />} />
          <Route path="/admin/security" element={<AdminSecurity />} />
          <Route path="/auth/digilocker/callback" element={<DigiLockerCallback />} />
          <Route path="/test-runs" element={<TestRuns />} />
          <Route path="/signin" element={<SignIn />} />
          <Route path="/profile" element={<Profile />} />
          <Route path="*" element={<div className="card">Page not found.</div>} />
        </Routes>
      </main>
      <KioskIdleGuard />
    </>
  );
}
