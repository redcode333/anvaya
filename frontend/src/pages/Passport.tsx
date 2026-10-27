import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, newKey, type Draft, type Evaluation, type SchemeResult } from "../api";
import { SavePanel } from "../AccountUI";
import { ErrorNote, OutcomeBadge, ValueInput } from "../components";
import { ListenButton } from "../ListenControls";
import { downloadPassportPdf } from "../passportPdf";
import { attrLabel, showValue, t, type Lang } from "../i18n";
import { speak, voiceProvider } from "../speech";
import { useApp } from "../state";

export function Steps({ active }: { active: string }) {
  const { lang, mode } = useApp();
  const items = [
    [mode === "kiosk" ? "/kiosk" : "/citizen", t("profile", lang)],
    ["/citizen/schemes", t("passport", lang)],
    ["/citizen/documents", t("documents", lang)],
  ];
  return (
    <nav className="steps" aria-label="Steps" style={{ marginBottom: "1rem" }}>
      {items.map(([to, label], i) => (
        <Link key={to} to={to} className={`chip ${active === to ? "on" : ""}`}>{i + 1}. {label}</Link>
      ))}
    </nav>
  );
}

function SchemeCard({ r, lang, onDraft, onAnswer }: { r: SchemeResult; lang: Lang; onDraft: (r: SchemeResult) => void; onAnswer: (attr: string, v: any) => void }) {
  const [open, setOpen] = useState(false);
  const [answers, setAnswers] = useState<Record<string, any>>({});
  return (
    <article className="scheme">
      <div className="scheme-head">
        <div style={{ minWidth: 0 }}>
          <h3>{r.scheme_name_localized ?? r.scheme_name}</h3>
          {r.scheme_name_machine_translated && (
            <div className="tiny">{r.scheme_name} · <span className="chip" title="Translated automatically by VerbX; the official scheme name is shown first in English">{t("machineTranslated", lang)}</span></div>
          )}
          <div className="row tiny">
            <span>{r.jurisdiction.level === "Central" ? "Central" : r.jurisdiction.state}</span>·
            <span className="mono">{r.rule_id} v{r.rule_version}</span>·
            <span>{r.criteria.filter((c) => c.outcome === "PASS").length}/{r.criteria.length} criteria pass</span>
          </div>
          {r.document_gaps.length > 0 && r.outcome !== "MISMATCH" && (
            <div className="row" style={{ marginTop: ".4rem" }}>
              {r.evidence.filter((e) => r.document_gaps.includes(e.doc_key)).map((e) => (
                <span key={e.doc_key} className="chip off" title={e.purpose}>📄 {e.label}: {e.status_label}</span>
              ))}
            </div>
          )}
        </div>
        <div className="stack" style={{ textAlign: "right" }}>
          <OutcomeBadge outcome={r.outcome} lang={lang} />
          <button className="btn small" onClick={() => setOpen(!open)} aria-expanded={open}>{t("why", lang)} {open ? "▲" : "▼"}</button>
        </div>
      </div>
      {open && (
        <div className="scheme-body">
          <ul className="small" style={{ margin: 0, paddingLeft: "1.1rem" }}>
            {r.decision_reason.map((d, i) => <li key={i}><span className="mono tiny">{d.code}</span> — {d.text}</li>)}
          </ul>
          <div className="table-wrap">
            <table className="trace">
              <thead><tr><th>Criterion</th><th>Rule needs</th><th>Your fact</th><th>Result</th></tr></thead>
              <tbody>
                {r.criteria.map((c) => (
                  <tr key={c.criterion_id}>
                    <td>{attrLabel(c.fact, lang)}
                      {c.quote && <blockquote>“{c.quote}”</blockquote>}
                      {c.note && <div className="tiny">{c.note}</div>}</td>
                    <td className="mono">{c.expected_text}</td>
                    <td>{c.fact_id ? <>{showValue(c.fact, c.observed, lang)} <div className="tiny mono">{c.fact_id}</div></> : "—"}</td>
                    <td className={`c-${c.outcome}`}><strong>{c.outcome}</strong></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {r.missing_questions && r.missing_questions.length > 0 && (
            <div className="stack">
              <strong className="small">{t("missingInfo", lang)}</strong>
              {r.missing_questions.map((q) => (
                <div key={q.attribute} className="row">
                  <span className="small" style={{ flex: "1 1 220px" }}>{q.text}</span>
                  <div style={{ flex: "1 1 160px" }}><ValueInput attr={q.attribute} value={answers[q.attribute] ?? null} lang={lang} onChange={(v) => setAnswers({ ...answers, [q.attribute]: v })} /></div>
                  <button className="btn small" disabled={answers[q.attribute] == null} onClick={() => onAnswer(q.attribute, answers[q.attribute])}>{t("save", lang)}</button>
                </div>
              ))}
            </div>
          )}
          {r.manual_checks.length > 0 && (
            <div className="small"><strong>Checked by an officer:</strong>
              <ul style={{ margin: ".2rem 0 0", paddingLeft: "1.1rem" }}>{r.manual_checks.map((m) => <li key={m.id}>{m.text}</li>)}</ul></div>
          )}
          <div className="small"><strong>{t("documents", lang)}:</strong>{" "}
            {r.evidence.map((e) => <span key={e.doc_key} className={`chip ${e.satisfied ? "on" : ""}`} style={{ margin: "0 .25rem .25rem 0" }}>{e.label} · {e.status_label}</span>)}
            {r.evidence_note && <div className="tiny">{r.evidence_note}</div>}
          </div>
          <dl className="kv">
            <dt>{t("source", lang)}</dt><dd><a href={r.source.source_url} target="_blank" rel="noreferrer">{r.source.source_url}</a></dd>
            <dt>Source ID</dt><dd className="mono">{r.source.source_id}</dd>
            <dt>Imported</dt><dd>{r.source.imported_at}</dd>
            <dt>Rule reviewed</dt><dd>{r.source.rule_reviewed_at} (team review against dataset text)</dd>
            <dt>Official source verified</dt><dd>{r.source.source_verified_at ?? "Not yet verified by a data steward"}</dd>
            <dt>Input facts</dt><dd className="mono">{r.input_fact_ids.join(", ") || "—"}</dd>
          </dl>
          {r.outcome !== "MISMATCH" && r.outcome !== "NEEDS_HUMAN_REVIEW" && (
            <button className="btn primary" onClick={() => onDraft(r)}>{t("prepareDraft", lang)}</button>
          )}
        </div>
      )}
    </article>
  );
}

export default function Passport() {
  const { lang, sessionId, mode } = useApp();
  const nav = useNavigate();
  const [ev, setEv] = useState<Evaluation | null>(null);
  const [err, setErr] = useState<any>(null);
  const [voiceMsg, setVoiceMsg] = useState("");

  const run = useCallback(async () => {
    if (!sessionId) return;
    setErr(null);
    try { setEv(await api<Evaluation>(`/sessions/${sessionId}/eligibility/evaluate`, { body: {} })); } catch (e) { setErr(e); }
  }, [sessionId]);
  useEffect(() => { run(); }, [run, lang]);

  if (!sessionId) return <div className="card">No active session. <Link to={mode === "kiosk" ? "/kiosk" : "/citizen"}>Start here</Link>.</div>;

  const draft = async (r: SchemeResult) => {
    try {
      const d = await api<Draft>(`/sessions/${sessionId}/drafts`, { body: { scheme_id: r.scheme_id }, headers: { "Idempotency-Key": newKey() } });
      nav(`/citizen/draft/${d.draft_id}`);
    } catch (e) { setErr(e); }
  };
  const answer = async (attribute: string, value: any) => {
    try { await api(`/sessions/${sessionId}/profile/facts`, { body: { attribute, value } }); run(); } catch (e) { setErr(e); }
  };
  const downloadPdf = async () => { setErr(null); try { await downloadPassportPdf(sessionId, lang); } catch (e) { setErr(e); } };
  const listenSummary = async () => {
    if (!ev?.voice_summary) return;
    setVoiceMsg("");
    const used = await speak(await voiceProvider(), sessionId, ev.voice_summary_segments ?? ev.voice_summary, lang);
    if (used === "unavailable") setVoiceMsg(`🔇 ${t("audioUnavailable", lang)}`);
    else if (used !== "cancelled") setVoiceMsg(`Spoken via ${used}`);
  };

  const groups: [string, SchemeResult[]][] = ev ? [
    ["candidates", ev.results.filter((r) => ["MATCH", "PROVISIONAL"].includes(r.outcome))],
    ["info", ev.results.filter((r) => ["INSUFFICIENT_INFORMATION", "NEEDS_HUMAN_REVIEW"].includes(r.outcome))],
    ["no", ev.results.filter((r) => r.outcome === "MISMATCH")],
  ] : [];
  const headings: Record<string, Record<Lang, string>> = {
    candidates: { en: "May suit you (provisional)", hi: "आपके लिए उपयुक्त हो सकती हैं (अस्थायी)", te: "మీకు సరిపోవచ్చు (తాత్కాలికం)" },
    info: { en: "Need more information or review", hi: "और जानकारी या समीक्षा चाहिए", te: "మరింత సమాచారం లేదా సమీక్ష అవసరం" },
    no: { en: "Do not match your confirmed details", hi: "आपकी पुष्टि की गई जानकारी से मेल नहीं", te: "మీ నిర్ధారిత వివరాలతో సరిపోలలేదు" },
  };

  return (
    <div>
      <Steps active="/citizen/schemes" />
      {err?.code === "PROFILE_NEEDS_CONFIRMATION" ? (
        <div className="notice">{err.message} <Link to={mode === "kiosk" ? "/kiosk" : "/citizen"}>{t("profile", lang)} →</Link></div>
      ) : <ErrorNote error={err} />}
      {ev && (
        <div className="stack">
          <div className="card stack">
            <div className="row spread">
              <h1>{t("passport", lang)}</h1>
              <div className="row">
                <ListenButton label={t("listen", lang)} onPlay={listenSummary} />
                <button className="btn" onClick={downloadPdf}>⬇ {t("downloadPassport", lang)}</button>
                <Link className="btn" to="/citizen/documents">{t("documents", lang)} →</Link>
              </div>
            </div>
            <p className="notice small">{t("notApproval", lang)}</p>
            <p className="small">{ev.voice_summary}
              {ev.voice_summary_machine_translated && <> <span className="chip" title="Scheme names in this summary were translated automatically by VerbX">{t("machineTranslated", lang)}</span></>}</p>
            {voiceMsg && <p className="tiny">{voiceMsg}</p>}
            <div className="tiny">
              Jurisdiction: {ev.jurisdiction?.state ?? "—"} + central schemes · bundle {ev.bundle_version} · evaluation <span className="mono">{ev.eval_id}</span>
              {ev.jurisdiction?.note && ` · ${ev.jurisdiction.note}`}
            </div>
            {ev.changes_since_last && ev.changes_since_last.length > 0 && (
              <div className="notice info small">
                <strong>{t("changed", lang)}:</strong>
                <ul style={{ margin: ".25rem 0 0", paddingLeft: "1.1rem" }}>
                  {ev.changes_since_last.map((c) => <li key={c.scheme_id}>{c.scheme_name}: {c.before ?? "—"} → <strong>{c.after ?? "—"}</strong></li>)}
                </ul>
              </div>
            )}
          </div>
          {groups.map(([k, list]) => list.length > 0 && (
            <section key={k} className="stack">
              <h2>{headings[k][lang]} <span className="chip">{list.length}</span></h2>
              {list.map((r) => <SchemeCard key={r.rule_id} r={r} lang={lang} onDraft={draft} onAnswer={answer} />)}
            </section>
          ))}
          <SavePanel sessionId={sessionId} />
        </div>
      )}
    </div>
  );
}
