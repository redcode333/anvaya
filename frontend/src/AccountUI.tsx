import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import { consentBody, pinProblem, saveWithConsent, sendEmailCode, startGoogle, verifyEmailCode, type AuthLike, type EmailFlow } from "./account";
import { absoluteLimitMs, createIdleTimer, type IdleTimer } from "./idle";
import { supabase } from "./auth";
import { ErrorNote } from "./components";
import { CopyButton, ListenButton } from "./ListenControls";
import { downloadPassportPdf } from "./passportPdf";
import { consentNotice, retentionText, t } from "./i18n";
import { speak, voiceProvider } from "./speech";
import { useApp } from "./state";

const authClient = () => supabase!.auth as unknown as AuthLike;

/** The itemised consent notice (purpose, what is stored, retention, how to withdraw) in the citizen's language. */
export function ConsentNotice({ open = false }: { open?: boolean }) {
  const { lang, config } = useApp();
  if (!config) return null;
  return (
    <details className="small" open={open}>
      <summary>{t("consentNoticeTitle", lang)} <span className="tiny mono">({config.retention.consent_version})</span></summary>
      <div className="notice-text">
        {consentNotice(lang, config.retention).map(([h, body]) => <div key={h}><h3>{h}</h3><p>{body}</p></div>)}
      </div>
    </details>
  );
}

export function RetentionNote() {
  const { lang, config } = useApp();
  if (!config) return null;
  return (
    <details className="small">
      <summary>{t("privacyTitle", lang)}</summary>
      <p className="tiny" style={{ marginTop: ".4rem" }}>{retentionText(lang, config.retention)}</p>
    </details>
  );
}

/** The Passport code, large, with a read-aloud button (kiosks read it out at once). */
export function CodeBig({ code, spoken, autoSpeak }: { code: string; spoken: string; autoSpeak?: boolean }) {
  const { lang, sessionId } = useApp();
  const [err, setErr] = useState<unknown>(null);
  const say = async () => speak(await voiceProvider(), sessionId, spoken, lang);
  useEffect(() => { if (autoSpeak) say(); }, [code]); // eslint-disable-line react-hooks/exhaustive-deps
  const download = async () => { setErr(null); try { await downloadPassportPdf(sessionId!, lang, code); } catch (e) { setErr(e); } };
  return (
    <div className="notice ok stack" role="status" aria-live="assertive">
      <div className="small"><strong>{t("yourPassportCode", lang)}</strong></div>
      <div className="code-big mono" aria-label={spoken}>{code}</div>
      <div className="row">
        <CopyButton text={code} label={t("copyCode", lang)} />
        <ListenButton label={t("readAgain", lang)} onPlay={say} />
        {sessionId && <button className="btn primary" onClick={download}>⬇ {t("downloadPassportCode", lang)}</button>}
      </div>
      <ErrorNote error={err} />
    </div>
  );
}

function CodeSave({ sessionId, consented, onSaved }: { sessionId: string; consented: boolean; onSaved: () => void }) {
  const { lang, mode } = useApp();
  const [pin, setPin] = useState("");
  const [res, setRes] = useState<{ code: string; spoken: string; notice: string } | null>(null);
  const [err, setErr] = useState<unknown>(null);
  const problem = pin ? pinProblem(pin) : null;
  const save = async () => {
    setErr(null);
    try {
      setRes(await api(`/sessions/${sessionId}/passport-code`, { body: { pin, ...consentBody(lang) } }));
      setPin(""); onSaved();
    } catch (e) { setErr(e); }
  };
  if (res) return <><CodeBig code={res.code} spoken={res.spoken} autoSpeak={mode === "kiosk"} /><p className="small">{res.notice}</p></>;
  return (
    <div className="stack">
      <label className="field">{t("choosePin", lang)}
        <input type="password" inputMode="numeric" autoComplete="off" maxLength={4} value={pin} className="pin"
          onChange={(e) => setPin(e.target.value.replace(/\D/g, "").slice(0, 4))} aria-invalid={!!problem} />
      </label>
      {problem && <p className="small notice error">{t(problem === "weak" ? "pinWeak" : "pinFormat", lang)}</p>}
      <ErrorNote error={err} />
      <button className="btn primary" disabled={!consented || !pin || !!problem} onClick={save}>{t("saveWithCode", lang)}</button>
    </div>
  );
}

/** "Save my passports": consent first, then an email code (links the anonymous account, same user id), Google
 *  (when enabled), or a Passport code + PIN. Kiosks offer only the code. */
export function SavePanel({ sessionId }: { sessionId: string }) {
  const { lang, mode, citizen, config, refreshAuth } = useApp();
  const [consent, setConsent] = useState(false);
  const [saved, setSaved] = useState<boolean | null>(null);
  const [email, setEmail] = useState(""), [code, setCode] = useState("");
  const [flow, setFlow] = useState<EmailFlow | null>(null);
  const [err, setErr] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const accounts = mode === "personal" && !!supabase && !!citizen;

  useEffect(() => {
    if (!accounts) return;
    api<{ saved: boolean }>("/account").then((a) => setSaved(a.saved)).catch(() => setSaved(false));
  }, [accounts, citizen?.is_anonymous]);

  if (saved) return <div className="card notice ok">✓ {t("savedAccount", lang)}</div>;
  const run = async (fn: () => Promise<void>) => { setErr(null); setBusy(true); try { await fn(); } catch (e) { setErr(e); } setBusy(false); };
  const send = () => run(async () => setFlow(await sendEmailCode(authClient(), email.trim())));
  const verify = () => run(async () => {
    await verifyEmailCode(authClient(), email.trim(), code, flow!);
    await refreshAuth();
    await saveWithConsent(lang);
    setSaved(true);
  });

  return (
    <section className="card stack" aria-labelledby="save-h">
      <h2 id="save-h">💾 {t("savePassports", lang)}</h2>
      <p className="small">{t("saveIntro", lang)}</p>
      <label className="row small" style={{ alignItems: "flex-start" }}>
        <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
        <span>{t("consentSave", lang)} <span className="tiny mono">({config?.retention.consent_version})</span></span>
      </label>
      <ConsentNotice />
      {accounts && (
        <div className="stack">
          {!flow ? (
            <div className="row">
              <input type="email" placeholder={t("email", lang)} aria-label={t("email", lang)} value={email} onChange={(e) => setEmail(e.target.value)} style={{ flex: 1 }} />
              <button className="btn" disabled={!consent || !email.includes("@") || busy} onClick={send}>{t("sendCode", lang)}</button>
            </div>
          ) : (
            <div className="row">
              <input type="text" inputMode="numeric" autoComplete="one-time-code" placeholder={t("enterCode", lang)} aria-label={t("enterCode", lang)}
                value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))} style={{ flex: 1 }} />
              <button className="btn primary" disabled={!consent || code.length !== 6 || busy} onClick={verify}>{t("verifySave", lang)}</button>
            </div>
          )}
          {config?.google_enabled && (
            <button className="btn" disabled={!consent || busy} onClick={() => run(async () => { await startGoogle(authClient(), lang, window.location.href); })}>{t("google", lang)}</button>
          )}
        </div>
      )}
      <ErrorNote error={err} />
      <details open={mode === "kiosk"}>
        <summary className="small">{t("orCode", lang)}</summary>
        <div style={{ marginTop: ".5rem" }}><CodeSave sessionId={sessionId} consented={consent} onSaved={() => undefined} /></div>
      </details>
      <RetentionNote />
    </section>
  );
}

/** Kiosk: after KIOSK_IDLE_SECONDS without input, a 30 s "Still there?" warning, then End session. Separately, the
 *  session ends at its absolute limit (KIOSK_MAX_SESSION_MINUTES, the server's expires_at) whatever the activity. */
export function KioskIdleGuard() {
  const { mode, sessionId, sessionExpiresAt, config, lang, endCitizenSession } = useApp();
  const [warning, setWarning] = useState(false);
  const [left, setLeft] = useState(0);
  const timer = useRef<IdleTimer | null>(null);
  const active = mode === "kiosk" && !!sessionId && !!config;

  useEffect(() => {
    if (!active || !sessionExpiresAt) return;
    const ms = absoluteLimitMs(sessionExpiresAt, Date.now());
    const t = setTimeout(() => endCitizenSession("idle"), ms);
    return () => clearTimeout(t);
  }, [active, sessionId, sessionExpiresAt]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!active) return;
    const warn = config!.kiosk_warning_seconds;
    let tick: ReturnType<typeof setInterval> | undefined;
    timer.current = createIdleTimer({
      idleSeconds: config!.kiosk_idle_seconds, warningSeconds: warn,
      onWarn: () => {
        setWarning(true); setLeft(warn);
        tick = setInterval(() => setLeft((x) => Math.max(0, x - 1)), 1000);
        voiceProvider().then((p) => speak(p, sessionId, t("stillThere", lang), lang));
      },
      onActive: () => { setWarning(false); clearInterval(tick); },
      onTimeout: () => { clearInterval(tick); setWarning(false); endCitizenSession("idle"); },
    });
    const activity = () => timer.current?.activity();
    const events = ["pointerdown", "keydown", "touchstart", "wheel"];
    events.forEach((e) => window.addEventListener(e, activity, { passive: true }));
    return () => { timer.current?.stop(); clearInterval(tick); events.forEach((e) => window.removeEventListener(e, activity)); };
  }, [active, sessionId]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!warning) return null;
  return (
    <div className="overlay" role="alertdialog" aria-modal="true" aria-labelledby="idle-h">
      <div className="card stack" style={{ maxWidth: 460, textAlign: "center" }}>
        <h2 id="idle-h" style={{ justifyContent: "center" }}>{t("stillThere", lang)}</h2>
        <p>{t("stillThereBody", lang)} <strong className="mono">{left}</strong> s.</p>
        <button className="btn primary" autoFocus onClick={() => timer.current?.activity()}>{t("imHere", lang)}</button>
      </div>
    </div>
  );
}
