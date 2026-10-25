import { useState, type ReactNode } from "react";
import type { ApiError } from "./api";
import { staffSignIn, type AuthLike } from "./account";
import { supabase } from "./auth";
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

export function StaffLogin({ roles, title, hint }: { roles: string[]; title: string; hint: string }) {
  const { refreshAuth } = useApp();
  const [email, setEmail] = useState(""), [p, setP] = useState("");
  const [err, setErr] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  if (!supabase) return <div className="card notice" style={{ maxWidth: 420 }}>Staff sign-in needs Supabase Auth (VITE_SUPABASE_URL / VITE_SUPABASE_PUBLISHABLE_KEY).</div>;
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr(null); setBusy(true);
    try { await staffSignIn(supabase!.auth as unknown as AuthLike, email.trim(), p, roles); await refreshAuth(); } catch (x) { setErr(x); }
    setBusy(false);
  };
  return (
    <form className="card stack" style={{ maxWidth: 420 }} onSubmit={submit}>
      <h2>{title}</h2>
      {hint && <p className="small muted">{hint}</p>}
      <label className="field">Email<input type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="username" required /></label>
      <label className="field">Password<input type="password" value={p} onChange={(e) => setP(e.target.value)} autoComplete="current-password" required /></label>
      <ErrorNote error={err} />
      <button className="btn primary" type="submit" disabled={busy}>Sign in</button>
      <p className="tiny">Staff accounts are created by an administrator; the role is checked by the server on every request.</p>
    </form>
  );
}

export function StaffBar({ children }: { children?: ReactNode }) {
  const { staff, signOut } = useApp();
  if (!staff) return null;
  return (
    <div className="row spread small muted" style={{ marginBottom: "1rem" }}>
      <span>Signed in as <strong>{staff.display_name}</strong> ({staff.role})</span>
      <span className="row">{children}<button className="btn small" onClick={() => signOut()}>Sign out</button></span>
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
