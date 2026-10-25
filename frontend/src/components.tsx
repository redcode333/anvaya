import { useEffect, useRef, useState, type ReactNode } from "react";
import type { ApiError } from "./api";
import { changeStaffPassword, nextMfaStep, staffSignIn, verifyMfa, type AuthLike, type MfaStep } from "./account";
import { supabase } from "./auth";
import { useCaptcha } from "./Turnstile";
import { attrLabel, BOOL_ATTRS, ENUMS, NUM_ATTRS, OUTCOME_LABEL, STATES, type Lang } from "./i18n";
import { useApp } from "./state";

export function ErrorNote({ error }: { error: unknown }) {
  if (!error) return null;
  const e = error as ApiError;
  return (
    <div className="notice error" role="alert">
      <strong>{e.code || "Error"}</strong> — {e.message}
      {e.requestId && <span className="tiny"> · request {e.requestId}</span>}
    </div>
  );
}

export function OutcomeBadge({ outcome, lang }: { outcome: string; lang: Lang }) {
  return <span className={`badge o-${outcome}`}>{OUTCOME_LABEL[outcome]?.[lang] ?? outcome}</span>;
}

export function StatusBadge({ status }: { status: string }) {
  return <span className={`badge s-${status}`}>{status}</span>;
}

const authClient = () => supabase!.auth as unknown as AuthLike;

/** Second step for staff: enrol an authenticator on the first sign-in (QR code, or the key typed in by hand), else
 *  enter the current 6-digit code. Only then does the server accept this sign-in for staff pages (aal2). */
export function MfaStepCard() {
  const { refreshAuth, signOut, staffPendingMfa } = useApp();
  const [step, setStep] = useState<MfaStep | null>(null);
  const [code, setCode] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [err, setErr] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const started = useRef(false);  // once per mount, also under StrictMode: a second enrol would replace the QR shown
  useEffect(() => {
    if (started.current) return;
    started.current = true;
    nextMfaStep(authClient()).then(setStep).catch(setErr);
  }, []);
  const verify = async (e: React.FormEvent) => {
    e.preventDefault(); setErr(null); setBusy(true);
    try { await verifyMfa(authClient(), step!, code); await refreshAuth(); } catch (x) { setErr(x); setCode(""); }
    setBusy(false);
  };
  return (
    <form className="card stack" style={{ maxWidth: 460 }} onSubmit={verify}>
      <h2>{step?.kind === "enroll" ? "Set up two-step sign-in" : "Enter your authenticator code"}</h2>
      <p className="small muted">Signed in as {staffPendingMfa?.display_name}. Staff accounts need a code from an authenticator app (Google Authenticator, Microsoft Authenticator, Aegis…) on every sign-in.</p>
      {step?.kind === "enroll" && (
        <div className="stack">
          <ol className="small" style={{ margin: 0, paddingLeft: "1.1rem" }}>
            <li>Open the authenticator app and add an account.</li>
            <li>Scan this QR code — or choose “enter a setup key” and type the key below.</li>
            <li>Type the 6-digit code the app shows.</li>
          </ol>
          <img src={step.qr} alt="QR code for the authenticator app" width={200} height={200} className="qr" />
          <button type="button" className="btn small" onClick={() => setShowKey((s) => !s)} aria-expanded={showKey}>{showKey ? "Hide" : "Can't scan? Show"} setup key</button>
          {showKey && <code className="mono setup-key" aria-label="Setup key">{step.secret.replace(/(.{4})/g, "$1 ").trim()}</code>}
        </div>
      )}
      <label className="field">6-digit code
        <input type="text" inputMode="numeric" autoComplete="one-time-code" value={code} maxLength={6} required autoFocus
          onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))} />
      </label>
      <ErrorNote error={err} />
      <div className="row">
        <button className="btn primary" type="submit" disabled={busy || !step || code.length !== 6}>Verify</button>
        <button className="btn ghost" type="button" onClick={() => signOut()}>Cancel</button>
      </div>
      <p className="tiny">Lost the phone? An administrator can reset your two-step sign-in; you then set it up again.</p>
    </form>
  );
}

export function StaffLogin({ roles, title, hint }: { roles: string[]; title: string; hint: string }) {
  const { refreshAuth, staffPendingMfa, lang } = useApp();
  const [email, setEmail] = useState(""), [p, setP] = useState("");
  const [err, setErr] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const captcha = useCaptcha(lang);
  if (!supabase) return <div className="card notice" style={{ maxWidth: 420 }}>Staff sign-in needs Supabase Auth (VITE_SUPABASE_URL / VITE_SUPABASE_PUBLISHABLE_KEY).</div>;
  if (staffPendingMfa && roles.includes(staffPendingMfa.role)) return <MfaStepCard />;
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr(null); setBusy(true);
    try { await staffSignIn(authClient(), email.trim(), p, roles, undefined, captcha.token); setP(""); await refreshAuth(); }
    catch (x) { setErr(x); }
    finally { captcha.used(); }
    setBusy(false);
  };
  return (
    <form className="card stack" style={{ maxWidth: 420 }} onSubmit={submit}>
      <h2>{title}</h2>
      {hint && <p className="small muted">{hint}</p>}
      <label className="field">Email<input type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="username" required /></label>
      <label className="field">Password<input type="password" value={p} onChange={(e) => setP(e.target.value)} autoComplete="current-password" required /></label>
      {captcha.widget}
      <ErrorNote error={err} />
      <button className="btn primary" type="submit" disabled={busy || !captcha.ready}>Sign in</button>
      <p className="tiny">Staff accounts are created by an administrator; the role and the authenticator code are checked by the server on every request.</p>
    </form>
  );
}

function ChangePassword({ onClose }: { onClose: () => void }) {
  const { refreshAuth } = useApp();
  const [p1, setP1] = useState(""), [p2, setP2] = useState("");
  const [err, setErr] = useState<unknown>(null);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault(); setErr(null);
    if (p1 !== p2) { setErr({ code: "MISMATCH", message: "The two passwords differ." }); return; }
    try { await changeStaffPassword(authClient(), p1); await refreshAuth(); onClose(); } catch (x) { setErr(x); }
  };
  return (
    <form className="card stack" style={{ maxWidth: 420 }} onSubmit={submit}>
      <h3>Change password</h3>
      <p className="tiny">After the change you are signed out on every device, this one included.</p>
      <label className="field">New password<input type="password" autoComplete="new-password" minLength={12} value={p1} onChange={(e) => setP1(e.target.value)} required /></label>
      <label className="field">Repeat<input type="password" autoComplete="new-password" minLength={12} value={p2} onChange={(e) => setP2(e.target.value)} required /></label>
      <ErrorNote error={err} />
      <div className="row"><button className="btn primary" type="submit">Change and sign out everywhere</button><button className="btn ghost" type="button" onClick={onClose}>Cancel</button></div>
    </form>
  );
}

export function StaffBar({ children }: { children?: ReactNode }) {
  const { staff, signOut, signOutAll } = useApp();
  const [changing, setChanging] = useState(false);
  if (!staff) return null;
  return (
    <div className="stack" style={{ marginBottom: "1rem" }}>
      <div className="row spread small muted">
        <span>Signed in as <strong>{staff.display_name}</strong> ({staff.role})</span>
        <span className="row">{children}
          <button className="btn small ghost" onClick={() => setChanging(true)}>Change password</button>
          <button className="btn small ghost" onClick={() => signOutAll()}>Sign out of all devices</button>
          <button className="btn small" onClick={() => signOut()}>Sign out</button></span>
      </div>
      {changing && <ChangePassword onClose={() => setChanging(false)} />}
    </div>
  );
}

/** Kiosk: who is operating this device; signing out ends every citizen session on it. */
export function KioskOperatorBar() {
  const { staff, signOut } = useApp();
  if (!staff) return null;
  return (
    <div className="row spread small muted">
      <span>Kiosk operator: <strong>{staff.display_name}</strong></span>
      <button className="btn small" onClick={() => signOut()}>Operator sign out (ends all sessions on this kiosk)</button>
    </div>
  );
}

export function ValueInput({ attr, value, onChange, lang }: { attr: string; value: any; onChange: (v: any) => void; lang: Lang }) {
  const id = `in-${attr}`;
  if (attr === "state")
    return (
      <select id={id} aria-label={attrLabel(attr, lang)} value={value ?? ""} onChange={(e) => onChange(e.target.value || null)}>
        <option value="">—</option>{STATES.map((s) => <option key={s}>{s}</option>)}
      </select>
    );
  if (ENUMS[attr])
    return (
      <select id={id} aria-label={attrLabel(attr, lang)} value={value ?? ""} onChange={(e) => onChange(e.target.value || null)}>
        <option value="">—</option>{ENUMS[attr].map((s) => <option key={s} value={s}>{s.replace(/_/g, " ")}</option>)}
      </select>
    );
  if (BOOL_ATTRS.includes(attr))
    return (
      <div className="seg" role="group" aria-label={attrLabel(attr, lang)}>
        {[true, false].map((b) => (
          <button type="button" key={String(b)} aria-pressed={value === b} onClick={() => onChange(b)}>
            {b ? { en: "Yes", hi: "हाँ", te: "అవును" }[lang] : { en: "No", hi: "नहीं", te: "కాదు" }[lang]}
          </button>
        ))}
      </div>
    );
  return (
    <input id={id} aria-label={attrLabel(attr, lang)} type={NUM_ATTRS.includes(attr) ? "number" : "text"} inputMode={NUM_ATTRS.includes(attr) ? "numeric" : undefined}
      value={value ?? ""} onChange={(e) => onChange(NUM_ATTRS.includes(attr) ? (e.target.value === "" ? null : Number(e.target.value)) : e.target.value)} />
  );
}

export function Json({ data }: { data: unknown }) {
  return <pre className="json">{JSON.stringify(data, null, 2)}</pre>;
}
