import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { ErrorNote } from "../components";
import { t, type Lang } from "../i18n";
import { useApp } from "../state";
import { Steps } from "./Passport";

type Doc = { doc_key: string; label: string; purpose: string; status: string; status_label: string; needed_for: { scheme_id: string; scheme_name: string }[] };
const STATUSES: { s: string; l: Record<Lang, string> }[] = [
  { s: "available", l: { en: "I have it", hi: "मेरे पास है", te: "నా దగ్గర ఉంది" } },
  { s: "missing", l: { en: "Missing", hi: "नहीं है", te: "లేదు" } },
  { s: "expired", l: { en: "Expired", hi: "समाप्त", te: "గడువు ముగిసింది" } },
  { s: "unknown", l: { en: "Not sure", hi: "पता नहीं", te: "తెలియదు" } },
];

export default function Documents() {
  const { lang, sessionId } = useApp();
  const [docs, setDocs] = useState<Doc[] | null>(null);
  const [err, setErr] = useState<unknown>(null);
  const load = () => sessionId && api<{ documents: Doc[] }>(`/sessions/${sessionId}/documents`).then((r) => setDocs(r.documents)).catch(setErr);
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
              <div className="seg" role="group" aria-label={d.label}>
                {STATUSES.map((s) => (
                  <button key={s.s} aria-pressed={d.status === s.s} onClick={() => mark(d.doc_key, s.s)}>{s.l[lang]}</button>
                ))}
              </div>
            </div>
            {d.status === "verified" && <span className="chip on">✓ {d.status_label}</span>}
          </div>
        ))}
        {docs && docs.length > 0 && <Link className="btn primary" to="/citizen/schemes">{t("checkSchemes", lang)} ↻</Link>}
      </div>
    </div>
  );
}
