import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { ErrorNote } from "../components";
import { t, type Lang } from "../i18n";
import { useApp } from "../state";
import { fileProblem, uploadDocument, viewLink } from "../uploads";
import { Steps } from "./Passport";

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
  return (
    <div>
      <Steps active="/citizen/documents" />
      <div className="card stack">
        <div className="row spread"><h1>{t("documents", lang)}</h1><Link className="btn" to="/citizen/schemes">← {t("passport", lang)}</Link></div>
        <p className="notice small">{t("docNote", lang)}</p>
        <ErrorNote error={err} />
        {docs?.length === 0 && <p className="muted">Check schemes first — documents are listed for candidate schemes.</p>}
        {docs?.map((d) => (
          <div key={d.doc_key} className="card flat">
            <div className="row spread" style={{ alignItems: "flex-start" }}>
              <div style={{ minWidth: 0, flex: "1 1 260px" }}>
                <h3>📄 {d.label}</h3>
                <p className="small muted">{d.purpose}</p>
                <p className="tiny">{t("neededFor", lang)}: {d.needed_for.map((n) => n.scheme_name).join(" · ")}</p>
              </div>
              {!d.upload && (
                <div className="seg" role="group" aria-label={d.label}>
                  {STATUSES.map((s) => (
                    <button key={s.s} aria-pressed={d.status === s.s} onClick={() => mark(d.doc_key, s.s)}>{s.l[lang]}</button>
                  ))}
                </div>
              )}
            </div>
            {d.status === "verified" && !d.upload && <span className="chip on">✓ {d.status_label}</span>}
            {d.status === "reupload_requested" && <span className="chip off">{d.status_label}</span>}
            <UploadBox doc={d} policy={policy} onDone={load} />
          </div>
        ))}
        {docs && docs.length > 0 && <Link className="btn primary" to="/citizen/schemes">{t("checkSchemes", lang)} ↻</Link>}
      </div>
    </div>
  );
}
