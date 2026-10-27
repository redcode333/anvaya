import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, newKey, type Draft } from "../api";
import { ErrorNote, OutcomeBadge, StatusBadge, ValueInput } from "../components";
import { FormHelper } from "../FormHelper";
import { CopyButton } from "../ListenControls";
import { OUTCOME_LABEL, showValue, t, type Lang } from "../i18n";
import { sourceLabel, statusLabel } from "../statusLabels";
import { useApp } from "../state";
import { VoiceGuide, type GuideResult, type GuideStep } from "../VoiceGuide";

const PROV: Record<string, string> = { confirmed: "on", citizen_entered: "on", inferred: "", unconfirmed: "off", missing: "off" };
const EDITABLE = ["applicant_name", "district"];

const DT = {
  fill: { en: "Fill by speaking", hi: "बोलकर भरें", te: "మాట్లాడి నింపండి" },
  fillTitle: { en: "Fill this form by speaking", hi: "यह फ़ॉर्म बोलकर भरें", te: "ఈ ఫారంను మాట్లాడి నింపండి" },
  fillHint: { en: "I'll ask for what is still missing, one question at a time. You can speak or type.", hi: "जो जानकारी बाकी है, वह मैं एक-एक करके पूछूँगा। आप बोल या लिख सकते हैं।", te: "ఇంకా మిగిలిన వివరాలను ఒక్కొక్కటిగా అడుగుతాను. మీరు మాట్లాడవచ్చు లేదా టైప్ చేయవచ్చు." },
  allFilled: { en: "All your answers are in the form. Check them, then save.", hi: "आपके सभी जवाब फ़ॉर्म में आ गए हैं। उन्हें जाँचिए, फिर सहेजिए।", te: "మీ సమాధానాలన్నీ ఫారంలో ఉన్నాయి. వాటిని చూసి, సేవ్ చేయండి." },
  saveNow: { en: "Save these details", hi: "ये जानकारी सहेजें", te: "ఈ వివరాలను సేవ్ చేయండి" },
  nothingToFill: { en: "Nothing is left to fill.", hi: "भरने के लिए कुछ बाकी नहीं है।", te: "నింపడానికి ఏమీ మిగలలేదు." },
  correction: { en: "The reviewer asked for a correction. Update the draft, then send it again.", hi: "समीक्षक ने सुधार माँगा है। ड्राफ़्ट बदलिए, फिर दोबारा भेजिए।", te: "సమీక్షకుడు సవరణ కోరారు. డ్రాఫ్ట్‌ను మార్చి, మళ్ళీ పంపండి." },
  withReviewer: { en: "This draft is with the reviewer. Use your case code to follow it.", hi: "यह ड्राफ़्ट समीक्षक के पास है। इसे देखने के लिए अपना केस कोड इस्तेमाल कीजिए।", te: "ఈ డ్రాఫ్ట్ సమీక్షకుని వద్ద ఉంది. దీన్ని అనుసరించడానికి మీ కేసు కోడ్ వాడండి." },
  expires: { en: "Expires {d}.", hi: "{d} तक मान्य।", te: "{d} వరకు చెల్లుతుంది." },
  recheck: { en: "Re-checked under the current rules: the result changed from {a} to {b}.", hi: "मौजूदा नियमों से दोबारा जाँचा: नतीजा {a} से {b} हो गया।", te: "ప్రస్తుత నియమాలతో మళ్ళీ చూశాం: ఫలితం {a} నుండి {b}కి మారింది." },
  retry: { en: "This was already sent: the same case is shown, nothing was duplicated.", hi: "यह पहले ही भेजा जा चुका है: वही केस दिख रहा है, कुछ दोहराया नहीं गया।", te: "ఇది ఇప్పటికే పంపబడింది: అదే కేసు చూపుతున్నాం, ఏదీ రెండుసార్లు కాలేదు." },
  prepared: { en: "Prepared {d}", hi: "तैयार: {d}", te: "తయారు: {d}" },
  details: { en: "Draft details", hi: "ड्राफ़्ट का विवरण", te: "డ్రాఫ్ట్ వివరాలు" },
  screening: { en: "Screening result", hi: "जाँच का नतीजा", te: "పరిశీలన ఫలితం" },
  notice: { en: "This is a draft for review. It has not been submitted to any government portal.", hi: "यह समीक्षा के लिए ड्राफ़्ट है। इसे किसी सरकारी पोर्टल पर जमा नहीं किया गया है।", te: "ఇది సమీక్ష కోసం డ్రాఫ్ట్. దీన్ని ఏ ప్రభుత్వ పోర్టల్‌లోనూ సమర్పించలేదు." },
} satisfies Record<string, Record<Lang, string>>;
const dt = (k: keyof typeof DT, lang: Lang) => DT[k][lang];

export default function DraftPage() {
  const { id } = useParams();
  const { lang, sessionId } = useApp();
  const [d, setD] = useState<Draft | null>(null);
  const [edits, setEdits] = useState<Record<string, any>>({});
  const [consent, setConsent] = useState(false);
  const [handoff, setHandoff] = useState<any>(null);
  const [err, setErr] = useState<unknown>(null);
  const [guide, setGuide] = useState<GuideStep[] | null>(null);

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

  // Fill by speaking: the plan is the open fields with a question each; an answer is parsed on the server and only placed in the form here.
  const startGuide = async () => {
    setErr(null);
    try {
      const p = await api<{ steps: GuideStep[] }>(`/drafts/${d!.draft_id}/voice-fill/plan?language=${lang}`, { sessionId: sessionId! });
      if (p.steps.length) setGuide(p.steps); else setErr({ code: "NOTHING_TO_FILL", message: dt("nothingToFill", lang) });
    } catch (e) { setErr(e); }
  };
  const answer = async (step: GuideStep, utterance: string): Promise<GuideResult> => {
    const r = await api<{ fields: Record<string, any>; understood: boolean; message: string | null }>(`/drafts/${d!.draft_id}/voice-fill`,
      { body: { utterance, asked: step.key, language: lang }, sessionId: sessionId! });
    if (!r.understood) return { ok: false, message: r.message ?? "" };
    return { ok: true, message: r.message ?? "", apply: () => setEdits((e) => ({ ...e, ...r.fields })) };
  };

  if (!d) return <><ErrorNote error={err} />{!err && <p>…</p>}</>;
  const locked = !!d.case && ["PENDING_REVIEW", "REVIEWED"].includes(d.case.status);
  const tone = (p: string) => (p === "missing" || p === "unconfirmed" ? "is-missing" : p === "inferred" ? "is-inferred" : "is-ok");
  const open = d.fields.filter((f) => f.provenance === "missing" || (EDITABLE.includes(f.key) && (f.value === null || f.value === ""))).length;
  const when = new Date(d.updated_at).toLocaleDateString({ en: "en-IN", hi: "hi-IN", te: "te-IN" }[lang], { day: "numeric", month: "short", year: "numeric" });
  const outcomeLabel = (o: string) => OUTCOME_LABEL[o]?.[lang] ?? o;

  return (
    <div className="draft-page">
      <Link className="btn ghost small draft-back" to="/citizen/schemes">← {t("passport", lang)}</Link>
      <header className="draft-hero">
        <span className="draft-eyebrow">{t("draftFor", lang)}</span>
        <div className="row spread">
          <h1>{d.scheme_name}</h1>
          <StatusBadge status={d.case?.status ?? d.status} />
        </div>
        <p className="notice small">{dt("notice", lang)}</p>
        <div className="draft-meta">
          <span className="tiny muted">{dt("screening", lang)}</span><OutcomeBadge outcome={d.eligibility_snapshot.outcome} lang={lang} />
          <span className="tiny muted">· {dt("prepared", lang).replace("{d}", when)}</span>
        </div>
        <details className="draft-tech">
          <summary>{dt("details", lang)}</summary>
          <div className="draft-meta">
            <span className="chip mono">{d.draft_id}</span><span className="chip">v{d.version}</span><span className="chip">{d.origin}</span>
            <span className="chip mono">{d.eligibility_snapshot.rule_id} v{d.eligibility_snapshot.rule_version}</span>
          </div>
        </details>
      </header>

      <div className="draft-grid">
        <div className="stack">
          {guide && sessionId && (
            <VoiceGuide lang={lang} sessionId={sessionId} title={dt("fillTitle", lang)} steps={guide} confirm answer={answer} onClose={() => setGuide(null)}
              done={(close) => (
                <div className="stack">
                  <p>{dt("allFilled", lang)}</p>
                  <div className="row">
                    {Object.keys(edits).length > 0 && <button className="btn primary" onClick={async () => { await save(); close(); }}>{dt("saveNow", lang)}</button>}
                    <button className="btn" onClick={close}>{lang === "en" ? "Close" : lang === "hi" ? "बंद करें" : "మూసివేయండి"}</button>
                  </div>
                </div>
              )} />
          )}
          <section className="card stack">
            <div className="row spread">
              <h2>{t("fieldCol", lang)}</h2>
              {!locked && !guide && open > 0 && <button className="btn small" onClick={startGuide} title={dt("fillHint", lang)}>🎙 {dt("fill", lang)}</button>}
            </div>
            {!locked && !guide && open > 0 && <p className="tiny muted">{dt("fillHint", lang)}</p>}
            <div className="draft-fields">
              {d.fields.map((f) => (
                <div key={f.key} className={`draft-row ${tone(f.provenance)}`}>
                  <div className="dr-k">{f.label}</div>
                  <div className="dr-v">{!locked && (EDITABLE.includes(f.key) || f.provenance === "missing")
                    ? <ValueInput attr={f.key} value={edits[f.key] ?? f.value} lang={lang} onChange={(v) => setEdits({ ...edits, [f.key]: v })} />
                    : showValue(f.key, f.value, lang)}</div>
                  <span className={`chip ${PROV[f.provenance] ?? ""}`}>{sourceLabel(f.provenance, lang)}</span>
                </div>
              ))}
            </div>
            {Object.keys(edits).length > 0 && <button className="btn primary" onClick={save}>{dt("saveNow", lang)}</button>}
            <ErrorNote error={err} />
          </section>
        </div>

        <aside className="card stack draft-send">
          <h2>{t("sendReview", lang)}</h2>
          {d.case?.status === "CORRECTION_REQUESTED" && <div className="notice">{dt("correction", lang)}</div>}
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
              <p className="small muted">{t("codeNote", lang)} {dt("expires", lang).replace("{d}", new Date(handoff.code_expires_at).toLocaleString())}</p>
              {handoff.recheck?.result_changed && (
                <div className="notice">⚠ {dt("recheck", lang).replace("{a}", outcomeLabel(handoff.recheck.outcome_at_draft)).replace("{b}", outcomeLabel(handoff.recheck.outcome_now))}</div>
              )}
              {handoff.idempotent_replay && <p className="tiny">{dt("retry", lang)}</p>}
            </div>
          )}
          {locked && !handoff && <p className="small">{dt("withReviewer", lang)} <span className="chip">{statusLabel(d.case?.status, lang)}</span></p>}
        </aside>
      </div>
      <FormHelper draftId={d.draft_id} caseCode={handoff?.code ?? null} />
    </div>
  );
}
