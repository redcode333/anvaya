import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, apiBlob, type Helper } from "./api";
import { copyText } from "./clipboard";
import { ErrorNote } from "./components";
import { ListenButton } from "./ListenControls";
import { t } from "./i18n";
import { speak, voiceProvider } from "./speech";
import { useApp } from "./state";

export { copyText };

/** The numbered steps as spoken sentences (headings are skipped). */
export const stepsToRead = (steps: Helper["steps"]) => steps.filter((s) => !s.heading).map((s, i) => `${i + 1}. ${s.text}`);

/** Form Helper: copy-ready fields in form order, what to bring, the application steps (numbered, read aloud), the
 *  official link with a QR code, and the PDF. Nothing is submitted anywhere. */
export function FormHelper({ draftId, caseCode }: { draftId: string; caseCode?: string | null }) {
  const { lang, sessionId } = useApp();
  const [h, setH] = useState<Helper | null>(null);
  const [err, setErr] = useState<unknown>(null);
  const [copied, setCopied] = useState<string | null>(null);
  const [audioNote, setAudioNote] = useState(false);
  const headers = caseCode ? { "X-Case-Code": caseCode } : undefined;

  useEffect(() => {
    setErr(null);
    api<Helper>(`/drafts/${draftId}/helper?language=${lang}`, { sessionId: sessionId ?? undefined, headers }).then(setH).catch(setErr);
  }, [draftId, lang, sessionId, caseCode]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!h) return <ErrorNote error={err} />;
  const copy = async (key: string, text: string) => { if (await copyText(text)) { setCopied(key); setTimeout(() => setCopied(null), 1500); } };
  const pdf = async () => {
    setErr(null);
    try {
      const blob = await apiBlob(`/drafts/${draftId}/pdf?language=${lang}`, { sessionId: sessionId ?? undefined, headers });
      const url = URL.createObjectURL(blob);
      Object.assign(document.createElement("a"), { href: url, download: `anvaya-draft-${draftId}-${lang}.pdf` }).click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) { setErr(e); }
  };
  const readAloud = async () => {
    setAudioNote(false);
    const used = await speak(await voiceProvider(), sessionId, stepsToRead(h.steps), lang);
    setAudioNote(used === "unavailable");
  };
  const missing = h.fields.filter((f) => f.tag === "missing");

  return (
    <section className="card stack helper" aria-labelledby="helper-h">
      <div className="hf-head">
        <h2 id="helper-h">{t("formHelper", lang)}</h2>
        <button className="btn primary" onClick={pdf}>⬇ {t("downloadPdf", lang)}</button>
      </div>
      <div className="notice ok" role="status"><strong>{h.status_label}</strong> · {t("notSubmitted", lang)}</div>
      <p className="tiny">{h.watermark_local}</p>

      <div className="stack">
        {h.fields.map((f) => (
          <div key={f.key} className={`fact ${f.tag === "missing" ? "pending" : ""}`}>
            <div>
              <div className="k">{f.label} <span className={`chip ${f.tag === "missing" ? "off" : "on"}`}>{f.tag_label}</span></div>
              {f.value !== null
                ? <div className="v">{f.value}</div>
                : <div className="small" role="note"><strong>{h.labels.bring}:</strong> {f.bring}</div>}
            </div>
            {f.copy_text && <button className="btn small" onClick={() => copy(f.key, f.copy_text!)} aria-label={`${t("copy", lang)}: ${f.label}`}>
              {copied === f.key ? "✓" : t("copy", lang)}</button>}
          </div>
        ))}
      </div>
      {missing.length > 0 && <div className="notice" role="status">{missing.length} · {h.labels.bring}</div>}
      <div className="notice small">
        <strong>{h.labels.bring}</strong>
        <ul style={{ margin: ".3rem 0 0", paddingLeft: "1.1rem" }}>{h.office_only.map((o) => <li key={o.key}>{o.label}: {o.hint}</li>)}</ul>
      </div>

      <h3>{h.labels.documents} <Link to="/citizen/documents" className="small hf-update">{t("updateDocsLink", lang)}</Link></h3>
      <ul className="small hf-docs">
        {h.documents.map((d) => <li key={d.doc_key} data-ready={d.ready}><span aria-hidden="true">{d.ready ? "✓" : ""}</span>{d.label} — {d.status_label}</li>)}
      </ul>

      <h3>{h.labels.steps} {h.steps_machine_translated && <span className="chip" title={h.labels.mt}>{h.labels.mt}</span>}</h3>
      {h.steps_note && <p className="tiny">{h.steps_note}</p>}
      {h.steps.length === 0 ? <p className="small">{t("noSteps", lang)}</p> : (
        <ol className="small hf-steps">
          {h.steps.map((s, i) => s.heading
            ? <li key={i} className="hf-step-head"><strong>{s.text}</strong></li>
            : <li key={i}>{s.text}</li>)}
        </ol>
      )}
      {h.steps.length > 0 && (
        <div className="row">
          <ListenButton label={t("readAloudSteps", lang)} onPlay={readAloud} />
          {audioNote && <span className="tiny muted" role="status">🔇 {t("audioUnavailable", lang)}</span>}
        </div>
      )}

      {h.official_link && (
        <div className="hf-link">
          {h.qr_url && <img src={h.qr_url} alt={`QR: ${h.official_link.url}`} width={120} height={120} className="qr" />}
          <div className="small"><strong>{h.labels.official_link}</strong><br />
            <a href={h.official_link.url} target="_blank" rel="noopener noreferrer">{h.official_link.label}</a>
            <div className="tiny mono" style={{ wordBreak: "break-all" }}>{h.official_link.url}</div></div>
        </div>
      )}

      <ErrorNote error={err} />
    </section>
  );
}
