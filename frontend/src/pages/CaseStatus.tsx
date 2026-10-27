import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import { ErrorNote, StatusBadge } from "../components";
import { t } from "../i18n";
import { speak, stopSpeaking, voiceProvider } from "../speech";
import { useApp } from "../state";

export default function CaseStatus() {
  const { code: routeCode } = useParams();
  const { lang } = useApp();
  const nav = useNavigate();
  const [code, setCode] = useState(routeCode ?? "");
  const [res, setRes] = useState<any>(null);
  const [err, setErr] = useState<unknown>(null);
  const [speaking, setSpeaking] = useState(false);
  const [audioNote, setAudioNote] = useState(false);
  const typed = useRef(false);  // a lookup the citizen asked for (a tap) may start reading aloud; a page load may not

  const read = async (summary: string) => {
    setAudioNote(false); setSpeaking(true);
    const used = await speak(await voiceProvider(), null, summary, lang);
    setSpeaking(false);
    setAudioNote(used === "unavailable");
  };
  const stop = () => { stopSpeaking(); setSpeaking(false); };

  const lookup = async (c: string, autoRead: boolean) => {
    stopSpeaking(); setSpeaking(false);
    setErr(null); setRes(null); setAudioNote(false);
    try {
      const r = await api<any>("/cases/status", { body: { code: c, language: lang } });
      setRes(r);
      if (autoRead && r.spoken_summary) read(r.spoken_summary);  // text is already on screen; audio follows
    } catch (e) { setErr(e); }
  };
  // New code, or the language switched: ask again so the text (and what is read aloud) matches the site language.
  useEffect(() => { if (routeCode) { lookup(routeCode, typed.current); typed.current = false; } }, [routeCode, lang]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => () => stopSpeaking(), []);

  return (
    <div className="card stack" style={{ maxWidth: 620 }}>
      <h1>{t("checkStatus", lang)}</h1>
      <form className="row" onSubmit={(e) => {
        e.preventDefault();
        const c = code.trim();
        if (!c) return;
        typed.current = true;
        if (c === routeCode) { typed.current = false; lookup(c, true); } else nav(`/case/${encodeURIComponent(c)}`);
      }}>
        <input type="text" value={code} onChange={(e) => setCode(e.target.value)} placeholder="ANV-XXXX-XXXX" aria-label={t("yourCode", lang)} style={{ flex: 1 }} />
        <button className="btn primary" type="submit">{t("checkStatus", lang)}</button>
      </form>
      <ErrorNote error={err} />
      {res && (
        <div className="stack">
          <div className="row"><StatusBadge status={res.status} /><strong>{res.status_label}</strong></div>
          <p>{res.scheme_name}</p>
          {res.review_outcome && <p className="small"><strong>{res.review_outcome_label ?? res.review_outcome.replace(/_/g, " ")}</strong></p>}
          {res.correction_note && <div className="notice">{t("reviewerNote", lang)}: {res.correction_note}</div>}
          <p className="tiny">{t("updatedAt", lang)} {res.updated_at}</p>
          <div className="row">
            <button className="btn" onClick={() => (speaking ? stop() : read(res.spoken_summary))} aria-pressed={speaking}>
              {speaking ? `⏹ ${t("stopListening", lang)}` : `🔊 ${t("listen", lang)}`}</button>
          </div>
          {audioNote && <p className="tiny muted" role="status">🔇 {t("audioUnavailable", lang)}</p>}
          <p className="notice small">{res.notice}</p>
        </div>
      )}
      <p className="tiny">{t("codeHelp", lang)}</p>
    </div>
  );
}
