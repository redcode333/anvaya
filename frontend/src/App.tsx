import { useEffect, useState } from "react";
import { NavLink, Route, Routes, useLocation } from "react-router-dom";
import { KioskIdleGuard } from "./AccountUI";
import { StopAudioPill } from "./ListenControls";
import { stopSpeaking } from "./speech";
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
import Staff from "./pages/Staff";
import TestRuns from "./pages/TestRuns";
import { useApp } from "./state";

/** Connection and offline-bundle details. Shown only where they matter: at a kiosk, when the connection is down, or
 *  while kiosk events wait in the outbox. Public pages (the landing page above all) stay uncluttered. */
function StatusBar() {
  const { online, simulateOffline, setSimulateOffline, lang, mode } = useApp();
  const loc = useLocation();
  const [tick, setTick] = useState(0);
  useEffect(() => { const i = setInterval(() => setTick((x) => x + 1), 2000); return () => clearInterval(i); }, []);
  const bundle = getBundle();
  const pending = getOutbox().filter((e) => e.sync.state !== "SYNCED").length;
  void tick;
  const staffPage = /^\/(staff|reviewer|admin|test-runs)/.test(loc.pathname);
  const kioskPage = mode === "kiosk" && !staffPage && loc.pathname !== "/";
  if (loc.pathname === "/" || (!kioskPage && online && pending === 0)) return null;
  return (
    <div className="statusbar" role="status" aria-live="polite">
      <span className={`chip dot ${online ? "on" : "off"}`}>{online ? t("online", lang) : t("offline", lang)}</span>
      {kioskPage && (
        <>
          <label className="row small" style={{ gap: ".3rem" }}>
            <input type="checkbox" checked={simulateOffline} onChange={(e) => setSimulateOffline(e.target.checked)} /> simulate network loss
          </label>
          <span className="chip">bundle {bundle ? `${bundle.bundle_version} · ${bundle.rules.length} rules · ${new Date(bundle.generated_at).toLocaleString()}` : "not cached"}</span>
        </>
      )}
      {pending > 0 && <span className="chip s-SYNC_PENDING">outbox: {pending} SYNC_PENDING</span>}
    </div>
  );
}

/** The site language: a segmented control whose highlight slides to the chosen language. */
function LangSwitch() {
  const { lang, setLang } = useApp();
  const idx = Math.max(0, LANGS.findIndex((l) => l.code === lang));
  return (
    <div className="lang-switch" role="group" aria-label="Language" style={{ ["--i" as string]: idx, ["--n" as string]: LANGS.length }}>
      <span className="lang-thumb" aria-hidden="true" />
      {LANGS.map((l) => (
        <button key={l.code} type="button" aria-pressed={lang === l.code} onClick={() => setLang(l.code)}>{l.name}</button>
      ))}
    </div>
  );
}

/** Profile shortcut: the account page when signed in, the sign-in page otherwise. */
function ProfileButton() {
  const { staff, citizen } = useApp();
  const signedIn = !!staff || (!!citizen && !citizen.is_anonymous);
  const label = signedIn ? "Profile" : "Sign in";
  return (
    <NavLink to={signedIn ? "/profile" : "/signin"} className="profile-btn" aria-label={label} title={label}>
      <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <circle cx="12" cy="8" r="4" /><path d="M4 21c0-4.4 3.6-7 8-7s8 2.6 8 7" />
      </svg>
      <span className="profile-label">{label}</span>
    </NavLink>
  );
}

export default function App() {
  const { mode, lang, staff, sessionId, endCitizenSession } = useApp();
  const loc = useLocation();
  const landing = loc.pathname === "/";
  const role = staff?.role;
  const reviewer = role === "reviewer" || role === "admin";
  // Pages that belong to a conversation in progress. Opening the Citizen tab from anywhere else starts a new one: a
  // saved session is only picked up on purpose (Resume with Passport code, My Passports), never by browsing back.
  const inJourney = loc.pathname === "/citizen" || /^\/citizen\/(schemes|documents|draft)(\/|$)/.test(loc.pathname);
  const startFresh = () => { if (mode !== "kiosk" && sessionId && !inJourney) endCitizenSession("user"); };
  // Audio never carries over to another page.
  useEffect(() => { stopSpeaking(); }, [loc.pathname]);
  const inStaffArea = /^\/(staff|reviewer|admin|test-runs|profile)/.test(loc.pathname);
  return (
    <>
      <header className={`topbar${landing ? " is-landing" : ""}`}>
        <div className="topbar-inner">
          <NavLink to="/" className="brand">
            <img className="brand-mark light" src="/brand/anvaya-mark.svg" alt="" width="28" height="28" />
            <img className="brand-mark dark" src="/brand/anvaya-mark-white.svg" alt="" width="28" height="28" />
            Anvaya AI
          </NavLink>
          {/* The landing page shows the name and logo with the profile and language buttons; the rest of the site
              also gets the public tabs and a Staff door. */}
          {!landing && (
            <>
              <nav className="nav" aria-label="Main">
                <NavLink to={mode === "kiosk" ? "/kiosk" : "/citizen"} onClick={startFresh}>Citizen</NavLink>
                {mode !== "kiosk" && <NavLink to="/citizen/passports">{t("myPassports", lang)}</NavLink>}
                <NavLink to="/case">Case status</NavLink>
                {/* The public tabs end with one "Staff" door (/staff: sign-in, or a hub for the signed-in role). The role tabs
                    only show inside the staff area, so a signed-in admin browsing as a citizen never sees Security. */}
                {inStaffArea && reviewer && <NavLink to="/reviewer">Reviewer</NavLink>}
                {inStaffArea && reviewer && <NavLink to="/admin/schemes">Catalogue</NavLink>}
                {inStaffArea && role === "admin" && <NavLink to="/admin/security">Security</NavLink>}
                {inStaffArea && role === "admin" && <NavLink to="/test-runs">TC1–TC5</NavLink>}
                <NavLink to="/staff">Staff</NavLink>
              </nav>
            </>
          )}
          <div className="topbar-actions">
            <LangSwitch />
            <ProfileButton />
          </div>
        </div>
        <StatusBar />
      </header>
      <main className={loc.pathname === "/" ? "main-landing" : undefined}>
        <div key={loc.pathname.startsWith("/reviewer/case") ? "/reviewer/case" : loc.pathname} className="page-enter">
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
          <Route path="/staff" element={<Staff />} />
          <Route path="/profile" element={<Profile />} />
          <Route path="*" element={<div className="card">Page not found.</div>} />
        </Routes>
        </div>
      </main>
      <KioskIdleGuard />
      <StopAudioPill />
    </>
  );
}
