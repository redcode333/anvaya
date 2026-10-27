import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, apiBlob, type Helper } from "./api";
import { copyText } from "./clipboard";
import { ErrorNote } from "./components";
import { ListenButton } from "./ListenControls";
import { t, type Lang } from "./i18n";
import { speak, voiceProvider } from "./speech";
import { useApp } from "./state";

export { copyText };

/** The numbered steps as spoken sentences (headings are skipped). */
export const stepsToRead = (steps: Helper["steps"]) => steps.filter((s) => !s.heading).map((s, i) => `${i + 1}. ${s.text}`);

const HF = {
  copyReady: { en: "Ready to copy", hi: "कॉपी के लिए तैयार", te: "కాపీకి సిద్ధం" },
  copyAll: { en: "Copy all", hi: "सब कॉपी करें", te: "అన్నీ కాపీ చేయండి" },
  openOfficial: { en: "Open the official page ↗", hi: "आधिकारिक पेज खोलें ↗", te: "అధికారిక పేజీని తెరవండి ↗" },
  scanOrOpen: { en: "Scan the code or open the page", hi: "कोड स्कैन करें या पेज खोलें", te: "కోడ్ స్కాన్ చేయండి లేదా పేజీ తెరవండి" },
} satisfies Record<string, Record<Lang, string>>;
const hf = (k: keyof typeof HF, lang: Lang) => HF[k][lang];

/** Form Helper: what to take to the office or portal. Values you can copy (only those that exist), what is still to bring or tell
 *  the officer, the document checklist, the application steps (numbered, read aloud), the official link with a QR code, and the PDF.
 *  Nothing is submitted anywhere; the draft's own details are edited above. */
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
  const ready = h.fields.filter((f) => f.value !== null && f.copy_text);
  const toTell = h.fields.filter((f) => f.value === null && f.bring);

  return (
    <section className="card stack helper" aria-labelledby="helper-h">
      <div className="hf-head">
        <div>
          <h2 id="helper-h">{t("formHelper", lang)}</h2>
          <p className="small muted hf-sub">{t("notSubmitted", lang)}</p>
        </div>
        <button className="btn primary" onClick={pdf}>⬇ {t("downloadPdf", lang)}</button>
      </div>

      {ready.length > 0 && (<>
        <div className="hf-title">
          <h3>{hf("copyReady", lang)}</h3>
          <button type="button" className="btn small ghost" onClick={() => copy("__all", ready.map((f) => `${f.label}: ${f.copy_text}`).join("\n"))}>
            {copied === "__all" ? `✓ ${t("copied", lang)}` : `⧉ ${hf("copyAll", lang)}`}
          </button>
        </div>
        <div className="hf-copy-grid">
          {ready.map((f) => (
            <div key={f.key} className="hf-copy">
              <div><span className="k">{f.label}</span><b>{f.value}</b></div>
              <button className="btn small" onClick={() => copy(f.key, f.copy_text!)} aria-label={`${t("copy", lang)}: ${f.label}`}>
                {copied === f.key ? "✓" : t("copy", lang)}
              </button>
            </div>
          ))}
        </div>
      </>)}

      {(toTell.length > 0 || h.office_only.length > 0) && (<>
        <h3>{h.labels.bring}</h3>
        <ul className="hf-bring">
          {toTell.map((f) => <li key={f.key}><b>{f.label}</b><span>{f.bring}</span></li>)}
          {h.office_only.map((o) => <li key={o.key}><b>{o.label}</b><span>{o.hint}</span></li>)}
        </ul>
      </>)}

      <h3>{h.labels.documents} <Link to="/citizen/documents" className="small hf-update">{t("updateDocsLink", lang)}</Link></h3>
      <ul className="small hf-docs">
        {h.documents.map((d) => <li key={d.doc_key} data-ready={d.ready}><span aria-hidden="true">{d.ready ? "✓" : ""}</span>{d.label} · {d.status_label}</li>)}
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
          {h.qr_url && <img src={h.qr_url} alt={`QR: ${h.official_link.url}`} width={112} height={112} className="qr" />}
          <div className="stack hf-link-text">
            <strong>{h.labels.official_link}</strong>
            <span className="small muted">{hf("scanOrOpen", lang)}</span>
            <a className="btn small" href={h.official_link.url} target="_blank" rel="noopener noreferrer">{hf("openOfficial", lang)}</a>
          </div>
        </div>
      )}

      <ErrorNote error={err} />
    </section>
  );
}
