import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import { PageHead, Stat, Stats, Tabs } from "../AdminUI";
import { ErrorNote, Json, OutcomeBadge, StaffBar, StaffLogin, StatusBadge } from "../components";
import { attrLabel, showValue } from "../i18n";
import { useApp } from "../state";

/** An uploaded document: preview through a 2-minute view link (every view is audited), then Verify or ask again. */
function UploadReview({ caseId, sessionId, docKey, upload, closed, onChange }: {
  caseId: string; sessionId: string; docKey: string; upload: any; closed: boolean; onChange: () => void;
}) {
  const [preview, setPreview] = useState<{ url: string; type: string } | null>(null);
  const [err, setErr] = useState<unknown>(null);
  const open = async () => {
    setErr(null);
    try { const v = await api<any>(`/sessions/${sessionId}/documents/${docKey}/view-url`); setPreview({ url: v.view_url, type: v.content_type }); }
    catch (e) { setErr(e); }
  };
  const decide = async (action: "verify" | "request_reupload") => {
    setErr(null);
    try { await api(`/reviewer/cases/${caseId}/documents/${docKey}`, { body: { action } }); setPreview(null); onChange(); }
    catch (e) { setErr(e); }
  };
  return (
    <div className="stack small" style={{ marginLeft: "1.6rem" }}>
      <div className="row">
        <span className={`chip ${upload.status === "verified" ? "on" : ""}`}>📎 {upload.status} · {upload.content_type} · {Math.round(upload.size_bytes / 1024)} KB</span>
        <button className="btn small" onClick={open}>Preview</button>
        {!closed && upload.status !== "verified" && <>
          <button className="btn small primary" onClick={() => decide("verify")}>Verify</button>
          <button className="btn small danger" onClick={() => decide("request_reupload")}>Request re-upload</button>
        </>}
      </div>
      {preview && (preview.type.startsWith("image/")
        ? <img src={preview.url} alt={`Uploaded ${docKey}`} style={{ maxWidth: "100%", maxHeight: 420, border: "1px solid var(--line)", borderRadius: 8 }} />
        : <iframe src={preview.url} title={`Uploaded ${docKey}`} style={{ width: "100%", height: 480, border: "1px solid var(--line)", borderRadius: 8 }} />)}
      {preview && <span className="tiny">Link valid 2 minutes; this view is recorded in the audit trail.</span>}
      <ErrorNote error={err} />
    </div>
  );
}

export default function ReviewerCase() {
  const { id } = useParams();
  const { staff } = useApp();
  const [c, setC] = useState<any>(null);
  const [err, setErr] = useState<unknown>(null);
  const [note, setNote] = useState("");
  const [outcome, setOutcome] = useState("appears_eligible");
  const [verify, setVerify] = useState<string[]>([]);
  const [done, setDone] = useState("");
  const [tab, setTab] = useState<"facts" | "trace" | "docs" | "audit">("facts");

  const ok = staff && ["reviewer", "admin"].includes(staff.role);
  const load = () => api(`/reviewer/cases/${id}`).then(setC).catch(setErr);
  useEffect(() => { if (ok) load(); }, [id, ok]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!ok) return <StaffLogin roles={["reviewer", "admin"]} title="Reviewer sign-in" hint="" />;
  if (!c) return <ErrorNote error={err} />;

  const act = async (action: string) => {
    setErr(null); setDone("");
    try {
      const r = await api<any>(`/reviewer/cases/${id}/decision`, { body: { action, note, outcome, verified_documents: verify } });
      setDone(`Recorded: ${action} → ${r.status}`); setVerify([]); setNote(""); load();
    } catch (e) { setErr(e); }
  };
  const ev = c.evaluation;
  const closed = c.status === "REVIEWED";
  const criteria: any[] = ev?.criteria ?? [];
  const passed = criteria.filter((x) => x.outcome === "PASS").length;
  const evidence: any[] = ev?.evidence ?? [];
  const verifiedDocs = evidence.filter((e) => (c.documents[e.doc_key] ?? "unknown") === "verified").length;
  const activeFacts = c.facts.filter((f: any) => !f.superseded_by);
  const unconfirmed = activeFacts.filter((f: any) => !f.confirmed).length;

  return (
    <div className="stack">
      <StaffBar><Link className="btn small" to="/reviewer">← Queue</Link></StaffBar>
      <PageHead title={c.scheme.name} sub={`${c.case_id} · ${c.origin} · language ${c.language}`}>
        <StatusBadge status={c.status} />{ev && <OutcomeBadge outcome={ev.outcome} lang="en" />}
      </PageHead>
      <div className="tiny muted">Consent given {c.consent.consented_at}{c.consent.scope?.length ? ` (${c.consent.scope.join(", ")})` : ""}</div>
      {c.recheck && <div className={`notice small ${c.recheck.result_changed ? "" : "info"}`}>Online re-check at handoff ({c.recheck.bundle_version}): {c.recheck.outcome_at_draft} → {c.recheck.outcome_now}{c.recheck.result_changed ? " — result changed" : " — unchanged"}{c.recheck.draft_bundle_version !== c.recheck.bundle_version && ` · draft computed under ${c.recheck.draft_bundle_version}`}</div>}

      <Stats>
        <Stat label="Criteria met" value={criteria.length ? `${passed}/${criteria.length}` : "—"} tone={criteria.length && passed === criteria.length ? "ok" : "warn"} />
        <Stat label="Documents verified" value={evidence.length ? `${verifiedDocs}/${evidence.length}` : "—"} tone={evidence.length && verifiedDocs === evidence.length ? "ok" : undefined} />
        <Stat label="Facts" value={activeFacts.length} tone={unconfirmed ? "warn" : undefined} hint={unconfirmed ? `${unconfirmed} unconfirmed` : undefined} />
        <Stat label="Draft version" value={`v${c.draft.version}`} />
      </Stats>

      <div className="review-grid">
        <div className="stack">
          <Tabs label="Case sections" value={tab} onChange={setTab} tabs={[
            { id: "facts", label: "Facts & draft", count: activeFacts.length },
            { id: "trace", label: "Rule trace", count: criteria.length },
            { id: "docs", label: "Documents", count: evidence.length },
            { id: "audit", label: "Audit trail", count: c.audit.length },
          ]} />

          {tab === "facts" && (
            <div className="stack">
              <section className="card stack">
                <h2>Profile facts (with history)</h2>
                <div className="table-wrap"><table className="list">
                  <thead><tr><th>Fact ID</th><th>Attribute</th><th>Value</th><th>Source</th><th>State</th></tr></thead>
                  <tbody>{c.facts.map((f: any) => (
                    <tr key={f.fact_id} style={f.superseded_by ? { opacity: .55, textDecoration: "line-through" } : undefined}>
                      <td className="mono tiny">{f.fact_id}</td><td>{attrLabel(f.attribute, "en")}</td><td>{showValue(f.attribute, f.value, "en")}</td>
                      <td className="tiny">{f.source}{f.raw_text && <div>“{f.raw_text}”</div>}</td>
                      <td className="tiny">{f.superseded_by ? `→ ${f.superseded_by}` : f.confirmed ? "confirmed" : <span className="chip off">unconfirmed</span>}</td>
                    </tr>))}</tbody>
                </table></div>
              </section>
              <section className="card stack">
                <h2>Draft v{c.draft.version}</h2>
                <div className="table-wrap"><table className="list"><tbody>
                  {c.draft.fields.map((f: any) => <tr key={f.key}><td>{f.label}</td><td>{showValue(f.key, f.value, "en")}</td><td><span className="chip">{f.provenance}</span></td></tr>)}
                </tbody></table></div>
              </section>
            </div>
          )}

          {tab === "trace" && (
            <section className="card stack">
              <h2>Rule trace</h2>
              {ev ? (<>
                <div className="tiny mono">{ev.rule_id} v{ev.rule_version} · bundle {ev.bundle_version}</div>
                <div className="table-wrap"><table className="trace">
                  <thead><tr><th>Criterion</th><th>Rule needs</th><th>Citizen's fact</th><th>Result</th></tr></thead>
                  <tbody>
                  {criteria.map((cr: any) => (
                    <tr key={cr.criterion_id}><td>{cr.fact}{cr.quote && <blockquote>“{cr.quote}”</blockquote>}</td><td className="mono">{cr.expected_text}</td>
                      <td>{showValue(cr.fact, cr.observed, "en")}<div className="tiny mono">{cr.fact_id}</div></td><td className={`c-${cr.outcome}`}><strong>{cr.outcome}</strong></td></tr>
                  ))}</tbody></table></div>
                {ev.manual_checks.length > 0 && <div className="notice small"><strong>Manual checks for you</strong><ul style={{ margin: ".3rem 0 0", paddingLeft: "1.1rem" }}>{ev.manual_checks.map((m: any) => <li key={m.id}>{m.text}</li>)}</ul></div>}
                <div className="small"><strong>Source:</strong> <a href={ev.source.source_url} target="_blank" rel="noreferrer" style={{ overflowWrap: "anywhere" }}>{ev.source.source_url}</a></div>
              </>) : <p className="muted">No evaluation found.</p>}
            </section>
          )}

          {tab === "docs" && (
            <section className="card stack">
              <h2>Documents</h2>
              <p className="tiny">Citizen marks are self-declarations; an upload is not verified until you verify it. Uploads are never read by AI or OCR.</p>
              {evidence.length === 0 && <p className="muted">This scheme asks for no documents.</p>}
              {evidence.map((e: any) => {
                const st = c.documents[e.doc_key] ?? "unknown";
                return (
                  <div key={e.doc_key} className={`rev-doc ${st === "verified" ? "ok" : ""}`}>
                    <label className="row small">
                      <input type="checkbox" disabled={closed || st === "verified"} checked={st === "verified" || verify.includes(e.doc_key)}
                        onChange={(x) => setVerify(x.target.checked ? [...verify, e.doc_key] : verify.filter((d) => d !== e.doc_key))} />
                      <span className="rev-doc-name">{e.label}</span> <span className="chip">citizen: {st}</span>
                    </label>
                    {c.uploads?.[e.doc_key] && <UploadReview caseId={c.case_id} sessionId={c.session_id} docKey={e.doc_key}
                      upload={c.uploads[e.doc_key]} closed={closed} onChange={load} />}
                  </div>
                );
              })}
            </section>
          )}

          {tab === "audit" && (
            <div className="stack">
              <section className="card"><h2>Audit trail ({c.audit.length} events)</h2>
                <div className="table-wrap"><table className="list"><thead><tr><th>Time</th><th>Actor</th><th>Action</th><th>Details</th></tr></thead>
                  <tbody>{c.audit.map((a: any) => <tr key={a.event_id}><td className="tiny">{a.ts}</td><td className="tiny">{a.actor_role}<div className="mono">{a.actor_id}</div></td><td className="mono tiny">{a.action}</td><td className="tiny mono">{JSON.stringify(a.details)}</td></tr>)}</tbody>
                </table></div>
              </section>
              <details className="card"><summary>Raw case JSON</summary><Json data={c} /></details>
            </div>
          )}
        </div>

        <aside className="card stack review-decision">
          <h2>Decision</h2>
          {closed ? (
            <div className="notice ok">This case is reviewed. The decision is recorded in the audit trail.</div>
          ) : (<>
            <label className="field">Note to citizen<textarea value={note} onChange={(e) => setNote(e.target.value)} /></label>
            <button className="btn" onClick={() => act("verify_documents")} disabled={!verify.length}>Mark {verify.length || ""} ticked document{verify.length === 1 ? "" : "s"} verified</button>
            <button className="btn" onClick={() => act("request_correction")}>Request correction</button>
            <label className="field">Outcome
              <select value={outcome} onChange={(e) => setOutcome(e.target.value)} aria-label="Review outcome">
                <option value="appears_eligible">potential match (not an approval)</option>
                <option value="needs_more_documents">needs more documents</option>
                <option value="not_eligible">no match</option>
              </select>
            </label>
            <button className="btn primary" onClick={() => act("record_review")}>Record review</button>
            <p className="tiny">Recording a review is not a government approval or submission.</p>
          </>)}
          {done && <div className="notice ok">{done}</div>}
          <ErrorNote error={err} />
        </aside>
      </div>
    </div>
  );
}
