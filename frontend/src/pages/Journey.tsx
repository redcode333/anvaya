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
import { ATTR, attrLabel, sessionState, showValue, t, type Lang } from "../i18n";
import { callSupported, startCall, type Call, type CallState } from "../call";
import { speak, stopSpeaking, voiceProvider, type Provider } from "../speech";
import { useApp } from "../state";
import { getOutbox, refreshBundle } from "../offline/store";
import OfflinePrescreen from "./OfflinePrescreen";
import demoPhrases from "../../../backend/anvaya/data/demo_phrases.json";

type Msg = { who: "bot" | "me"; text: string; note?: string; guard?: string; voice?: boolean };
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
  const [call, setCall] = useState<Call | null>(null);  // the hands-free call, while one is open
  const [callState, setCallState] = useState<CallState>("listening");
  const [voiceNote, setVoiceNote] = useState<string>("");
  const [audioNote, setAudioNote] = useState(false);
  const [editing, setEditing] = useState<{ fact_id?: string; attribute: string; value: any } | null>(null);
  const chatRef = useRef<HTMLDivElement>(null);
  // The call's callbacks outlive a render, so they read the latest values through refs.
  const callRef = useRef<Call | null>(null);
  const starting = useRef(false);
  const busyRef = useRef(false);
  const langRef = useRef(lang);
  const sendRef = useRef<(u: string, c?: "text" | "voice") => Promise<void>>(async () => undefined);
  const turns = useRef<Promise<void>>(Promise.resolve());  // sentences spoken while a reply is pending wait their turn
  busyRef.current = busy; langRef.current = lang;

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

  const send = async (utterance: string, channel: "text" | "voice" = "text"): Promise<void> => {
    if (!sessionId || !utterance.trim()) return;
    setBusy(true); setErr(null);
    setMsgs((m) => [...m, { who: "me", text: utterance, voice: channel === "voice" }]);
    setText("");
    try {
      const r = await api<any>(`/sessions/${sessionId}/turns`, { body: { utterance, channel, language: lang } });
      const gl = r.glossary?.length ? r.glossary.map((g: any) => `“${g.term}” — ${g.meaning}`).join(" · ") : undefined;
      setMsgs((m) => [...m, { who: "bot", guard: r.guardrail ?? undefined, text: r.reply, note: gl }]);
      if (mode === "kiosk" || channel === "voice") say(sessionId, r.reply_segments ?? r.reply);
      await loadProfile(sessionId);
    } catch (e) { setErr(e); }
    setBusy(false);
  };
  sendRef.current = send;

  // One tap opens a hands-free call (the mic stays open, sentences are sent as they finish, and talking over the bot
  // makes it stop and listen); the next tap ends it.
  const mic = async () => {
    if (callRef.current) { callRef.current.stop(); return; }
    if (starting.current || !sessionId) return;
    starting.current = true;
    setVoiceNote("");
    stopSpeaking();
    const c = await startCall({
      provider, sessionId, lang: () => langRef.current, busy: () => busyRef.current,
      onText: (txt) => { turns.current = turns.current.then(() => sendRef.current(txt, "voice")); },
      onState: setCallState, onError: setVoiceNote,
      onEnd: () => { callRef.current = null; setCall(null); setCallState("listening"); voiceProvider().then(setProvider); },
    });
    starting.current = false;
    if (!c) return;
    callRef.current = c; setCall(c);
    // Like picking up a phone: the bot greets first when nothing has been said yet.
    if (msgs.length === 1 && msgs[0].who === "bot") say(sessionId, msgs[0].text);
  };
  // The call ends with the session, and when the page is left.
  useEffect(() => { if (!sessionId) callRef.current?.stop(); }, [sessionId]);
  useEffect(() => () => { callRef.current?.stop(); stopSpeaking(); }, []);

  // Using the card instead of answering the bot's "Is that right?" out loud: stop the spoken question and say it was taken.
  const acknowledge = (text: string) => { stopSpeaking(); setMsgs((m) => [...m, { who: "bot", text }]); };
  const confirmFact = async (f: Fact) => {
    try {
      await api(`/sessions/${sessionId}/profile/facts/${f.fact_id}`, { method: "PATCH", body: { confirmed: true } });
      acknowledge(`${t("confirmed", lang)} ✓ ${attrLabel(f.attribute, lang)}: ${showValue(f.attribute, f.value, lang)}`);
    } catch (e) { setErr(e); }
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
  const confirmAll = async () => {
    try { await api(`/sessions/${sessionId}/profile/confirm-all`, { body: {} }); acknowledge(t("allConfirmedMsg", lang)); } catch (e) { setErr(e); }
    loadProfile(sessionId!);
  };

  const endSession = async () => {
    await endCitizenSession("user");
    setMsgs([]); setProfile(null); setText("");
  };
  // The kiosk idle timeout ends the session from outside this page: clear what is on screen too.
  useEffect(() => { if (!sessionId) { setMsgs([]); setProfile(null); setText(""); } }, [sessionId]);

  if (mode === "kiosk" && !(staff && ["operator", "admin"].includes(staff.role)))
    return (
      <div className="kiosk-gate">
        <section className="kiosk-gate-intro">
          <span className="kiosk-gate-icon" aria-hidden="true">
            <svg width="34" height="34" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><rect x="4" y="3" width="16" height="12" rx="2" /><path d="M12 15v4M8 21h8" /></svg>
          </span>
          <h1>{t("kioskSetupT", lang)}</h1>
          <p>{t("kioskSetupD", lang)}</p>
          <ul>{(["kioskPoint1", "kioskPoint2", "kioskPoint3"] as const).map((k) => <li key={k}>{t(k, lang)}</li>)}</ul>
        </section>
        <StaffLogin roles={["operator", "admin"]} title="Kiosk operator sign-in"
          hint="A kiosk operator starts each temporary citizen session." />
      </div>
    );

  if (mode === "kiosk" && !online) return <><KioskOperatorBar /><OfflinePrescreen /></>;

  if (!sessionId)
    return (
      <div className="stack">
      {mode === "kiosk" && <KioskOperatorBar />}
      <div className={`welcome${mode === "kiosk" ? " kiosk-welcome" : ""}`}>
        <section className="welcome-main">
          <span className="welcome-orb" aria-hidden="true"><span className="orb-ring" /><span className="orb-ring r2" /><MicIcon size={30} /></span>
          <h1>{t("tagline", lang)}</h1>
          <p className="welcome-intro">{t("intro", lang)}</p>
          <ErrorNote error={err} />
          {needsCaptcha && captcha.widget}
          <div className="welcome-actions">
            <button className="btn primary welcome-start" onClick={begin} disabled={needsCaptcha && !captcha.ready}>
              <MicIcon size={20} />{t("start", lang)}
            </button>
            <button className="btn ghost" onClick={() => nav("/resume")}>{t("resume", lang)}</button>
          </div>
          <ul className="welcome-chips">
            {(["wChip1", "wChip2", "wChip3"] as const).map((k) => <li key={k}>{t(k, lang)}</li>)}
          </ul>
          <RetentionNote />
          <p className="tiny">{provider === "none" ? t("voiceOff", lang) : t("voiceOn", lang)}</p>
        </section>
        <ol className="welcome-steps" aria-label="How it works">
          {([1, 2, 3] as const).map((n) => (
            <li key={n}>
              <span className="welcome-num" aria-hidden="true">{n}</span>
              <div><b>{t(`wStep${n}T` as "wStep1T", lang)}</b><span>{t(`wStep${n}D` as "wStep1D", lang)}</span></div>
            </li>
          ))}
        </ol>
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
            <div key={i} className={`bubble ${m.who}${m.guard && ["abuse", "injection", "sensitive", "offtopic"].includes(m.guard) ? " guard" : ""}`}>
              {m.voice && <span className="bubble-voice" title={t("voiceInput", lang)}><MicIcon size={13} /></span>}{m.text}{m.note && <div className="bubble-note">ℹ {m.note}</div>}</div>
          ))}
          {busy && <div className="bubble bot typing" role="status" aria-label="Anvaya is replying"><i /><i /><i /></div>}
        </div>
        <div className="composer">
          <button type="button" className={`orb-mic ${call ? "rec" : ""}`} onClick={mic} disabled={!callSupported(provider)}
            aria-label={call ? t("endCall", lang) : t("speak", lang)} aria-pressed={!!call}
            title={provider === "none" ? "Voice not available" : `Voice via ${provider}`}>
            <span className="orb-ring" aria-hidden="true" /><span className="orb-ring r2" aria-hidden="true" />
            <MicIcon size={28} />
          </button>
          <textarea value={text} onChange={(e) => setText(e.target.value)} placeholder={t("typeHere", lang)} aria-label={t("typeHere", lang)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(text); } }} />
          <button className="btn primary" onClick={() => send(text)} disabled={busy || !text.trim()}>{t("send", lang)}</button>
        </div>
        {call && <p className="small" role="status">{t(({ listening: "callListening", hearing: "callHearing", thinking: "callThinking", speaking: "callSpeaking" } as const)[callState], lang)}</p>}
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
          <span className="chip">{sessionState(profile?.session.workflow_state, lang)}</span>
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
                  <div className="k">{attrLabel(f.attribute, lang)} {f.high_impact && <span className="chip" title="High-impact: must be confirmed">!</span>} {f.verified && <span className="chip on">{t("verifiedDigiLocker", lang)}</span>}</div>
                  {isEditing ? <ValueInput attr={f.attribute} value={editing!.value} onChange={(v) => setEditing({ ...editing!, value: v })} lang={lang} />
                    : <div className="v">{showValue(f.attribute, f.value, lang)}</div>}
                  {readBack && !isEditing && !f.disputed && <div className="small" role="status"><strong>{t("isThisRight", lang)}</strong> <span>{f.readback}</span></div>}
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
