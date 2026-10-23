import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";
import { ErrorNote, OutcomeBadge, StaffBar, StaffLogin, StatusBadge } from "../components";
import { useApp } from "../state";

const FILTERS = ["", "PENDING_REVIEW", "CORRECTION_REQUESTED", "REVIEWED"];

export default function Reviewer() {
  const { staff } = useApp();
  const nav = useNavigate();
  const [status, setStatus] = useState("PENDING_REVIEW");
  const [cases, setCases] = useState<any[] | null>(null);
  const [showTests, setShowTests] = useState(false);
  const [code, setCode] = useState("");
  const [err, setErr] = useState<unknown>(null);

  const isReviewer = staff && ["reviewer", "admin"].includes(staff.role);
  useEffect(() => {
    if (!isReviewer) return;
    api<{ cases: any[] }>(`/reviewer/cases${status ? `?status=${status}` : ""}`).then((r) => setCases(r.cases)).catch(setErr);
  }, [status, isReviewer]);

  if (!isReviewer) return <StaffLogin roles={["reviewer", "admin"]} title="Reviewer sign-in" hint="Role is checked on the server for every request." demo={["reviewer"]} />;

  const lookup = async (e: React.FormEvent) => {
    e.preventDefault(); setErr(null);
    try { nav(`/reviewer/case/${(await api<{ case_id: string }>("/reviewer/cases/lookup", { body: { code } })).case_id}`); } catch (x) { setErr(x); }
  };
  const shown = (cases ?? []).filter((c) => showTests || !c.is_test);

  return (
    <div className="stack">
      <StaffBar />
      <div className="row spread">
        <h1>Review queue</h1>
        <form className="row" onSubmit={lookup}>
          <input type="text" placeholder="Case code ANV-…" value={code} onChange={(e) => setCode(e.target.value)} aria-label="Case code" style={{ width: 200 }} />
          <button className="btn" type="submit">Open by code</button>
        </form>
      </div>
      <div className="row">
        <div className="seg" role="group" aria-label="Status filter">
          {FILTERS.map((f) => <button key={f} aria-pressed={status === f} onClick={() => setStatus(f)}>{f || "All"}</button>)}
        </div>
        <label className="row small"><input type="checkbox" checked={showTests} onChange={(e) => setShowTests(e.target.checked)} /> show test-runner cases</label>
      </div>
      <ErrorNote error={err} />
      <div className="card table-wrap">
        <table className="list">
          <thead><tr><th>Case</th><th>Scheme</th><th>Screening</th><th>Status</th><th>Origin</th><th>Updated</th></tr></thead>
          <tbody>
            {shown.length === 0 && <tr><td colSpan={6} className="muted">No cases.</td></tr>}
            {shown.map((c) => (
              <tr key={c.case_id}>
                <td><Link className="mono" to={`/reviewer/case/${c.case_id}`}>{c.case_id}</Link></td>
                <td>{c.scheme_name}</td>
                <td><OutcomeBadge outcome={c.screening_outcome} lang="en" /></td>
                <td><StatusBadge status={c.status} />{c.review_outcome && <div className="tiny">{c.review_outcome}</div>}</td>
                <td>{c.origin}{c.is_test && " · test"}</td>
                <td className="tiny">{c.updated_at}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="tiny">States shown are draft-review states. SUBMITTED_EXTERNAL is reserved for a real, verified government integration and never appears here.</p>
    </div>
  );
}
