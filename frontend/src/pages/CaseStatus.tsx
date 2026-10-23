import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import { ErrorNote, StatusBadge } from "../components";
import { t } from "../i18n";
import { speak, voiceProvider } from "../speech";
import { useApp } from "../state";

export default function CaseStatus() {
  const { code: routeCode } = useParams();
  const { lang } = useApp();
  const nav = useNavigate();
  const [code, setCode] = useState(routeCode ?? "");
  const [res, setRes] = useState<any>(null);
  const [err, setErr] = useState<unknown>(null);

  const lookup = async (c: string) => {
    setErr(null); setRes(null);
    try { setRes(await api("/cases/status", { body: { code: c } })); } catch (e) { setErr(e); }
  };
  useEffect(() => { if (routeCode) lookup(routeCode); }, [routeCode]);

  return (
    <div className="card stack" style={{ maxWidth: 620 }}>
      <h1>{t("checkStatus", lang)}</h1>
      <form className="row" onSubmit={(e) => { e.preventDefault(); nav(`/case/${encodeURIComponent(code.trim())}`); }}>
        <input type="text" value={code} onChange={(e) => setCode(e.target.value)} placeholder="ANV-XXXX-XXXX" aria-label={t("yourCode", lang)} style={{ flex: 1 }} />
        <button className="btn primary" type="submit">{t("checkStatus", lang)}</button>
      </form>
      <ErrorNote error={err} />
      {res && (
        <div className="stack">
          <div className="row"><StatusBadge status={res.status} /><strong>{res.status_label}</strong></div>
          <p>{res.scheme_name}</p>
          {res.review_outcome && <p className="small"><strong>{res.review_outcome_label ?? res.review_outcome.replace(/_/g, " ")}</strong></p>}
          {res.correction_note && <div className="notice">Reviewer note: {res.correction_note}</div>}
          <p className="tiny">Updated {res.updated_at}</p>
          <button className="btn" onClick={async () => speak(await voiceProvider(), null, res.spoken_summary, res.language)}>🔊 {t("listen", lang)}</button>
          <p className="notice small">{res.notice}</p>
        </div>
      )}
      <p className="tiny">The code shows status only. Personal details are never shown from a code alone; lookups are rate-limited.</p>
    </div>
  );
}
