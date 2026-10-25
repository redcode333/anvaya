import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, ApiError } from "../api";
import { deleteAccount, downloadMyData, formatCode, loadHistory, sendEmailCode, sendPhoneCode, verifyEmailCode, verifyPhoneCode, whatChanged, type AuthLike, type Change, type EmailFlow, type PassportVersion, type Reason } from "../account";
import { ConsentNotice, RetentionNote } from "../AccountUI";
import { useCaptcha } from "../Turnstile";
import { supabase } from "../auth";
import { ErrorNote, OutcomeBadge } from "../components";
import { attrLabel, showValue, t, type Lang } from "../i18n";
import { useApp } from "../state";

type Account = {
  saved: boolean; is_anonymous: boolean; email: string | null; has_passport_code: boolean; passport_count: number;
  consent: { version: string; consented_at: string } | null;
  profile: { fact_id: string; attribute: string; value: any; confirmed_at: string | null; needs_reconfirmation: boolean }[];
};

const authClient = () => supabase!.auth as unknown as AuthLike;

export function reasonText(r: Reason, lang: Lang): string {
  if (r.kind === "fact_changed") return `${t("factChanged", lang)}: ${attrLabel(r.attribute, lang)} ${showValue(r.attribute, r.before, lang)} → ${showValue(r.attribute, r.after, lang)}`;
  if (r.kind === "rule_changed") return `${t("ruleChanged", lang)}: ${r.rule_id} v${r.before} → v${r.after}`;
  return `${t("documentChanged", lang)}: ${r.doc_key} ${r.before ?? "—"} → ${r.after ?? "—"}`;
}

function EmailSignIn() {
  const { lang, refreshAuth } = useApp();
  const [email, setEmail] = useState(""), [code, setCode] = useState("");
  const [flow, setFlow] = useState<EmailFlow | null>(null);
  const [err, setErr] = useState<unknown>(null);
  const captcha = useCaptcha(lang);
  const run = async (fn: () => Promise<void>) => { setErr(null); try { await fn(); } catch (e) { setErr(e); } };
  const send = () => run(async () => {
    try { setFlow(await sendEmailCode(authClient(), email.trim(), captcha.token)); } finally { captcha.used(); }
  });
  return (
    <div className="card stack" style={{ maxWidth: 520 }}>
      <h2>{t("signInEmail", lang)}</h2>
      {!flow ? (
        <>
          <div className="row">
            <input type="email" value={email} placeholder={t("email", lang)} aria-label={t("email", lang)} onChange={(e) => setEmail(e.target.value)} style={{ flex: 1 }} />
            <button className="btn primary" disabled={!email.includes("@") || !captcha.ready} onClick={send}>{t("sendCode", lang)}</button>
          </div>
          {captcha.widget}
        </>
      ) : (
        <div className="row">
          <input type="text" inputMode="numeric" autoComplete="one-time-code" value={code} placeholder={t("enterCode", lang)} aria-label={t("enterCode", lang)}
            onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))} style={{ flex: 1 }} />
          <button className="btn primary" disabled={code.length !== 6} onClick={() => run(async () => { await verifyEmailCode(authClient(), email.trim(), code, flow); await refreshAuth(); })}>{t("open", lang)}</button>
        </div>
      )}
      <ErrorNote error={err} />
    </div>
  );
}

/** Phone OTP through Supabase phone auth — shown only when PHONE_OTP_ENABLED (Indian SMS needs DLT registration and a
 *  paid SMS provider, so it is off in this build). */
function PhoneSignIn() {
  const { lang, refreshAuth } = useApp();
  const [phone, setPhone] = useState(""), [sent, setSent] = useState<string | null>(null), [code, setCode] = useState("");
  const [err, setErr] = useState<unknown>(null);
  const captcha = useCaptcha(lang);
  const run = async (fn: () => Promise<void>) => { setErr(null); try { await fn(); } catch (e) { setErr(e); } };
  return (
    <div className="card stack" style={{ maxWidth: 520 }}>
      {!sent ? (
        <>
          <div className="row">
            <input type="tel" inputMode="tel" value={phone} placeholder="98xxxxxxxx" aria-label={t("phone", lang)} onChange={(e) => setPhone(e.target.value)} style={{ flex: 1 }} />
            <button className="btn primary" disabled={!captcha.ready} onClick={() => run(async () => {
              try { setSent(await sendPhoneCode(authClient(), phone, captcha.token)); } finally { captcha.used(); }
            })}>{t("sendCode", lang)}</button>
          </div>
          {captcha.widget}
        </>
      ) : (
        <div className="row">
          <input type="text" inputMode="numeric" autoComplete="one-time-code" value={code} placeholder={t("smsCode", lang)} aria-label={t("smsCode", lang)}
            onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))} style={{ flex: 1 }} />
          <button className="btn primary" disabled={code.length !== 6} onClick={() => run(async () => { await verifyPhoneCode(authClient(), sent, code); await refreshAuth(); })}>{t("open", lang)}</button>
        </div>
      )}
      <ErrorNote error={err} />
    </div>
  );
}

function AttachCode({ onDone }: { onDone: () => void }) {
  const { lang } = useApp();
  const [code, setCode] = useState(""), [pin, setPin] = useState("");
  const [err, setErr] = useState<unknown>(null);
  return (
    <details className="small">
      <summary>{t("attachCode", lang)}</summary>
      <div className="row" style={{ marginTop: ".5rem" }}>
        <input type="text" value={code} placeholder="PSP-XXXX-XXXX" aria-label={t("passportCode", lang)} onChange={(e) => setCode(formatCode(e.target.value))} />
        <input type="password" inputMode="numeric" value={pin} placeholder={t("pin", lang)} aria-label={t("pin", lang)} maxLength={4} onChange={(e) => setPin(e.target.value.replace(/\D/g, ""))} style={{ width: "6rem" }} />
        <button className="btn" onClick={async () => { setErr(null); try { await api("/account/attach-passport", { body: { code, pin } }); onDone(); } catch (e) { setErr(e); } }}>{t("save", lang)}</button>
      </div>
      <ErrorNote error={err} />
    </details>
  );
}

export default function MyPassports() {
  const { lang, citizen, sessionId, signOut, signOutAll, resetCitizen, config } = useApp();
  const [notice, setNotice] = useState<string | null>(null);
  const nav = useNavigate();
  const [account, setAccount] = useState<Account | null>(null);
  const [versions, setVersions] = useState<PassportVersion[] | null>(null);
  const [since, setSince] = useState("");
  const [changes, setChanges] = useState<Change[] | null>(null);
  const [confirmText, setConfirmText] = useState("");
  const [pendingCase, setPendingCase] = useState(false);  // the server asked for a second confirmation
  const [done, setDone] = useState(false);
  const [err, setErr] = useState<unknown>(null);
  const signedIn = !!citizen && !citizen.is_anonymous;
  // A Passport-code holder sees the history of the session they resumed; an account holder sees their account.
  const viaSession = !signedIn && sessionId ? sessionId : null;

  const load = useCallback(async () => {
    setErr(null);
    try {
      const acct = citizen ? await api<Account>("/account") : null;
      setAccount(acct);
      if (acct && !acct.saved && !viaSession) { setVersions(null); return; }  // nothing kept without consent
      const h = await loadHistory(viaSession);
      setVersions(h.versions);
      if (h.versions.length > 1) setSince(h.versions[1].created_at.slice(0, 10));
    } catch (e) { setErr(e); setVersions(null); }
  }, [citizen, viaSession]);
  useEffect(() => { if (signedIn || viaSession || citizen) load(); }, [signedIn, viaSession, citizen, load]);
  useEffect(() => {
    if (!since || !versions?.length) return;
    whatChanged(`${since}T23:59:59+00:00`, viaSession).then((r) => setChanges(r.changes)).catch(setErr);
  }, [since, versions, viaSession]);

  if (done) return <div className="card notice ok" role="status">{t("deleted", lang)} <Link to="/">←</Link></div>;
  if (!signedIn && !viaSession)
    return (
      <div className="stack">
        <h1>{t("myPassports", lang)}</h1>
        {notice && <div className="notice ok" role="status">{notice}</div>}
        {supabase && <EmailSignIn />}
        {supabase && config?.phone_otp_enabled && <PhoneSignIn />}
        <p><Link className="btn" to="/resume">{t("resume", lang)} →</Link></p>
        <ConsentNotice />
        <RetentionNote />
      </div>
    );

  const download = async () => { setErr(null); try { await downloadMyData(viaSession); } catch (e) { setErr(e); } };
  const everywhere = async () => {
    setErr(null);
    try { await signOutAll(); setNotice(t("signedOutAll", lang)); nav("/citizen/passports"); } catch (e) { setErr(e); }
  };

  const remove = async (acknowledgePendingCase = false) => {
    setErr(null);
    try { await deleteAccount(authClient(), { acknowledgePendingCase }); resetCitizen(); setDone(true); }
    catch (e) { if (e instanceof ApiError && e.code === "PENDING_CASE_DOCUMENTS") setPendingCase(true); else setErr(e); }
  };

  return (
    <div className="stack">
      <div className="row spread">
        <h1>{t("myPassports", lang)}</h1>
        {signedIn && <span className="row small">{account?.email ?? citizen?.email}
          <button className="btn small" onClick={() => signOut().then(() => nav("/"))}>{t("signOut", lang)}</button>
          <button className="btn small ghost" onClick={everywhere}>{t("signOutAll", lang)}</button></span>}
      </div>
      <ErrorNote error={err} />
      <section className="card row spread">
        <span className="small">{t("downloadDataHint", lang)}</span>
        <button className="btn" onClick={download}>⬇ {t("downloadData", lang)}</button>
      </section>
      {account && !account.saved && <div className="notice">{t("saveIntro", lang)} <Link to="/citizen">{t("profile", lang)} →</Link></div>}
      {account?.saved && account.profile.length > 0 && (
        <section className="card stack">
          <h2>{t("savedProfile", lang)}</h2>
          <div className="facts">
            {account.profile.filter((f) => f.attribute !== "applicant_name").map((f) => (
              <div key={f.fact_id} className={`fact ${f.needs_reconfirmation ? "pending" : ""}`}>
                <div><div className="k">{attrLabel(f.attribute, lang)}</div><div className="v">{showValue(f.attribute, f.value, lang)}</div>
                  {f.needs_reconfirmation && <div className="small" role="status"><strong>{t("reconfirm", lang)}</strong></div>}</div>
                <span className="tiny">{f.confirmed_at?.slice(0, 10)}</span>
              </div>
            ))}
          </div>
          <Link className="btn primary" to="/citizen">{t("checkSchemes", lang)} →</Link>
        </section>
      )}
      {versions && versions.length > 1 && (
        <section className="card stack">
          <div className="row spread">
            <h2>{t("whatChangedSince", lang)}</h2>
            <input type="date" value={since} onChange={(e) => setSince(e.target.value)} aria-label={t("whatChangedSince", lang)} />
          </div>
          {changes && changes.length === 0 && <p className="small muted">{t("noChanges", lang)}</p>}
          <ul className="small" style={{ margin: 0, paddingLeft: "1.1rem" }}>
            {changes?.map((c) => (
              <li key={c.scheme_id}>
                <strong>{c.scheme_name}</strong>: {c.before ? <OutcomeBadge outcome={c.before} lang={lang} /> : "—"} → {c.after ? <OutcomeBadge outcome={c.after} lang={lang} /> : "—"}
                <ul style={{ paddingLeft: "1.1rem" }}>{c.reasons.map((r, i) => <li key={i}>{reasonText(r, lang)}</li>)}</ul>
              </li>
            ))}
          </ul>
        </section>
      )}
      {versions && (
        <section className="card stack">
          <h2>{t("history", lang)} <span className="chip">{versions.length}</span></h2>
          {versions.map((v) => (
            <details key={v.version_id}>
              <summary className="small">{v.created_at.replace("T", " ").slice(0, 16)} · {Object.entries(v.counts).map(([o, n]) => `${n} ${o}`).join(" · ")}</summary>
              <div className="tiny mono">{v.bundle_version} · facts {v.fact_ids.join(", ")}</div>
              <ul className="small" style={{ paddingLeft: "1.1rem" }}>
                {v.outcomes.map((o) => <li key={o.rule_id}>{o.scheme_name} <span className="mono tiny">{o.rule_id} v{o.rule_version}</span> <OutcomeBadge outcome={o.outcome} lang={lang} /></li>)}
              </ul>
            </details>
          ))}
        </section>
      )}
      {signedIn && <AttachCode onDone={load} />}
      <ConsentNotice />
      <RetentionNote />
      {citizen && (
        <section className="card stack">
          <h2>{t("withdrawConsent", lang)} · {t("deleteAccount", lang)}</h2>
          <p className="small">{t("deleteConfirm", lang)}</p>
          <div className="row">
            <input type="text" value={confirmText} onChange={(e) => setConfirmText(e.target.value)} aria-label="DELETE" style={{ width: "10rem" }} />
            <button className="btn danger" disabled={confirmText !== "DELETE" || pendingCase} onClick={() => remove()}>{t("deleteAccount", lang)}</button>
          </div>
          {pendingCase && (
            <div className="notice stack" role="alertdialog" aria-live="assertive" aria-label={t("deleteAccount", lang)}>
              <p style={{ margin: 0 }}><strong>{t("pendingCaseWarning", lang)}</strong></p>
              <div className="row">
                <button className="btn danger" onClick={() => remove(true)}>{t("deleteAnyway", lang)}</button>
                <button className="btn" autoFocus onClick={() => { setPendingCase(false); setConfirmText(""); }}>{t("keepAccount", lang)}</button>
              </div>
            </div>
          )}
        </section>
      )}
    </div>
  );
}
