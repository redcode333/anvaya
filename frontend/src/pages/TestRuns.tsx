import { useEffect, useState } from "react";
import { api } from "../api";
import { ErrorNote, Json } from "../components";

type Run = { tc_id: string; title: string; expected: string; passed: boolean; ran_at: string; run_id: string; input: any; actual: any; checks: { name: string; passed: boolean; detail: any }[] };

export default function TestRuns() {
  const [defs, setDefs] = useState<Record<string, { title: string; expected: string }>>({});
  const [runs, setRuns] = useState<Record<string, Run | null>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<unknown>(null);

  const load = () => api<any>("/test-runs").then((r) => { setDefs(r.definitions); setRuns(r.latest); }).catch(setErr);
  useEffect(() => { load(); }, []);

  const run = async (tc: string) => {
    setBusy(tc); setErr(null);
    try { const r = await api<Run>(`/test-runs/${tc}`, { body: {} }); setRuns((x) => ({ ...x, [tc]: r })); } catch (e) { setErr(e); }
    setBusy(null);
  };
  const runAll = async () => { for (const tc of Object.keys(defs)) await run(tc); };
  const reset = async () => { await api("/test-runs/reset", { body: {} }); load(); };

  return (
    <div className="stack">
      <div className="row spread">
        <h1>Official scenarios TC1–TC4</h1>
        <div className="row">
          {Object.keys(defs).map((tc) => <button key={tc} className="btn" disabled={!!busy} onClick={() => run(tc)}>{busy === tc ? "…" : `Run ${tc}`}</button>)}
          <button className="btn primary" disabled={!!busy} onClick={runAll}>Run all</button>
          <button className="btn ghost" onClick={reset}>Reset</button>
        </div>
      </div>
      <p className="small muted">Each scenario creates an isolated test session and runs the real pipeline (extraction → confirmation → deterministic rules → drafts). Evidence is saved with every run.</p>
      <ErrorNote error={err} />
      {Object.entries(defs).map(([tc, d]) => {
        const r = runs[tc];
        return (
          <section key={tc} className="card stack">
            <div className="row spread">
              <h2>{tc} · {d.title}</h2>
              {r ? <span className={`badge ${r.passed ? "o-MATCH" : "o-MISMATCH"}`}>{r.passed ? "PASS" : "FAIL"}</span> : <span className="chip">not run</span>}
            </div>
            <p className="small"><strong>Expected:</strong> {d.expected}</p>
            {r && (<>
              <ul className="small" style={{ margin: 0, paddingLeft: "1.1rem" }}>
                {r.checks.map((c) => <li key={c.name} className={c.passed ? "c-PASS" : "c-FAIL"}>{c.passed ? "✓" : "✗"} <span style={{ color: "var(--ink)" }}>{c.name}</span></li>)}
              </ul>
              <div className="tiny mono">{r.run_id} · {r.ran_at}</div>
              <details><summary>Input</summary><Json data={r.input} /></details>
              <details><summary>Actual result & evidence</summary><Json data={r.actual} /></details>
              <details><summary>Check details</summary><Json data={r.checks} /></details>
            </>)}
          </section>
        );
      })}
    </div>
  );
}
