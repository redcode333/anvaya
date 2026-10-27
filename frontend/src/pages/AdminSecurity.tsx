import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { PageHead, Stat, Stats, Tabs } from "../AdminUI";
import { ErrorNote, StaffBar, StaffLogin } from "../components";
import { useApp } from "../state";

type StaffRow = { user_id: string; email: string | null; role: string; mfa_enrolled: boolean; last_sign_in_at: string | null };
type JobRun = { run_id: string; job: string; trigger: string; started_at: string; finished_at: string | null; status: string; counts: Record<string, unknown> };
type AuthEventRow = { ts: string; event: string; actor_id: string; actor_role: string; ip_prefix: string | null; details: Record<string, unknown> };
type Tab = "staff" | "jobs" | "events";

/** Admin: staff accounts with their two-step sign-in state (reset when a phone is lost) and the last 500 auth events
 *  (actor id, event, time, IP prefix — no emails, codes or tokens are ever recorded). */
export default function AdminSecurity() {
  const { staff } = useApp();
  const [rows, setRows] = useState<StaffRow[] | null>(null);
  const [events, setEvents] = useState<AuthEventRow[] | null>(null);
  const [runs, setRuns] = useState<JobRun[] | null>(null);
  const [tab, setTab] = useState<Tab>("staff");
  const [filter, setFilter] = useState("");
  const [err, setErr] = useState<unknown>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const isAdmin = staff?.role === "admin";

  const load = useCallback(async () => {
    setErr(null);
    try {
      // Independent sources: one failing (e.g. the Auth admin API behind the staff list) must not blank the others.
      const [s, e, j] = await Promise.allSettled([api<{ staff: StaffRow[] }>("/admin/staff"), api<{ events: AuthEventRow[] }>("/admin/auth-events"),
        api<{ runs: JobRun[] }>("/admin/jobs")]);
      if (s.status === "fulfilled") setRows(s.value.staff);
      if (e.status === "fulfilled") setEvents(e.value.events);
      if (j.status === "fulfilled") setRuns(j.value.runs);
      const failed = [s, e, j].find((r): r is PromiseRejectedResult => r.status === "rejected");
      if (failed) setErr(failed.reason);
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
  const withoutMfa = rows?.filter((r) => !r.mfa_enrolled).length;
  const lastRun = runs?.[0];
  const failedRuns = runs?.filter((r) => r.status !== "success").length;

  return (
    <div className="stack">
      <StaffBar><button className="btn small" onClick={load}>Refresh</button></StaffBar>
      <PageHead title="Security" sub="Staff two-step sign-in, background jobs and the sign-in audit log." />
      <ErrorNote error={err} />
      {msg && <div className="notice ok" role="status">{msg}</div>}
      <Stats>
        <Stat label="Staff accounts" value={rows?.length ?? "—"} />
        <Stat label="Without two-step sign-in" value={withoutMfa ?? "—"} tone={withoutMfa ? "warn" : "ok"} hint={withoutMfa ? "asked at next sign-in" : undefined} />
        <Stat label="Last background job" value={lastRun ? (lastRun.status === "success" ? "✓ ok" : lastRun.status) : "—"} tone={lastRun && lastRun.status !== "success" ? "bad" : "ok"}
          hint={lastRun ? `${lastRun.job} · ${lastRun.started_at.replace("T", " ").slice(0, 16)} UTC` : undefined} />
        <Stat label="Failed job runs" value={failedRuns ?? "—"} tone={failedRuns ? "bad" : "ok"} />
      </Stats>
      <Tabs label="Security sections" value={tab} onChange={setTab} tabs={[
        { id: "staff", label: "Staff sign-in", count: rows?.length ?? 0 },
        { id: "jobs", label: "Background jobs", count: runs?.length ?? 0 },
        { id: "events", label: "Auth events", count: events?.length ?? 0 },
      ]} />

      {tab === "staff" && (
        <section className="card stack" role="tabpanel">
          <div className="table-wrap"><table className="events">
            <thead><tr><th>Account</th><th>Role</th><th>Authenticator</th><th>Last sign-in</th><th /></tr></thead>
            <tbody>
              {rows?.map((r) => (
                <tr key={r.user_id}>
                  <td>{r.email ?? <span className="mono tiny">{r.user_id}</span>}</td><td><span className="chip">{r.role}</span></td>
                  <td>{r.mfa_enrolled ? <span className="chip on">✓ enrolled</span> : <span className="chip off">not set up</span>}</td>
                  <td className="tiny">{r.last_sign_in_at?.replace("T", " ").slice(0, 16) ?? "—"}</td>
                  <td>{r.mfa_enrolled && <button className="btn small danger" onClick={() => reset(r)}>Reset</button>}</td>
                </tr>
              ))}
            </tbody>
          </table></div>
          <p className="tiny">Reset removes a person's authenticator when their phone is lost; they sign in again and set up a new one.</p>
        </section>
      )}

      {tab === "jobs" && (
        <section className="card stack" role="tabpanel">
          <p className="tiny">Retention and cleanup run hourly (scheduled call, which also wakes the server) and are recorded here: counts only.</p>
          <div className="table-wrap"><table className="events">
            <thead><tr><th>Started (UTC)</th><th>Job</th><th>Trigger</th><th>Status</th><th>Finished</th><th>Counts</th></tr></thead>
            <tbody>
              {runs?.map((r) => (
                <tr key={r.run_id}>
                  <td className="tiny mono">{r.started_at.replace("T", " ").slice(0, 19)}</td><td>{r.job}</td><td>{r.trigger}</td>
                  <td>{r.status === "success" ? <span className="chip on">✓ success</span> : <span className="chip off">{r.status}</span>}</td>
                  <td className="tiny mono">{r.finished_at?.replace("T", " ").slice(11, 19) ?? "—"}</td>
                  <td className="tiny mono" style={{ wordBreak: "break-word" }}>{Object.keys(r.counts).length ? JSON.stringify(r.counts) : ""}</td>
                </tr>
              ))}
            </tbody>
          </table></div>
        </section>
      )}

      {tab === "events" && (
        <section className="card stack" role="tabpanel">
          <div className="row spread">
            <p className="tiny">The last 500 sign-in events. Actor id and IP prefix only — never emails, codes or tokens.</p>
            <input type="search" placeholder="filter: event or actor id" value={filter} onChange={(e) => setFilter(e.target.value)} aria-label="Filter events" />
          </div>
          <div className="table-wrap"><table className="events">
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
              {shown.length === 0 && <tr><td colSpan={5} className="muted">No events{filter ? " match the filter" : ""}.</td></tr>}
            </tbody>
          </table></div>
        </section>
      )}
    </div>
  );
}
