import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, newKey, type Draft } from "../api";
import { ErrorNote, OutcomeBadge, StatusBadge, ValueInput } from "../components";
import { showValue, t } from "../i18n";
import { useApp } from "../state";

const PROV: Record<string, string> = { confirmed: "on", citizen_entered: "on", inferred: "", unconfirmed: "off", missing: "off" };

export default function DraftPage() {
  const { id } = useParams();
  const { lang, sessionId } = useApp();
  const [d, setD] = useState<Draft | null>(null);
  const [edits, setEdits] = useState<Record<string, any>>({});
  const [consent, setConsent] = useState(false);
  const [handoff, setHandoff] = useState<any>(null);
  const [err, setErr] = useState<unknown>(null);

  const load = () => api<Draft>(`/drafts/${id}`, { sessionId: sessionId ?? undefined }).then(setD).catch(setErr);
  useEffect(() => { load(); }, [id]); // eslint-disable-line react-hooks/exhaustive-deps

  const save = async () => {
    if (!d) return;
    setErr(null);
    try {
      const nd = await api<Draft>(`/drafts/${d.draft_id}`, { method: "PATCH", body: { version: d.version, fields: edits }, sessionId: sessionId! });
      setD(nd); setEdits({});
    } catch (e: any) { setErr(e); if (e.code === "CONFLICT") load(); }
  };

  const send = async () => {
    if (!d) return;
    // Reuse the same key for retries of this handoff attempt, so a timeout + retry cannot duplicate.
    const k = `anvaya.citizen.handoffKey.${d.draft_id}.${d.version}`;
    let key = sessionStorage.getItem(k);
    if (!key) { key = newKey(); sessionStorage.setItem(k, key); }
    setErr(null);
    try {
      setHandoff(await api(`/drafts/${d.draft_id}/handoff`, { body: { consent: { share_with_reviewer: true, language: lang } }, headers: { "Idempotency-Key": key }, sessionId: sessionId! }));
      load();
    } catch (e) { setErr(e); }
  };

  if (!d) return <><ErrorNote error={err} />{!err && <p>Loading…</p>}</>;
  const locked = d.case && ["PENDING_REVIEW", "REVIEWED"].includes(d.case.status);
  const editable = ["applicant_name", "district"];

  return (
    <div className="grid two">
      <section className="card stack">
        <div className="row spread">
          <h1>{t("draft", lang)}: {d.scheme_name}</h1>
          <StatusBadge status={d.case?.status ?? d.status} />
        </div>
        <p className="notice small">{d.notice}</p>
        <div className="row tiny">
          <span className="mono">{d.draft_id} · v{d.version}</span> · origin {d.origin} · screening <OutcomeBadge outcome={d.eligibility_snapshot.outcome} lang={lang} />
          · {d.eligibility_snapshot.rule_id} v{d.eligibility_snapshot.rule_version}
        </div>
        <div className="table-wrap">
          <table className="list">
            <thead><tr><th>Field</th><th>Value</th><th>Provenance</th></tr></thead>
            <tbody>
              {d.fields.map((f) => (
                <tr key={f.key}>
                  <td>{f.label}<div className="tiny mono">{f.fact_id ?? ""}</div></td>
                  <td>{!locked && (editable.includes(f.key) || f.provenance === "missing")
                    ? <ValueInput attr={f.key} value={edits[f.key] ?? f.value} lang={lang} onChange={(v) => setEdits({ ...edits, [f.key]: v })} />
                    : showValue(f.key, f.value, lang)}</td>
                  <td><span className={`chip ${PROV[f.provenance] ?? ""}`}>{f.provenance.replace("_", " ")}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {Object.keys(edits).length > 0 && <button className="btn" onClick={save}>{t("save", lang)} (v{d.version} → v{d.version + 1})</button>}
        <div className="small"><strong>{t("documents", lang)}:</strong>{" "}
          {d.documents.map((x) => <span key={x.doc_key} className={`chip ${x.status === "available" || x.status === "verified" ? "on" : "off"}`} style={{ margin: "0 .25rem .25rem 0" }}>{x.doc_key.replace(/_/g, " ")}: {x.status}</span>)}
          <Link to="/citizen/documents" className="small"> update</Link>
        </div>
        <ErrorNote error={err} />
      </section>

      <section className="card stack">
        <h2>{t("sendReview", lang)}</h2>
        {d.case?.status === "CORRECTION_REQUESTED" && <div className="notice">The reviewer asked for a correction. Update the draft, then send again.</div>}
        {!locked && (<>
          <label className="row" style={{ alignItems: "flex-start" }}>
            <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} style={{ marginTop: ".3rem" }} />
            <span className="small">{t("consent", lang)}</span>
          </label>
          <button className="btn primary" disabled={!consent} onClick={send}>{t("sendReview", lang)}</button>
        </>)}
        {handoff && (
          <div className="stack">
            <div className="tiny">{t("yourCode", lang)}</div>
            <div className="code-big">{handoff.code}</div>
            <p className="small muted">{t("codeNote", lang)} Expires {new Date(handoff.code_expires_at).toLocaleString()}.</p>
            {handoff.recheck?.result_changed && (
              <div className="notice">⚠ Re-checked under the current rules: result changed from {handoff.recheck.outcome_at_draft} to {handoff.recheck.outcome_now}.</div>
            )}
            {handoff.idempotent_replay && <p className="tiny">Retry detected — same case returned, no duplicate created.</p>}
            <Link className="btn" to={`/case/${handoff.code}`}>{t("checkStatus", lang)} →</Link>
          </div>
        )}
        {locked && !handoff && <p className="small">This draft is with the reviewer ({d.case?.status}). Use your case code to follow its status.</p>}
      </section>
    </div>
  );
}
