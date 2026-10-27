import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ApiError, api } from "../api";
import { codeKind, formatCaseCode } from "../caseCode";
import { StatusBadge } from "../components";
import { t, type Lang } from "../i18n";
import { ListenButton } from "../ListenControls";
import { speak, stopSpeaking, voiceProvider } from "../speech";
import { useApp } from "../state";

/** Where a case is, as three steps: sent → with a reviewer → the reviewer's answer. */
function Progress({ status, lang }: { status: string; lang: Lang }) {
  const at = status === "REVIEWED" || status === "CORRECTION_REQUESTED" ? 3 : status === "PENDING_REVIEW" || status === "SYNCED" ? 2 : 1;
  const steps = [t("stepSent", lang), t("stepReview", lang), t("stepDecision", lang)];
  return (
    <ol className="case-steps" aria-label={steps.join(" → ")}>
      {steps.map((label, i) => {
        const n = i + 1;
        const state = n < at || (n === at && status === "REVIEWED") ? "done" : n === at ? (status === "CORRECTION_REQUESTED" ? "warn" : "now") : "todo";
        return (
          <li key={label} data-state={state} aria-current={state === "now" || state === "warn" ? "step" : undefined}>
            <span className="case-dot" aria-hidden="true">{state === "done" ? "✓" : state === "warn" ? "!" : n}</span><span>{label}</span>
          </li>
        );
      })}
    </ol>
  );
}

export default function CaseStatus() {
  const { code: routeCode } = useParams();
  const { lang } = useApp();
  const nav = useNavigate();
  const [code, setCode] = useState(routeCode ? formatCaseCode(routeCode) : "");
  const [res, setRes] = useState<any>(null);
  const [err, setErr] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [audioNote, setAudioNote] = useState(false);
  const typed = useRef(false);  // a lookup the citizen asked for (a tap) may start reading aloud; a page load may not
  const kind = codeKind(code);

  const read = async (summary: string) => {
    setAudioNote(false);
    const used = await speak(await voiceProvider(), null, summary, lang);
    setAudioNote(used === "unavailable");
  };

  const lookup = async (c: string, autoRead: boolean) => {
    stopSpeaking();
    setErr(null); setRes(null); setAudioNote(false); setBusy(true);
    try {
      const r = await api<any>("/cases/status", { body: { code: c, language: lang } });
      setRes(r);
      if (autoRead && r.spoken_summary) read(r.spoken_summary);  // text is already on screen; audio follows
    } catch (e) { setErr(e); }
    setBusy(false);
  };
  // New code, or the language switched: ask again so the text (and what is read aloud) matches the site language.
  useEffect(() => { if (routeCode) { lookup(routeCode, typed.current); typed.current = false; } }, [routeCode, lang]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => () => stopSpeaking(), []);

  const passportMistake = kind === "passport" || (err as ApiError | null)?.code === "PASSPORT_CODE_NOT_CASE_CODE";
  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!code || kind === "passport") return;
    typed.current = true;
    if (code === routeCode) { typed.current = false; lookup(code, true); } else nav(`/case/${encodeURIComponent(code)}`);
  };

  return (
    <div className="case-page">
      <section className="case-card">
        <span className="case-icon" aria-hidden="true">
          <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><circle cx="11" cy="11" r="6.5" /><path d="M20 20l-4.2-4.2M8.5 11l1.8 1.8 3.2-3.4" /></svg>
        </span>
        <h1>{t("checkStatus", lang)}</h1>
        <p className="muted">{t("caseSub", lang)}</p>
        <form className="case-form" onSubmit={submit}>
          <input type="text" className="mono" value={code} placeholder="ANV-XXXX-XXXX" aria-label={t("yourCode", lang)} autoComplete="off" autoCapitalize="characters"
            spellCheck={false} aria-invalid={passportMistake} onChange={(e) => setCode(formatCaseCode(e.target.value))} />
          <button className="btn primary" type="submit" disabled={busy || !code || kind === "passport"}>{busy ? "…" : t("checkStatus", lang)}</button>
        </form>

        {passportMistake ? (
          <div className="notice info case-mistake" role="alert">
            <strong>{t("casePassportHead", lang)}</strong>
            <span>{t("casePassportBody", lang)}</span>
            <button type="button" className="btn small" onClick={() => nav("/resume", { state: { code: formatCaseCode(code) } })}>{t("goResume", lang)}</button>
          </div>
        ) : err ? (
          // The server's message already says what to do in the site language; the error code and request id are for support, not for a citizen.
          <div className="notice error" role="alert">{(err as ApiError).message}</div>
        ) : null}

        {res && (
          <div className="case-result stack">
            <div className="row"><StatusBadge status={res.status} /><strong>{res.status_label}</strong></div>
            <Progress status={res.status} lang={lang} />
            <p className="case-scheme">{res.scheme_name}</p>
            {res.review_outcome && <p className="small"><strong>{res.review_outcome_label ?? res.review_outcome.replace(/_/g, " ")}</strong></p>}
            {res.correction_note && <div className="notice">{t("reviewerNote", lang)}: {res.correction_note}</div>}
            <p className="tiny">{t("updatedAt", lang)} {res.updated_at}</p>
            <div className="row">
              <ListenButton label={t("listen", lang)} onPlay={() => read(res.spoken_summary)} />
              <button type="button" className="btn ghost" onClick={() => { setCode(""); setRes(null); setErr(null); nav("/case"); }}>{t("checkAnother", lang)}</button>
            </div>
            {audioNote && <p className="tiny muted" role="status">🔇 {t("audioUnavailable", lang)}</p>}
            <p className="notice small">{res.notice}</p>
          </div>
        )}
        <p className="tiny">{t("codeHelp", lang)}</p>
      </section>

      <aside className="case-which" aria-label={t("caseWhich", lang)}>
        <h2>{t("caseWhich", lang)}</h2>
        <div className="case-kind" data-on={kind !== "passport"}>
          <span className="case-tag">ANV-XXXX-XXXX</span><b>{t("caseCodeT", lang)}</b><span>{t("caseCodeD", lang)}</span>
        </div>
        <div className="case-kind" data-on={kind === "passport"}>
          <span className="case-tag alt">PSP-XXXX-XXXX</span><b>{t("passCodeT", lang)}</b><span>{t("passCodeD", lang)}</span>
        </div>
      </aside>
    </div>
  );
}
