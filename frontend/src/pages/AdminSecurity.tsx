import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { ErrorNote, StaffBar, StaffLogin } from "../components";
import { useApp } from "../state";

type StaffRow = { user_id: string; email: string | null; role: string; mfa_enrolled: boolean; last_sign_in_at: string | null };
type AuthEventRow = { ts: string; event: string; actor_id: string; actor_role: string; ip_prefix: string | null; details: Record<string, unknown> };

/** Admin: staff accounts with their two-step sign-in state (reset when a phone is lost) and the last 500 auth events
 *  (actor id, event, time, IP prefix — no emails, codes or tokens are ever recorded). */
export default function AdminSecurity() {
  const { staff } = useApp();
  const [rows, setRows] = useState<StaffRow[] | null>(null);
  const [events, setEvents] = useState<AuthEventRow[] | null>(null);
  const [filter, setFilter] = useState("");
  const [err, setErr] = useState<unknown>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const isAdmin = staff?.role === "admin";

  const load = useCallback(async () => {
    setErr(null);
    try {
      const [s, e] = await Promise.all([api<{ staff: StaffRow[] }>("/admin/staff"), api<{ events: AuthEventRow[] }>("/admin/auth-events")]);
      setRows(s.staff); setEvents(e.events);
    } catch (x) { setErr(x); }
  }, []);
  useEffect(() => { if (isAdmin) load(); }, [isAdmin, load]);

  if (!isAdmin) return <StaffLogin roles={["admin"]} title="Admin sign-in (security)" hint="Staff two-step sign-in and the auth audit log." />;

  const reset = async (r: StaffRow) => {
    if (!window.confirm(`Reset two-step sign-in for ${r.email ?? r.user_id}? They will be signed out and must set up a new authenticator.`)) return;
    setErr(null); setMsg(null);
    try { const res = await api<{ factors_removed: number }>(`/admin/staff/${r.user_id}/reset-mfa`, { body: {} }); setMsg(`Removed ${res.factors_removed} authenticator(s).`); load(); }
    catch (x) { setErr(x); }
  };
  const shown = (events ?? []).filter((e) => !filter || e.event.includes(filter) || e.actor_id.includes(filter));

  return (
    <div className="stack">
      <StaffBar><button className="btn small" onClick={load}>Refresh</button></StaffBar>
      <h1>Security</h1>
      <ErrorNote error={err} />
      {msg && <div className="notice ok" role="status">{msg}</div>}
      <section className="card stack">
        <h2>Staff two-step sign-in</h2>
        <table className="events">
          <thead><tr><th>Account</th><th>Role</th><th>Authenticator</th><th>Last sign-in</th><th /></tr></thead>
          <tbody>
            {rows?.map((r) => (
              <tr key={r.user_id}>
                <td>{r.email ?? <span className="mono tiny">{r.user_id}</span>}</td><td>{r.role}</td>
                <td>{r.mfa_enrolled ? "✓ enrolled" : "not set up (asked at next sign-in)"}</td>
                <td className="tiny">{r.last_sign_in_at?.replace("T", " ").slice(0, 16) ?? "—"}</td>
                <td>{r.mfa_enrolled && <button className="btn small danger" onClick={() => reset(r)}>Reset</button>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
      <section className="card stack">
        <div className="row spread">
          <h2>Auth events <span className="chip">{events?.length ?? 0}</span></h2>
          <input type="search" placeholder="filter: event or actor id" value={filter} onChange={(e) => setFilter(e.target.value)} aria-label="Filter events" />
        </div>
        <table className="events">
          <thead><tr><th>Time (UTC)</th><th>Event</th><th>Actor</th><th>IP prefix</th><th>Details</th></tr></thead>
          <tbody>
            {shown.map((e, i) => (
              <tr key={`${e.ts}-${i}`}>
                <td className="tiny mono">{e.ts.replace("T", " ").slice(0, 19)}</td><td>{e.event}</td>
                <td className="tiny"><span className="mono">{e.actor_id}</span> ({e.actor_role})</td>
                <td className="tiny mono">{e.ip_prefix ?? "—"}</td>
                <td className="tiny mono">{Object.keys(e.details).length ? JSON.stringify(e.details) : ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
