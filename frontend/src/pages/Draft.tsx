import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, newKey, type Draft } from "../api";
import { ErrorNote, OutcomeBadge, StatusBadge, ValueInput } from "../components";
import { FormHelper } from "../FormHelper";
import { CopyButton } from "../ListenControls";
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

  const tone = (p: string) => (p === "missing" || p === "unconfirmed" ? "is-missing" : p === "inferred" ? "is-inferred" : "is-ok");

  return (
    <div className="draft-page">
      <Link className="btn ghost small draft-back" to="/citizen/schemes">← {t("passport", lang)}</Link>
      <header className="draft-hero">
        <span className="draft-eyebrow">{t("draftFor", lang)}</span>
        <div className="row spread">
          <h1>{d.scheme_name}</h1>
          <StatusBadge status={d.case?.status ?? d.status} />
        </div>
        <p className="notice small">{d.notice}</p>
        <div className="draft-meta">
          <span className="chip mono">{d.draft_id}</span><span className="chip">v{d.version}</span><span className="chip">{d.origin}</span>
          <OutcomeBadge outcome={d.eligibility_snapshot.outcome} lang={lang} />
          <span className="chip mono">{d.eligibility_snapshot.rule_id} v{d.eligibility_snapshot.rule_version}</span>
        </div>
      </header>

      <div className="draft-grid">
        <section className="card stack">
          <h2>{t("fieldCol", lang)}</h2>
          <div className="draft-fields">
            {d.fields.map((f) => (
              <div key={f.key} className={`draft-row ${tone(f.provenance)}`}>
                <div className="dr-k">{f.label}{f.fact_id && <div className="tiny mono">{f.fact_id}</div>}</div>
                <div className="dr-v">{!locked && (editable.includes(f.key) || f.provenance === "missing")
                  ? <ValueInput attr={f.key} value={edits[f.key] ?? f.value} lang={lang} onChange={(v) => setEdits({ ...edits, [f.key]: v })} />
                  : showValue(f.key, f.value, lang)}</div>
                <span className={`chip ${PROV[f.provenance] ?? ""}`}>{f.provenance.replace("_", " ")}</span>
              </div>
            ))}
          </div>
          {Object.keys(edits).length > 0 && <button className="btn primary" onClick={save}>{t("save", lang)} (v{d.version} → v{d.version + 1})</button>}
          <div className="draft-docs">
            <strong className="small">{t("documents", lang)}</strong>
            <div className="row">
              {d.documents.map((x) => <span key={x.doc_key} className={`chip ${x.status === "available" || x.status === "verified" ? "on" : "docchip"}`}>{x.doc_key.replace(/_/g, " ")}: {x.status}</span>)}
              <Link to="/citizen/documents" className="small">update</Link>
            </div>
          </div>
          <ErrorNote error={err} />
        </section>

        <aside className="card stack draft-send">
          <h2>{t("sendReview", lang)}</h2>
          {d.case?.status === "CORRECTION_REQUESTED" && <div className="notice">The reviewer asked for a correction. Update the draft, then send again.</div>}
          {!locked && (<>
            <ol className="send-steps">
              {(["sendStep1", "sendStep2", "sendStep3"] as const).map((k, i) => <li key={k}><span aria-hidden="true">{i + 1}</span>{t(k, lang)}</li>)}
            </ol>
            <label className="row" style={{ alignItems: "flex-start" }}>
              <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} style={{ marginTop: ".3rem" }} />
              <span className="small">{t("consent", lang)}</span>
            </label>
            <button className="btn primary send-btn" disabled={!consent} onClick={send}>{t("sendReview", lang)}</button>
          </>)}
          {handoff && (
            <div className="handoff stack">
              <div className="tiny">{t("yourCode", lang)}</div>
              <div className="code-big">{handoff.code}</div>
              <div className="row">
                <CopyButton text={handoff.code} label={t("copyCode", lang)} />
                <Link className="btn" to={`/case/${handoff.code}`}>{t("checkStatus", lang)} →</Link>
              </div>
              <p className="small muted">{t("codeNote", lang)} Expires {new Date(handoff.code_expires_at).toLocaleString()}.</p>
              {handoff.recheck?.result_changed && (
                <div className="notice">⚠ Re-checked under the current rules: result changed from {handoff.recheck.outcome_at_draft} to {handoff.recheck.outcome_now}.</div>
              )}
              {handoff.idempotent_replay && <p className="tiny">Retry detected — same case returned, no duplicate created.</p>}
            </div>
          )}
          {locked && !handoff && <p className="small">This draft is with the reviewer ({d.case?.status}). Use your case code to follow its status.</p>}
        </aside>
      </div>
      <FormHelper draftId={d.draft_id} caseCode={handoff?.code ?? null} />
    </div>
  );
}
