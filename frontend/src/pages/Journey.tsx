import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, type Fact } from "../api";
import { choices, splitPending } from "../confirmation";
import { ensureAnonymous, startDigiLocker, type AuthLike } from "../account";
import { RetentionNote } from "../AccountUI";
import { supabase } from "../auth";
import { ErrorNote, KioskOperatorBar, StaffLogin, ValueInput } from "../components";
import { MicIcon } from "../landing/DemoCard";
import { useCaptcha } from "../Turnstile";
import { ATTR, attrLabel, showValue, t, type Lang } from "../i18n";
import { listen, speak, verbxFailedOver, voiceProvider, type Provider, type Recorder } from "../speech";
import { useApp } from "../state";
import { getOutbox, refreshBundle } from "../offline/store";
import OfflinePrescreen from "./OfflinePrescreen";
import demoPhrases from "../../../backend/anvaya/data/demo_phrases.json";

type Msg = { who: "bot" | "me"; text: string; meta?: string; guard?: string };
type Profile = { session: { session_id: string; language: Lang; workflow_state: string }; facts: Fact[]; needs_confirmation: string[] };

// Kiosk demo phrases: shared with the backend, which lets only these (and demo/test sessions) reach free-tier LLMs.
const SAMPLES = demoPhrases as Record<Lang, { label: string; text: string }[]>;

export default function Journey({ mode }: { mode: "personal" | "kiosk" }) {
  const app = useApp();
  const { lang, sessionId, setSessionId, staff, citizen, config, online, setMode, endCitizenSession, refreshAuth } = app;
  const nav = useNavigate();
  const captcha = useCaptcha(lang);
  // Turnstile only guards the anonymous sign-in, which happens once per device (personal mode, no session yet).
  const needsCaptcha = mode === "personal" && !!supabase && !staff && !citizen;
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [text, setText] = useState("");
  const [err, setErr] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [provider, setProvider] = useState<Provider>("none");
  const [rec, setRec] = useState<Recorder | null>(null);
  const [voiceNote, setVoiceNote] = useState<string>("");
  const [audioNote, setAudioNote] = useState(false);
  const [editing, setEditing] = useState<{ fact_id?: string; attribute: string; value: any } | null>(null);
  const chatRef = useRef<HTMLDivElement>(null);

  useEffect(() => { if (app.mode !== mode) setMode(mode); }, [mode]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { voiceProvider().then(setProvider); }, []);
  // Kiosk keeps its offline rule bundle fresh whenever it is online, so a later outage still has rules.
  useEffect(() => { if (mode === "kiosk" && online) refreshBundle(); }, [mode, online]);
  useEffect(() => { chatRef.current?.scrollTo({ top: chatRef.current.scrollHeight, behavior: "smooth" }); }, [msgs, busy]);

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

  // Fire-and-forget: the text is already on screen; audio plays when (and if) it arrives.
  const say = (sid: string, text: string | string[]) => {
    setAudioNote(false);
    speak(provider, sid, text, lang).then((used) => setAudioNote(used === "unavailable"));
  };

  const begin = async () => {
    setErr(null);
    try {
      // Personal mode starts with an anonymous Supabase session, so "Save my passports" can later link an email to
      // the same user id. Kiosks never create citizen accounts.
      if (mode === "personal" && supabase && !staff) {
        try { await ensureAnonymous(supabase.auth as unknown as AuthLike, captcha.token); } finally { captcha.used(); }
        await refreshAuth();
      }
      const s = await api<{ session_id: string; expires_at: string; greeting: string; account?: { saved: boolean; restored: string[]; reconfirm: string[] } | null }>(
        "/sessions", { body: { mode, language: lang } });
      setSessionId(s.session_id, s.expires_at);
      const restored = s.account?.saved && s.account.restored.length
        ? [{ who: "bot" as const, text: `${t("savedProfile", lang)}: ${s.account.restored.length}${s.account.reconfirm.length ? ` · ${t("reconfirm", lang)}: ${s.account.reconfirm.length}` : ""}` }] : [];
      setMsgs([{ who: "bot", text: s.greeting }, ...restored]);
      if (mode === "kiosk") say(s.session_id, s.greeting);
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
      setMsgs((m) => [...m, { who: "bot", guard: r.guardrail ?? undefined, text: r.reply, meta: r.extracted.length ? `${r.extracted.map((f: Fact) => f.fact_id).join(", ")}${gl}` : gl || undefined }]);
      if (mode === "kiosk" || channel === "voice") say(sessionId, r.reply_segments ?? r.reply);
      await loadProfile(sessionId);
    } catch (e) { setErr(e); }
    setBusy(false);
  };

  const mic = () => {
    if (rec) { rec.stop(); setRec(null); return; }
    setVoiceNote("");
    const r = listen(provider, sessionId!, lang, (txt) => send(txt, "voice"), (m) => setVoiceNote(m),
      () => { setRec(null); voiceProvider().then(setProvider); });
    setRec(r);
  };

  const confirmFact = async (f: Fact) => {
    await api(`/sessions/${sessionId}/profile/facts/${f.fact_id}`, { method: "PATCH", body: { confirmed: true } }).catch(setErr);
    loadProfile(sessionId!);
  };
  const chooseValue = async (f: Fact, value: any) => {
    await api(`/sessions/${sessionId}/profile/facts/${f.fact_id}`, { method: "PATCH", body: { value } }).catch(setErr);
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
    await endCitizenSession("user");
    setMsgs([]); setProfile(null); setText("");
  };
  // The kiosk idle timeout ends the session from outside this page: clear what is on screen too.
  useEffect(() => { if (!sessionId) { setMsgs([]); setProfile(null); setText(""); } }, [sessionId]);

  if (mode === "kiosk" && !(staff && ["operator", "admin"].includes(staff.role)))
    return <StaffLogin roles={["operator", "admin"]} title="Kiosk operator sign-in"
      hint="A kiosk operator starts each temporary citizen session." />;

  if (mode === "kiosk" && !online) return <><KioskOperatorBar /><OfflinePrescreen /></>;

  if (!sessionId)
    return (
      <div className="stack">
      {mode === "kiosk" && <KioskOperatorBar />}
      <div className="card stack" style={{ maxWidth: 560 }}>
        <h1>{t("tagline", lang)}</h1>
        <p className="muted">{t("intro", lang)}</p>
        <ErrorNote error={err} />
        {needsCaptcha && captcha.widget}
        <button className="btn primary" onClick={begin} disabled={needsCaptcha && !captcha.ready}>{t("start", lang)}</button>
        <button className="btn ghost small" onClick={() => nav("/resume")}>{t("resume", lang)}</button>
        <RetentionNote />
        <p className="tiny">Voice: {provider === "verbx" ? "VerbX" : provider === "browser" ? `browser speech (VerbX ${verbxFailedOver() ? "unavailable" : "not configured"})` : "not available — text only"}.
          Audio is not stored by Anvaya.</p>
      </div>
      </div>
    );

  const facts = profile?.facts.filter((f) => f.attribute !== "applicant_name") ?? [];
  const pending = profile?.needs_confirmation ?? [];
  const { individual, bulk } = splitPending(facts);
  const known = new Set(profile?.facts.map((f) => f.attribute));
  // Date of birth comes only from DigiLocker (verified); it is not typed in.
  const addable = Object.keys(ATTR).filter((a) => !known.has(a) && a !== "date_of_birth");
  const digilocker = async () => {
    setErr(null);
    try { window.location.assign(await startDigiLocker(sessionId!)); } catch (e) { setErr(e); }
  };

  return (
    <div className="stack">
    {mode === "kiosk" && <KioskOperatorBar />}
    <div className="grid two">
      <section className="card">
        <h2>{mode === "kiosk" ? "🗣️" : "💬"} {t("tagline", lang)}</h2>
        <div className="chat" ref={chatRef} aria-live="polite">
          {msgs.length === 0 && <div className="bubble bot">{{ en: "Continue telling me about your household.", hi: "अपने परिवार के बारे में बताते रहिए।", te: "మీ కుటుంబం గురించి చెప్పడం కొనసాగించండి." }[lang]}</div>}
          {msgs.map((m, i) => (
            <div key={i} className={`bubble ${m.who}${m.guard && m.guard !== "smalltalk" ? " guard" : ""}`}>{m.text}{m.meta && <div className="tiny mono">{m.meta}</div>}</div>
          ))}
          {busy && <div className="bubble bot typing" role="status" aria-label="Anvaya is replying"><i /><i /><i /></div>}
        </div>
        <div className="composer">
          <button type="button" className={`orb-mic ${rec ? "rec" : ""}`} onClick={mic} disabled={busy || provider === "none"}
            aria-label={rec ? t("listening", lang) : t("speak", lang)} aria-pressed={!!rec}
            title={provider === "none" ? "Voice not available" : `Voice via ${provider}`}>
            <span className="orb-ring" aria-hidden="true" /><span className="orb-ring r2" aria-hidden="true" />
            <MicIcon size={28} />
          </button>
          <textarea value={text} onChange={(e) => setText(e.target.value)} placeholder={t("typeHere", lang)} aria-label={t("typeHere", lang)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(text); } }} />
          <button className="btn primary" onClick={() => send(text)} disabled={busy || !text.trim()}>{t("send", lang)}</button>
        </div>
        {rec && <p className="small" role="status">{t("listening", lang)}</p>}
        {voiceNote && <p className="notice small">{voiceNote}</p>}
        {audioNote && <p className="tiny muted" role="status">🔇 {t("audioUnavailable", lang)}</p>}
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
        {individual.length > 0 && <div className="notice">{t("needsConfirm", lang)}: {individual.length} · {t("confirmEach", lang)}</div>}
        <div className="facts">
          {facts.length === 0 && <p className="muted small">—</p>}
          {facts.map((f) => {
            const isPending = !f.confirmed;
            const readBack = isPending && individual.includes(f) && f.readback;
            const isEditing = editing?.fact_id === f.fact_id;
            return (
              <div key={f.fact_id} className={`fact ${isPending ? "pending" : ""}`}>
                <div>
                  <div className="k">{attrLabel(f.attribute, lang)} {f.high_impact && <span className="chip" title="High-impact: must be confirmed">!</span>} {f.verified && <span className="chip on">{t("verifiedDigiLocker", lang)}</span>} <span className="mono tiny">{f.fact_id}</span></div>
                  {isEditing ? <ValueInput attr={f.attribute} value={editing!.value} onChange={(v) => setEditing({ ...editing!, value: v })} lang={lang} />
                    : <div className="v">{showValue(f.attribute, f.value, lang)}</div>}
                  {readBack && !isEditing && !f.disputed && <div className="small" role="status"><strong>{t("isThisRight", lang)}</strong> <span className="mono">{f.readback}</span></div>}
                  {f.disputed && !isEditing && <div className="small" role="status"><strong>{t("whichIsRight", lang)}</strong></div>}
                  <div className="tiny">
                    {f.raw_text && <>“{f.raw_text}” · </>}{f.source}{f.inferred && " · inferred"}{f.note && ` · ${f.note}`}
                  </div>
                </div>
                <div className="row" style={{ justifyContent: "flex-end" }}>
                  {isEditing ? (<>
                    <button className="btn small primary" onClick={saveEdit}>{t("save", lang)}</button>
                    <button className="btn small" onClick={() => setEditing(null)}>{t("cancel", lang)}</button>
                  </>) : (<>
                    {choices(f).length > 0
                      ? choices(f).map((v) => <button key={String(v)} className="btn small primary mono" onClick={() => chooseValue(f, v)}>{showValue(f.attribute, v, lang)}</button>)
                      : isPending ? <button className="btn small primary" onClick={() => confirmFact(f)}>{t("confirm", lang)}</button>
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
          {bulk.length > 0 && <button className="btn" onClick={confirmAll}>{t("confirmAll", lang)}</button>}
          <button className="btn primary" disabled={pending.length > 0 || facts.length === 0} onClick={() => nav("/citizen/schemes")}>{t("checkSchemes", lang)} →</button>
        </div>
        {mode === "personal" && config?.digilocker_enabled && citizen && (
          <button className="btn" onClick={digilocker}>{t("digilocker", lang)}</button>
        )}
        {mode === "kiosk" && <button className="btn danger" onClick={endSession}>{t("endSession", lang)}</button>}
        {mode === "personal" && <button className="btn ghost small" onClick={endSession}>Start over</button>}
      </section>
    </div>
    {mode === "kiosk" && getOutbox().length > 0 && <OfflinePrescreen embedded />}
    </div>
  );
}
