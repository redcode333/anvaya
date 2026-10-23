import { useEffect, useState, type ReactNode } from "react";
import { api, ApiError } from "./api";
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

// Staff accounts still on their public demo password (none when ANVAYA_*_PASSWORD are set): only these are hinted.
let demoAccounts: Promise<Record<string, string>> | null = null;
export function useDemoAccounts(): Record<string, string> {
  const [acc, setAcc] = useState<Record<string, string>>({});
  useEffect(() => {
    demoAccounts ??= api<{ accounts: { username: string; password: string }[] }>("/auth/demo-accounts", { auth: false })
      .then((r) => Object.fromEntries(r.accounts.map((a) => [a.username, a.password])))
      .catch(() => ({}));
    demoAccounts.then(setAcc);
  }, []);
  return acc;
}

export function DemoCreds({ users }: { users: string[] }) {
  const acc = useDemoAccounts();
  const shown = users.filter((u) => acc[u]);
  if (!shown.length) return null;
  return <>Demo account{shown.length > 1 ? "s" : ""}: {shown.map((u, i) => <span key={u}>{i > 0 && " · "}<span className="mono">{u} / {acc[u]}</span></span>)}.</>;
}

export function StaffLogin({ roles, title, hint, demo = [] }: { roles: string[]; title: string; hint: string; demo?: string[] }) {
  const { setStaff } = useApp();
  const [u, setU] = useState(""), [p, setP] = useState("");
  const [err, setErr] = useState<unknown>(null);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr(null);
    try {
      const r = await api<{ token: string; user: any }>("/auth/login", { body: { username: u, password: p }, auth: false });
      if (!roles.includes(r.user.role)) throw new ApiError("FORBIDDEN", `This page needs a ${roles.join(" or ")} account.`, 403);
      setStaff(r.user, r.token);
    } catch (x) { setErr(x); }
  };
  return (
    <form className="card stack" style={{ maxWidth: 420 }} onSubmit={submit}>
      <h2>{title}</h2>
      <p className="small muted">{hint} <DemoCreds users={demo} /></p>
      <label className="field">Username<input type="text" value={u} onChange={(e) => setU(e.target.value)} autoComplete="username" /></label>
      <label className="field">Password<input type="password" value={p} onChange={(e) => setP(e.target.value)} autoComplete="current-password" /></label>
      <ErrorNote error={err} />
      <button className="btn primary" type="submit">Sign in</button>
      <p className="tiny">Seeded staff accounts only — not production identity.</p>
    </form>
  );
}

export function StaffBar({ children }: { children?: ReactNode }) {
  const { staff, setStaff } = useApp();
  if (!staff) return null;
  return (
    <div className="row spread small muted" style={{ marginBottom: "1rem" }}>
      <span>Signed in as <strong>{staff.display_name}</strong> ({staff.role})</span>
      <span className="row">{children}<button className="btn small" onClick={() => setStaff(null, null)}>Sign out</button></span>
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
