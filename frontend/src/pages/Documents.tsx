import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { ErrorNote } from "../components";
import { t, type Lang } from "../i18n";
import { useApp } from "../state";
import { fileProblem, uploadDocument, viewLink } from "../uploads";
import { Steps } from "./Passport";

const READY = ["available", "uploaded", "verified"];
const MISSING = ["missing", "expired", "reupload_requested"];
const tone = (status: string) => (READY.includes(status) ? "ok" : MISSING.includes(status) ? "miss" : "check");

type Upload = { upload_id: string; status: string; content_type: string; size_bytes: number; uploaded_at: string } | null;
type Doc = { doc_key: string; label: string; purpose: string; status: string; status_label: string; upload?: Upload; needed_for: { scheme_id: string; scheme_name: string }[] };
type Policy = { allowed: boolean; reason: string | null };
const STATUSES: { s: string; l: Record<Lang, string> }[] = [
  { s: "available", l: { en: "I have it", hi: "मेरे पास है", te: "నా దగ్గర ఉంది" } },
  { s: "missing", l: { en: "Missing", hi: "नहीं है", te: "లేదు" } },
  { s: "expired", l: { en: "Expired", hi: "समाप्त", te: "గడువు ముగిసింది" } },
  { s: "unknown", l: { en: "Not sure", hi: "पता नहीं", te: "తెలియదు" } },
];

function UploadBox({ doc, policy, onDone }: { doc: Doc; policy: Policy | null; onDone: () => void }) {
  const { lang, sessionId, mode } = useApp();
  const [consent, setConsent] = useState(false);
  const [pct, setPct] = useState<number | null>(null);
  const [err, setErr] = useState<unknown>(null);
  const input = useRef<HTMLInputElement>(null);
  if (!policy) return null;
  if (!policy.allowed)
    return <p className="tiny muted">{t(policy.reason === "CASE_CLOSED" ? "uploadCaseClosed" : "uploadNeedsCase", lang)}</p>;

  const pick = async (file: File | undefined) => {
    setErr(null);
    if (!file) return;
    const problem = fileProblem(file);
    if (problem) { setErr({ code: "FILE", message: t(problem === "type" ? "fileTypeBad" : "fileTooLarge", lang) }); return; }
    try { await uploadDocument(sessionId!, doc.doc_key, file, setPct); onDone(); }
    catch (e) { setErr(e); }
    finally { setPct(null); if (input.current) input.current.value = ""; }  // keep no copy in the page
  };
  const view = async () => {
    try { window.open((await viewLink(sessionId!, doc.doc_key)).view_url, "_blank", "noopener,noreferrer"); } catch (e) { setErr(e); }
  };
  return (
    <div className="stack small" style={{ marginTop: ".5rem" }}>
      {doc.upload && (
        <div className="row">
          <span className={`chip ${doc.upload.status === "verified" ? "on" : ""}`}>
            {doc.upload.status === "verified" ? `✓ ${doc.status_label}` : `📎 ${t("notVerifiedYet", lang)}`}
          </span>
          {mode !== "kiosk" && <button className="btn small" onClick={view}>{t("viewDoc", lang)}</button>}
        </div>
      )}
      <div className={doc.doc_key === "aadhaar" ? "notice" : "tiny"}>🔒 {t("maskedAadhaar", lang)}</div>
      <label className="row" style={{ alignItems: "flex-start" }}>
        <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
        <span className="tiny">{t("uploadConsent", lang)}</span>
      </label>
      <label className={`btn small ${!consent || pct !== null ? "disabled" : ""}`} aria-disabled={!consent || pct !== null}>
        ⬆ {t("uploadDoc", lang)}
        <input ref={input} type="file" hidden disabled={!consent || pct !== null} accept="image/jpeg,image/png,application/pdf"
          onChange={(e) => pick(e.target.files?.[0])} />
      </label>
      <span className="tiny">{t("uploadTypes", lang)}</span>
      {pct !== null && <div role="status"><progress max={100} value={pct} style={{ width: "100%" }} /> {t("uploading", lang)} {pct}%</div>}
      <ErrorNote error={err} />
    </div>
  );
}

export default function Documents() {
  const { lang, sessionId } = useApp();
  const [docs, setDocs] = useState<Doc[] | null>(null);
  const [policy, setPolicy] = useState<Policy | null>(null);
  const [err, setErr] = useState<unknown>(null);
  const load = () => sessionId && api<{ documents: Doc[]; upload: Policy }>(`/sessions/${sessionId}/documents`)
    .then((r) => { setDocs(r.documents); setPolicy(r.upload); }).catch(setErr);
  useEffect(() => { load(); }, [sessionId, lang]); // eslint-disable-line react-hooks/exhaustive-deps
  const mark = async (doc: string, status: string) => {
    try { setDocs((await api<{ documents: Doc[] }>(`/sessions/${sessionId}/documents/${doc}`, { method: "PUT", body: { status } })).documents); }
    catch (e) { setErr(e); }
  };
  if (!sessionId) return <div className="card">No active session.</div>;
  const total = docs?.length ?? 0;
  const ready = docs?.filter((d) => READY.includes(d.status)).length ?? 0;
  const missing = docs?.filter((d) => MISSING.includes(d.status)).length ?? 0;
  const check = total - ready - missing;
  return (
    <div>
      <Steps active="/citizen/documents" />
      <div className="docs-hero card stack">
        <div className="row spread"><h1>{t("documents", lang)}</h1><Link className="btn" to="/citizen/schemes">← {t("passport", lang)}</Link></div>
        <p className="notice small">{t("docNote", lang)}</p>
        <ErrorNote error={err} />
        {total > 0 && (
          <div className="docs-progress">
            <div className="row spread">
              <strong>{t("docsReadyOf", lang).replace("{a}", String(ready)).replace("{b}", String(total))}</strong>
              <span className="tiny">{t("docsTapHint", lang)}</span>
            </div>
            <div className="docs-bar" role="progressbar" aria-valuemin={0} aria-valuemax={total} aria-valuenow={ready}>
              <i className="ok" style={{ width: `${(ready / total) * 100}%` }} /><i className="check" style={{ width: `${(check / total) * 100}%` }} /><i className="miss" style={{ width: `${(missing / total) * 100}%` }} />
            </div>
            <div className="docs-legend">
              <span className="ok">● {t("docsReady", lang)} {ready}</span><span className="check">● {t("docsCheck", lang)} {check}</span><span className="miss">● {t("docsMissing", lang)} {missing}</span>
            </div>
          </div>
        )}
      </div>
      {docs?.length === 0 && (
        <div className="card stack" style={{ marginTop: "1rem" }}>
          <p className="muted">{t("docsEmpty", lang)}</p>
          <Link className="btn primary" to="/citizen/schemes" style={{ justifySelf: "start" }}>{t("passport", lang)} →</Link>
        </div>
      )}
      <div className="docs-list">
        {docs?.map((d) => {
          const names = d.needed_for.map((n) => n.scheme_name);
          return (
            <article key={d.doc_key} className={`doc t-${tone(d.status)}`}>
              <div className="doc-top">
                <span className="doc-ic" aria-hidden="true">📄</span>
                <div className="doc-main">
                  <h3>{d.label}</h3>
                  <p className="small muted">{d.purpose}</p>
                  <div className="doc-for" aria-label={t("neededFor", lang)}>
                    <span className="tiny">{t("neededFor", lang)}:</span>
                    {names.slice(0, 3).map((n) => <span key={n} className="chip">{n}</span>)}
                    {names.length > 3 && <span className="chip">+{names.length - 3} {t("neededMore", lang)}</span>}
                  </div>
                </div>
              </div>
              {!d.upload && (
                <div className="seg doc-seg" role="group" aria-label={d.label}>
                  {STATUSES.map((s) => (
                    <button key={s.s} data-s={s.s} aria-pressed={d.status === s.s} onClick={() => mark(d.doc_key, s.s)}>{s.l[lang]}</button>
                  ))}
                </div>
              )}
              {d.status === "verified" && !d.upload && <span className="chip on">✓ {d.status_label}</span>}
              {d.status === "reupload_requested" && <span className="chip off">{d.status_label}</span>}
              <details className="doc-upload" open={!!d.upload}>
                <summary>⬆ {t("uploadDoc", lang)}</summary>
                <UploadBox doc={d} policy={policy} onDone={load} />
              </details>
            </article>
          );
        })}
      </div>
      {docs && docs.length > 0 && <Link className="btn primary docs-cta" to="/citizen/schemes">{t("checkSchemes", lang)} ↻</Link>}
    </div>
  );
}
