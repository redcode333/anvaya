import { useEffect, useState } from "react";
import { api } from "../api";
import { ErrorNote, StaffBar, StaffLogin } from "../components";
import { STATES } from "../i18n";
import { useApp } from "../state";

function SchemeDetail({ id, onClose }: { id: string; onClose: () => void }) {
  const [s, setS] = useState<any>(null);
  useEffect(() => { api(`/schemes/${id}`).then(setS); }, [id]);
  if (!s) return null;
  return (
    <div className="card stack">
      <div className="row spread"><h2>{s.name}</h2><button className="btn small" onClick={onClose}>Close</button></div>
      <div className="row tiny"><span>{s.level}</span>·<span>{s.state ?? "Pan India"}</span>·<span>{s.department}</span>·<span className="mono">{s.scheme_id}</span></div>
      <div className="notice small">{s.freshness.label} · imported {s.freshness.imported_at} · review {s.freshness.review_status} · confidence {s.freshness.confidence}
        {s.quality_flags.length > 0 && <> · flags: {s.quality_flags.join(", ")}</>}</div>
      {s.rule && <p className="small">Structured rule: <span className="mono">{s.rule.rule_id} v{s.rule.version}</span> ({s.rule.review_status})</p>}
      <details open><summary>Eligibility (dataset text)</summary><p className="small" style={{ whiteSpace: "pre-wrap" }}>{s.eligibility_text}</p></details>
      <details><summary>Benefits</summary><p className="small" style={{ whiteSpace: "pre-wrap" }}>{s.benefits}</p></details>
      <details><summary>Documents (dataset text)</summary><p className="small" style={{ whiteSpace: "pre-wrap" }}>{s.documents_text}</p></details>
      <details><summary>Application process</summary><p className="small" style={{ whiteSpace: "pre-wrap" }}>{s.application_process}</p></details>
      <details><summary>Sources</summary><ul className="small">{s.sources.map((u: any, i: number) => <li key={i}>{u.label}: {u.url ? <a href={u.url} target="_blank" rel="noreferrer">{u.url}</a> : "no URL"}</li>)}</ul></details>
      <details><summary>Knowledge-graph neighbours</summary>
        {Object.entries(s.graph).map(([rel, nodes]: any) => nodes.length > 0 && (
          <div key={rel} className="small"><span className="mono tiny">{rel}</span>: {nodes.map((n: any) => n.label || n.name).join(" · ")}</div>
        ))}
      </details>
    </div>
  );
}

export default function AdminSchemes() {
  const { staff } = useApp();
  const [q, setQ] = useState(""), [state, setState] = useState(""), [level, setLevel] = useState(""), [hasRule, setHasRule] = useState(false);
  const [res, setRes] = useState<any>(null);
  const [fresh, setFresh] = useState<any>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [err, setErr] = useState<unknown>(null);
  const isStaff = staff && ["admin", "reviewer"].includes(staff.role);

  const search = () => {
    const p = new URLSearchParams({ q, state, level, limit: "40", ...(hasRule ? { has_rule: "1" } : {}) });
    api(`/schemes?${p}`).then(setRes).catch(setErr);
  };
  useEffect(() => { search(); }, [state, level, hasRule]); // eslint-disable-line react-hooks/exhaustive-deps
  const loadFresh = () => api("/admin/schemes/freshness").then(setFresh).catch(setErr);
  useEffect(() => { if (isStaff) loadFresh(); }, [isStaff]);

  const [verifying, setVerifying] = useState<{ rule_id: string; url: string } | null>(null);
  const verify = async () => {
    if (!verifying?.url) return;
    try { await api(`/admin/rules/${verifying.rule_id}/verify`, { body: { checked_source_url: verifying.url } }); setVerifying(null); loadFresh(); } catch (e) { setErr(e); }
  };

  const art = fresh?.artifacts?.[0];
  return (
    <div className="stack">
      {isStaff ? <StaffBar /> : null}
      <h1>Scheme catalogue & data freshness</h1>
      <p className="notice small">The dataset is an input catalogue, not proof that entries are current or official. Only the curated rules below are evaluated; every other record is shown with a verification caveat.</p>
      <ErrorNote error={err} />
      {!isStaff && <StaffLogin roles={["admin", "reviewer"]} title="Steward sign-in (freshness report)" hint="Admins can verify rules against official sources; reviewers can view." demo={["admin", "reviewer"]} />}
      {fresh && (
        <div className="grid two">
          <section className="card stack">
            <h2>Source artifact</h2>
            {art && <dl className="kv">
              <dt>File</dt><dd>{art.filename}</dd><dt>SHA-256</dt><dd className="mono tiny">{art.sha256}</dd>
              <dt>Rows</dt><dd>{art.row_count} ({art.report.distinct_names} distinct names after normalization)</dd>
              <dt>Jurisdictions</dt><dd>{Object.keys(art.report.states).length}</dd><dt>Imported</dt><dd>{art.imported_at}</dd>
              <dt>Quality flags</dt><dd>{Object.entries(art.report.flag_counts).map(([k, v]) => `${k}: ${v}`).join(" · ")}</dd>
              {art.report.duplicate_names.length > 0 && <><dt>Duplicate names</dt><dd>{art.report.duplicate_names.join(", ")}</dd></>}
            </dl>}
            <h3>Knowledge graph (relational)</h3>
            <div className="small">{Object.entries(fresh.graph.nodes).map(([k, v]) => `${k} ${v}`).join(" · ")}</div>
            <div className="small muted">{Object.entries(fresh.graph.edges).map(([k, v]) => `${k} ${v}`).join(" · ")}</div>
          </section>
          <section className="card stack">
            <h2>Curated rules · {fresh.bundle_version}</h2>
            <div className="table-wrap"><table className="list">
              <thead><tr><th>Rule</th><th>Review</th><th>Official source verified</th><th /></tr></thead>
              <tbody>{fresh.rules.map((r: any) => (
                <tr key={r.rule_id}>
                  <td><span className="mono tiny">{r.rule_id}</span><div className="small">{r.scheme_name}</div>{r.review_note && <div className="tiny">{r.review_note}</div>}</td>
                  <td><span className={`chip ${r.review_status === "team_reviewed" ? "on" : "off"}`}>{r.review_status}</span><div className="tiny">{r.reviewed_at}</div></td>
                  <td className="tiny">{r.source_verified_at ? `${r.source_verified_at} by ${r.source_verified_by}` : "not verified"}<div>freshness {r.freshness_days}d</div></td>
                  <td>{staff?.role === "admin" && (verifying?.rule_id === r.rule_id ? (
                    <div className="stack" style={{ minWidth: 220 }}>
                      <input type="text" aria-label="Official source URL checked" value={verifying?.url ?? ""} onChange={(e) => setVerifying({ rule_id: r.rule_id, url: e.target.value })} />
                      <div className="row"><button className="btn small primary" onClick={verify}>Confirm</button><button className="btn small" onClick={() => setVerifying(null)}>Cancel</button></div>
                    </div>) : <button className="btn small" onClick={() => setVerifying({ rule_id: r.rule_id, url: r.source_url })}>Verify</button>)}</td>
                </tr>))}</tbody>
            </table></div>
          </section>
        </div>
      )}
      <section className="card stack">
        <h2>Search catalogue</h2>
        <form className="row" onSubmit={(e) => { e.preventDefault(); search(); }}>
          <input type="text" placeholder="keyword e.g. old age pension" value={q} onChange={(e) => setQ(e.target.value)} style={{ flex: "2 1 220px" }} aria-label="Keyword" />
          <select value={state} onChange={(e) => setState(e.target.value)} style={{ flex: "1 1 160px" }} aria-label="State"><option value="">All states</option>{STATES.map((s) => <option key={s}>{s}</option>)}</select>
          <select value={level} onChange={(e) => setLevel(e.target.value)} style={{ flex: "1 1 120px" }} aria-label="Level"><option value="">Any level</option><option>Central</option><option>State</option></select>
          <label className="row small"><input type="checkbox" checked={hasRule} onChange={(e) => setHasRule(e.target.checked)} /> curated rule only</label>
          <button className="btn primary" type="submit">Search</button>
        </form>
        {res && <p className="tiny">{res.total} matching records{state && " (state + central)"}</p>}
        {open && <SchemeDetail id={open} onClose={() => setOpen(null)} />}
        <div className="table-wrap"><table className="list">
          <thead><tr><th>Scheme</th><th>Jurisdiction</th><th>Category</th><th>Status</th></tr></thead>
          <tbody>{res?.items.map((s: any) => (
            <tr key={s.scheme_id}>
              <td><button className="btn ghost small" style={{ textAlign: "left", padding: 0 }} onClick={() => setOpen(s.scheme_id)}>{s.name}</button>
                <div className="tiny">{s.brief_description?.slice(0, 140)}</div></td>
              <td className="small">{s.level}{s.state ? ` · ${s.state}` : ""}</td>
              <td className="tiny">{s.categories}</td>
              <td>{s.has_reviewed_rule ? <span className="chip on">rule {s.rule_id}</span> : <span className="chip">catalogue only</span>}
                {s.quality_flags.length > 0 && <div className="tiny">{s.quality_flags.join(", ")}</div>}</td>
            </tr>))}</tbody>
        </table></div>
      </section>
    </div>
  );
}
