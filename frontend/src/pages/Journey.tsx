import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, type Fact } from "../api";
import { ErrorNote, StaffLogin, ValueInput } from "../components";
import { ATTR, attrLabel, showValue, t, type Lang } from "../i18n";
import { listen, speak, voiceProvider, type Provider, type Recorder } from "../speech";
import { useApp } from "../state";
import { getOutbox, refreshBundle } from "../offline/store";
import OfflinePrescreen from "./OfflinePrescreen";

type Msg = { who: "bot" | "me"; text: string; meta?: string };
type Profile = { session: { session_id: string; language: Lang; workflow_state: string }; facts: Fact[]; needs_confirmation: string[] };

const SAMPLES: Record<Lang, { label: string; text: string }[]> = {
  te: [
    { label: "రైతు కుటుంబం (AP)", text: "నా వయస్సు 67 సంవత్సరాలు. నేను గుంటూరు, ఆంధ్రప్రదేశ్ లో ఒక గ్రామంలో ఉంటాను. 4 మంది సభ్యులు. మా ఆదాయం సంవత్సరానికి 60 వేలు. బీపీఎల్ కార్డు ఉంది. పెన్షన్ రావడం లేదు. నేను రైతు, 2 ఎకరాల భూమి ఉంది. బ్యాంక్ ఖాతా ఉంది." },
    { label: "వయస్సు తప్పుగా విన్నది", text: "నా వయస్సు 26 సంవత్సరాలు. ఆంధ్రప్రదేశ్ గ్రామంలో ఉంటాను. బీపీఎల్ కార్డు ఉంది. పెన్షన్ రావడం లేదు." },
  ],
  hi: [
    { label: "बिहार, उम्र गलत सुनी", text: "मेरी उम्र 26 साल है। मैं बिहार के गाँव में रहता हूँ। बीपीएल कार्ड है, कोई पेंशन नहीं मिलती। सालाना आय 40000 रुपये।" },
    { label: "विधवा, बिहार", text: "मैं 52 साल की विधवा हूँ, बिहार के गाँव में रहती हूँ। परिवार में 3 लोग। आय 3000 रुपये महीना। बीपीएल कार्ड है।" },
  ],
  en: [
    { label: "Farmer household (AP)", text: "I am 67 years old, a farmer in a village in Guntur, Andhra Pradesh. Family of 4, yearly income 60,000 rupees. We have a BPL card, I do not get any pension, I own 2 acres of land and have a bank account." },
    { label: "Maharashtra, 62", text: "I am 62 years old, BPL household, I do not get any pension. I live in Maharashtra, in a city. Family of 2, income 90000 per year." },
  ],
};

export default function Journey({ mode }: { mode: "personal" | "kiosk" }) {
  const app = useApp();
  const { lang, sessionId, setSessionId, staff, online, setMode, resetCitizen } = app;
  const nav = useNavigate();
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [text, setText] = useState("");
  const [err, setErr] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [provider, setProvider] = useState<Provider>("none");
  const [rec, setRec] = useState<Recorder | null>(null);
  const [voiceNote, setVoiceNote] = useState<string>("");
  const [editing, setEditing] = useState<{ fact_id?: string; attribute: string; value: any } | null>(null);
  const chatRef = useRef<HTMLDivElement>(null);

  useEffect(() => { if (app.mode !== mode) setMode(mode); }, [mode]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { voiceProvider().then(setProvider); }, []);
  // Kiosk keeps its offline rule bundle fresh whenever it is online, so a later outage still has rules.
  useEffect(() => { if (mode === "kiosk" && online) refreshBundle(); }, [mode, online]);
  useEffect(() => { chatRef.current?.scrollTo(0, chatRef.current.scrollHeight); }, [msgs]);

  const loadProfile = useCallback(async (sid: string) => {
    try { setProfile(await api<Profile>(`/sessions/${sid}`)); }
    catch (e: any) { if (["SESSION_EXPIRED", "SESSION_NOT_FOUND"].includes(e.code)) { setSessionId(null); setProfile(null); } else setErr(e); }
  }, [setSessionId]);

  useEffect(() => { if (sessionId && online) loadProfile(sessionId); }, [sessionId, online, loadProfile]);
  // Language switch mid-session keeps facts: only the display language changes on the server.
  useEffect(() => {
    if (sessionId && online && profile && profile.session.language !== lang)
      api(`/sessions/${sessionId}`, { method: "PATCH", body: { language: lang } }).then(() => loadProfile(sessionId)).catch(setErr);
  }, [lang]); // eslint-disable-line react-hooks/exhaustive-deps

  const begin = async () => {
    setErr(null);
    try {
      const s = await api<{ session_id: string; greeting: string }>("/sessions", { body: { mode, language: lang } });
      setSessionId(s.session_id);
      setMsgs([{ who: "bot", text: s.greeting }]);
      if (mode === "kiosk") speak(provider, s.session_id, s.greeting, lang);
    } catch (e) { setErr(e); }
  };

  const send = async (utterance: string, channel: "text" | "voice" = "text") => {
    if (!sessionId || !utterance.trim()) return;
    setBusy(true); setErr(null);
    setMsgs((m) => [...m, { who: "me", text: utterance, meta: channel === "voice" ? `${t("heard", lang)} (${provider})` : undefined }]);
    setText("");
    try {
      const r = await api<any>(`/sessions/${sessionId}/turns`, { body: { utterance, channel, language: lang } });
      const gl = r.glossary?.length ? ` · glossary: ${r.glossary.map((g: any) => `“${g.term}” → ${g.meaning}`).join("; ")}` : "";
      setMsgs((m) => [...m, { who: "bot", text: r.reply, meta: r.extracted.length ? `${r.extracted.map((f: Fact) => f.fact_id).join(", ")}${gl}` : gl || undefined }]);
      if (mode === "kiosk" || channel === "voice") speak(provider, sessionId, r.reply, lang);
      await loadProfile(sessionId);
    } catch (e) { setErr(e); }
    setBusy(false);
  };

  const mic = () => {
    if (rec) { rec.stop(); setRec(null); return; }
    setVoiceNote("");
    const r = listen(provider, sessionId!, lang, (txt) => send(txt, "voice"), (m) => setVoiceNote(m), () => setRec(null));
    setRec(r);
  };

  const confirmFact = async (f: Fact) => {
    await api(`/sessions/${sessionId}/profile/facts/${f.fact_id}`, { method: "PATCH", body: { confirmed: true } }).catch(setErr);
    loadProfile(sessionId!);
  };
  const saveEdit = async () => {
    if (!editing || editing.value === null || editing.value === "") return;
    try {
      if (editing.fact_id) await api(`/sessions/${sessionId}/profile/facts/${editing.fact_id}`, { method: "PATCH", body: { value: editing.value } });
      else await api(`/sessions/${sessionId}/profile/facts`, { body: { attribute: editing.attribute, value: editing.value } });
      setEditing(null);
      loadProfile(sessionId!);
    } catch (e) { setErr(e); }
  };
  const confirmAll = async () => { await api(`/sessions/${sessionId}/profile/confirm-all`, { body: {} }).catch(setErr); loadProfile(sessionId!); };

  const endSession = async () => {
    if (sessionId) await api(`/sessions/${sessionId}/end`, { body: {} }).catch(() => undefined);
    resetCitizen(); setMsgs([]); setProfile(null); setText("");
  };

  if (mode === "kiosk" && !(staff && ["operator", "admin"].includes(staff.role)))
    return <StaffLogin roles={["operator", "admin"]} title="Kiosk operator sign-in"
      hint="A kiosk operator starts each temporary citizen session. Demo account: operator / operator123." />;

  if (mode === "kiosk" && !online) return <OfflinePrescreen />;

  if (!sessionId)
    return (
      <div className="card stack" style={{ maxWidth: 560 }}>
        <h1>{t("tagline", lang)}</h1>
        <p className="muted">{t("intro", lang)}</p>
        <ErrorNote error={err} />
        <button className="btn primary" onClick={begin}>{t("start", lang)}</button>
        <p className="tiny">Voice: {provider === "verbx" ? "VerbX" : provider === "browser" ? "browser speech (VerbX not configured)" : "not available — text only"}.
          Audio is not stored by Anvaya.</p>
      </div>
    );

  const facts = profile?.facts.filter((f) => f.attribute !== "applicant_name") ?? [];
  const pending = profile?.needs_confirmation ?? [];
  const known = new Set(profile?.facts.map((f) => f.attribute));
  const addable = Object.keys(ATTR).filter((a) => !known.has(a));

  return (
    <div className="stack">
    <div className="grid two">
      <section className="card">
        <h2>{mode === "kiosk" ? "🗣️" : "💬"} {t("tagline", lang)}</h2>
        <div className="chat" ref={chatRef} aria-live="polite">
          {msgs.length === 0 && <div className="bubble bot">{{ en: "Continue telling me about your household.", hi: "अपने परिवार के बारे में बताते रहिए।", te: "మీ కుటుంబం గురించి చెప్పడం కొనసాగించండి." }[lang]}</div>}
          {msgs.map((m, i) => (
            <div key={i} className={`bubble ${m.who}`}>{m.text}{m.meta && <div className="tiny mono">{m.meta}</div>}</div>
          ))}
        </div>
        <div className="composer">
          <button className={`btn mic ${rec ? "rec" : ""}`} onClick={mic} disabled={busy || provider === "none"}
            aria-label={rec ? t("listening", lang) : t("speak", lang)} title={provider === "none" ? "Voice not available" : `Voice via ${provider}`}>🎤</button>
          <textarea value={text} onChange={(e) => setText(e.target.value)} placeholder={t("typeHere", lang)} aria-label={t("typeHere", lang)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(text); } }} />
          <button className="btn primary" onClick={() => send(text)} disabled={busy || !text.trim()}>{t("send", lang)}</button>
        </div>
        {rec && <p className="small" role="status">{t("listening", lang)}</p>}
        {voiceNote && <p className="notice small">{voiceNote}</p>}
        <details className="small" style={{ marginTop: ".75rem" }}>
          <summary>Demo phrases (simulated transcripts)</summary>
          <div className="row" style={{ marginTop: ".5rem" }}>
            {SAMPLES[lang].map((s) => (
              <button key={s.label} className="btn small" onClick={() => send(s.text, "voice")} title="Sent as a voice transcript, so every fact needs confirmation">{s.label}</button>
            ))}
          </div>
        </details>
        <ErrorNote error={err} />
      </section>

      <section className="card stack">
        <div className="row spread">
          <h2>{t("profile", lang)}</h2>
          <span className="tiny mono">{profile?.session.workflow_state}</span>
        </div>
        {pending.length > 0 && <div className="notice">{t("needsConfirm", lang)}: {pending.length}</div>}
        <div className="facts">
          {facts.length === 0 && <p className="muted small">—</p>}
          {facts.map((f) => {
            const isPending = !f.confirmed;
            const isEditing = editing?.fact_id === f.fact_id;
            return (
              <div key={f.fact_id} className={`fact ${isPending ? "pending" : ""}`}>
                <div>
                  <div className="k">{attrLabel(f.attribute, lang)} {f.high_impact && <span className="chip" title="High-impact: must be confirmed">!</span>} <span className="mono tiny">{f.fact_id}</span></div>
                  {isEditing ? <ValueInput attr={f.attribute} value={editing!.value} onChange={(v) => setEditing({ ...editing!, value: v })} lang={lang} />
                    : <div className="v">{showValue(f.attribute, f.value, lang)}</div>}
                  <div className="tiny">
                    {f.raw_text && <>“{f.raw_text}” · </>}{f.source}{f.inferred && " · inferred"}{f.note && ` · ${f.note}`}
                  </div>
                </div>
                <div className="row" style={{ justifyContent: "flex-end" }}>
                  {isEditing ? (<>
                    <button className="btn small primary" onClick={saveEdit}>{t("save", lang)}</button>
                    <button className="btn small" onClick={() => setEditing(null)}>{t("cancel", lang)}</button>
                  </>) : (<>
                    {isPending ? <button className="btn small primary" onClick={() => confirmFact(f)}>{t("confirm", lang)}</button>
                      : <span className="chip on">✓ {t("confirmed", lang)}</span>}
                    <button className="btn small" onClick={() => setEditing({ fact_id: f.fact_id, attribute: f.attribute, value: f.value })}>{t("correct", lang)}</button>
                  </>)}
                </div>
              </div>
            );
          })}
        </div>
        {editing && !editing.fact_id && (
          <div className="fact"><div>
            <div className="k">{attrLabel(editing.attribute, lang)}</div>
            <ValueInput attr={editing.attribute} value={editing.value} onChange={(v) => setEditing({ ...editing, value: v })} lang={lang} />
          </div><div className="row"><button className="btn small primary" onClick={saveEdit}>{t("save", lang)}</button>
            <button className="btn small" onClick={() => setEditing(null)}>{t("cancel", lang)}</button></div></div>
        )}
        {addable.length > 0 && !editing && (
          <label className="field">{t("addDetail", lang)}
            <select value="" onChange={(e) => e.target.value && setEditing({ attribute: e.target.value, value: null })}>
              <option value="">+</option>{addable.map((a) => <option key={a} value={a}>{attrLabel(a, lang)}</option>)}
            </select>
          </label>
        )}
        <div className="row">
          {pending.length > 0 && <button className="btn" onClick={confirmAll}>{t("confirmAll", lang)}</button>}
          <button className="btn primary" disabled={pending.length > 0 || facts.length === 0} onClick={() => nav("/citizen/schemes")}>{t("checkSchemes", lang)} →</button>
        </div>
        {mode === "kiosk" && <button className="btn danger" onClick={endSession}>{t("endSession", lang)}</button>}
        {mode === "personal" && <button className="btn ghost small" onClick={endSession}>Start over</button>}
      </section>
    </div>
    {mode === "kiosk" && getOutbox().length > 0 && <OfflinePrescreen embedded />}
    </div>
  );
}
