import { useState } from "react";
import { Link } from "react-router-dom";
import type { SchemeResult } from "./api";
import { ValueInput } from "./components";
import { attrLabel, showValue, t, type Lang } from "./i18n";
import { humanExpected, reasonText, reasonTone, whyText } from "./why";

/** "Why this result", in plain words: the verdict, one line per condition (needs / yours / met), what is still to do, and the official
 *  source. Internal codes, ids and timestamps sit behind "Technical details". */
export function WhyPanel({ r, lang, candidate, onDraft, onAnswer }: {
  r: SchemeResult; lang: Lang; candidate: boolean; onDraft: (r: SchemeResult) => void; onAnswer: (attr: string, v: any) => void;
}) {
  const [answers, setAnswers] = useState<Record<string, any>>({});
  const toBring = r.evidence.filter((e) => !e.satisfied);
  const quotes = r.criteria.filter((c) => c.quote);
  const ICON = { PASS: "✓", FAIL: "✕", UNKNOWN: "?" } as Record<string, string>;
  const WORD = { PASS: whyText("met", lang), FAIL: whyText("notMet", lang), UNKNOWN: whyText("unknown", lang) } as Record<string, string>;

  return (
    <div className="why">
      <ul className="why-verdict">
        {/* the officer's checks have their own section below, so that reason is not said twice */}
        {r.decision_reason.filter((d) => !(d.code === "MANUAL_CHECKS_PENDING" && r.manual_checks.length > 0)).map((d, i) => (
          <li key={i} className={reasonTone(d.code)}><span aria-hidden="true">{reasonTone(d.code) === "ok" ? "✓" : "!"}</span>{reasonText(d.code, d.text, lang)}</li>
        ))}
      </ul>

      {r.criteria.length > 0 && (
        <section className="why-sec">
          <h4>{whyText("conditions", lang)}</h4>
          <ul className="why-conds">
            {r.criteria.map((c) => (
              <li key={c.criterion_id} className={`why-cond c-${c.outcome}`}>
                <span className="why-ic" aria-hidden="true">{ICON[c.outcome] ?? "?"}</span>
                <span className="why-cond-main">
                  <b>{attrLabel(c.fact, lang)}</b>
                  <span className="why-cond-sub">
                    {whyText("needs", lang)} {humanExpected(c.expected_text, c.fact, lang, showValue)}
                    {c.fact_id && <> · {whyText("yours", lang)} <strong>{showValue(c.fact, c.observed, lang)}</strong></>}
                  </span>
                  {c.note && <span className="why-cond-sub">{c.note}</span>}
                </span>
                <span className="why-cond-word">{WORD[c.outcome] ?? c.outcome}</span>
              </li>
            ))}
          </ul>
          {quotes.length > 0 && (
            <details className="why-quotes">
              <summary>{whyText("quotes", lang)}</summary>
              {quotes.map((c) => <blockquote key={c.criterion_id}><b>{attrLabel(c.fact, lang)}:</b> “{c.quote}”</blockquote>)}
            </details>
          )}
        </section>
      )}

      {r.missing_questions && r.missing_questions.length > 0 && (
        <section className="why-sec">
          <h4>{t("missingInfo", lang)}</h4>
          {r.missing_questions.map((q) => (
            <div key={q.attribute} className="row why-ask">
              <span className="small" style={{ flex: "1 1 220px" }}>{q.text}</span>
              <div style={{ flex: "1 1 160px" }}><ValueInput attr={q.attribute} value={answers[q.attribute] ?? null} lang={lang} onChange={(v) => setAnswers({ ...answers, [q.attribute]: v })} /></div>
              <button className="btn small" disabled={answers[q.attribute] == null} onClick={() => onAnswer(q.attribute, answers[q.attribute])}>{t("save", lang)}</button>
            </div>
          ))}
        </section>
      )}

      {r.manual_checks.length > 0 && (
        <section className="why-sec">
          <h4>{whyText("officer", lang)}</h4>
          <ul className="why-list">{r.manual_checks.map((m) => <li key={m.id}>{m.text}</li>)}</ul>
        </section>
      )}

      {toBring.length > 0 && (
        <section className="why-sec">
          <h4>{whyText("docs", lang)}</h4>
          <div className="row">
            {toBring.map((e) => <span key={e.doc_key} className="chip docchip" title={e.purpose}>{e.label}</span>)}
          </div>
          <Link className="small" to="/citizen/documents">{whyText("updateDocs", lang)}</Link>
        </section>
      )}

      <div className="why-source">
        <a href={r.source.source_url} target="_blank" rel="noreferrer">{whyText("source", lang)} ↗</a>
        {!r.source.source_verified_at && <span className="tiny muted">{whyText("sourceUnverified", lang)}</span>}
      </div>

      <details className="why-tech">
        <summary>{whyText("tech", lang)}</summary>
        <dl className="kv">
          <dt>Rule</dt><dd className="mono">{r.rule_id} v{r.rule_version}</dd>
          <dt>Source ID</dt><dd className="mono">{r.source.source_id}</dd>
          <dt>Imported</dt><dd>{r.source.imported_at}</dd>
          <dt>Rule reviewed</dt><dd>{r.source.rule_reviewed_at}</dd>
          <dt>Official source verified</dt><dd>{r.source.source_verified_at ?? "—"}</dd>
          {r.evidence_note && <><dt>Note</dt><dd>{r.evidence_note}</dd></>}
        </dl>
      </details>

      {!candidate && r.outcome !== "MISMATCH" && r.outcome !== "NEEDS_HUMAN_REVIEW" && (
        <button className="btn primary" onClick={() => onDraft(r)}>{t("prepareDraft", lang)}</button>
      )}
    </div>
  );
}
