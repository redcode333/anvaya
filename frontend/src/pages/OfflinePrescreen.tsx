import { useEffect, useState } from "react";
import { ErrorNote, OutcomeBadge, StatusBadge, ValueInput } from "../components";
import { attrLabel, t } from "../i18n";
import { evaluate, sortResults, type LocalResult } from "../offline/rulesEngine";
import { clearSynced, enqueue, getBundle, getOutbox, refreshBundle, syncOutbox } from "../offline/store";
import { useApp } from "../state";

const FIELDS = ["state", "age", "annual_income", "gender", "marital_status", "area", "occupation", "bpl",
  "receives_other_pension", "owns_cultivable_land", "has_bank_account"];

/** Shown in kiosk mode whenever connectivity is lost (real or simulated). Also embedded as the sync panel online. */
export default function OfflinePrescreen({ embedded = false }: { embedded?: boolean }) {
  const { lang, online } = useApp();
  const [bundle, setBundle] = useState(getBundle());
  const [facts, setFacts] = useState<Record<string, any>>({});
  const [results, setResults] = useState<LocalResult[] | null>(null);
  const [name, setName] = useState("");
  const [consent, setConsent] = useState(false);
  const [outbox, setOutbox] = useState(getOutbox());
  const [msg, setMsg] = useState<string>("");
  const [err, setErr] = useState<unknown>(null);
  const [ms, setMs] = useState<number | null>(null);

  useEffect(() => { if (online && !bundle) refreshBundle().then((r) => { setBundle(r.bundle); setMsg(r.message); }); }, [online]); // eslint-disable-line react-hooks/exhaustive-deps

  const run = () => {
    if (!bundle) return;
    const t0 = performance.now();
    const ef = Object.fromEntries(Object.entries(facts).filter(([, v]) => v !== null && v !== "")
      .map(([k, v]) => [k, { fact_id: `LOCAL-${k}`, value: v, confirmed: true }]));
    const st = facts.state;
    const cands = bundle.rules.filter(({ rule }) => rule.jurisdiction.level === "Central" || rule.jurisdiction.state === st);
    setResults(sortResults(cands.map(({ rule, meta }) => evaluate(rule, ef, {}, meta))));
    setMs(performance.now() - t0);
  };

  const queue = (r: LocalResult) => {
    if (!bundle) return;
    enqueue({ language: lang, scheme_id: r.scheme_id, facts: { ...facts, applicant_name: name || undefined },
      documents: {}, local_result: { outcome: r.outcome, rule_id: r.rule_id, rule_version: r.rule_version },
      consent: { share_with_reviewer: consent } }, bundle.bundle_version);
    setOutbox(getOutbox());
    setMsg(`Draft for “${r.scheme_name}” queued locally (SYNC_PENDING). It will be re-checked online before reaching a reviewer.`);
  };

  const sync = async (resend = false) => {
    setErr(null);
    try {
      const r = await syncOutbox(resend);
      setMsg(r.sent ? `Sent ${r.sent} event(s): ${r.results.map((x: any) => x.status).join(", ")}` : "Nothing to sync.");
    } catch (e) { setErr(e); }
    setOutbox(getOutbox());
  };

  const refresh = async () => { const r = await refreshBundle(); setBundle(r.bundle); setMsg(r.message); };

  return (
    <div className="stack">
      {!embedded && (
        <div className="notice">
          <strong>{t("offline", lang)} — preliminary pre-screen.</strong> Typed input only (cloud speech needs a connection).
          Results use the cached rule bundle and may be stale; nothing here is an approval or a submission.
        </div>
      )}
      <div className={embedded ? "stack" : "grid two"}>
        {!embedded && (
          <section className="card stack">
            <h2>Household details</h2>
            {!bundle && <div className="notice error">No rule bundle cached on this kiosk yet. Connect once to download it.</div>}
            <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))" }}>
              {FIELDS.map((f) => (
                <label key={f} className="field">{attrLabel(f, lang)}
                  <ValueInput attr={f} value={facts[f] ?? null} lang={lang} onChange={(v) => setFacts({ ...facts, [f]: v })} />
                </label>
              ))}
            </div>
            <button className="btn primary" onClick={run} disabled={!bundle}>{t("checkSchemes", lang)}</button>
            {ms !== null && <p className="tiny">Local rule evaluation: {ms.toFixed(1)} ms on {bundle?.rules.length} cached rules · bundle {bundle?.bundle_version}</p>}
          </section>
        )}
        <section className="card stack">
          {results && !embedded && (<>
            <h2>Local results</h2>
            {results.map((r) => (
              <div key={r.rule_id} className="row spread" style={{ borderBottom: "1px solid var(--line)", paddingBottom: ".4rem" }}>
                <div><strong>{r.scheme_name}</strong>
                  <div className="tiny">{r.rule_id} v{r.rule_version}{r.missing_facts.length > 0 && ` · missing: ${r.missing_facts.map((m) => attrLabel(m, lang)).join(", ")}`}</div></div>
                <div className="row"><OutcomeBadge outcome={r.outcome} lang={lang} />
                  {r.outcome !== "MISMATCH" && <button className="btn small" onClick={() => queue(r)}>Save draft to outbox</button>}</div>
              </div>
            ))}
            <label className="field">{attrLabel("applicant_name", lang)}<input type="text" value={name} onChange={(e) => setName(e.target.value)} /></label>
            <label className="row small"><input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} /> {t("consent", lang)}</label>
          </>)}
          <div className="row spread"><h2>Kiosk outbox</h2>
            <span className="row">
              <button className="btn small" onClick={() => sync(false)} disabled={!online}>Sync now</button>
              <button className="btn small" onClick={() => sync(true)} disabled={!online} title="Re-sends already-synced events with the same idempotency keys">Retry test (resend)</button>
              <button className="btn small" onClick={refresh} disabled={!online}>Refresh bundle</button>
              <button className="btn small ghost" onClick={() => { clearSynced(); setOutbox(getOutbox()); }}>Clear synced</button>
            </span></div>
          {outbox.length === 0 && <p className="muted small">Empty.</p>}
          {outbox.map((e) => (
            <div key={e.event_id} className="card flat small">
              <div className="row spread"><span className="mono tiny">{e.event_id.slice(0, 8)} · key {e.idempotency_key.slice(0, 8)}</span><StatusBadge status={e.sync.state} /></div>
              <div>{e.payload.scheme_id} · local {e.payload.local_result.outcome} · bundle {e.bundle_version} · attempts {e.sync.attempts}</div>
              {e.sync.result && (
                <div className="tiny">
                  server: {e.sync.result.status || "accepted"} {e.sync.result.server_outcome && `· online re-check ${e.sync.result.server_outcome}`}
                  {e.sync.result.result_changed && " · ⚠ result changed after online re-check"}
                  {e.sync.result.bundle_outdated && " · ⚠ kiosk bundle was outdated"}
                  {e.sync.result.duplicate_ack && " · duplicate ignored (idempotent)"}
                  {e.sync.result.code && <> · case code <strong className="mono">{e.sync.result.code}</strong></>}
                </div>
              )}
              {e.sync.last_error && <div className="tiny">last error: {e.sync.last_error}</div>}
            </div>
          ))}
          {msg && <p className="notice info small">{msg}</p>}
          <ErrorNote error={err} />
        </section>
      </div>
    </div>
  );
}
