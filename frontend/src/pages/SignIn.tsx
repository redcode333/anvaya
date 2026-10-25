import { useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { ErrorNote } from "../components";
import { useFeatureConfig, type FeatureStatus } from "../featureConfig";
import { t, type Key } from "../i18n";
import { useApp } from "../state";

export const IdCardIcon = ({ color = "currentColor" }: { color?: string }) => (
  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <rect x="3" y="5" width="18" height="14" rx="2.5" /><circle cx="9" cy="11" r="2.2" /><path d="M5.8 16c.6-1.5 1.8-2.3 3.2-2.3s2.6.8 3.2 2.3" /><path d="M14.5 10.5l1.5 1.5 3-3" />
  </svg>
);
const PhoneIcon = ({ color = "currentColor" }: { color?: string }) => (
  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <rect x="7" y="2.5" width="10" height="19" rx="2.5" /><path d="M11 18.5h2" />
  </svg>
);

/**
 * One sign-in option driven by its runtime status:
 *  on          → a working control
 *  coming_soon → visible but disabled (aria-disabled, no handler, so no request can ever fire) + "Coming soon"
 *  off         → not rendered
 */
export function FeatureOption({ id, status, label, icon, soonSub, onSub, children }: {
  id: string; status: FeatureStatus; label: string; icon: (c?: string) => ReactNode; soonSub: string; onSub: string; children: ReactNode;
}) {
  const { lang } = useApp();
  if (status === "off") return null;
  if (status === "coming_soon") {
    return (
      <div className="opt" data-testid={`opt-${id}`} data-status="coming_soon">
        <button type="button" className="opt-btn soon" aria-disabled="true" aria-describedby={`${id}-sub`}>
          {icon()}<span className="opt-label">{label}</span><span className="opt-badge">{t("comingSoon", lang)}</span>
        </button>
        <span id={`${id}-sub`} className="opt-sub">{soonSub}</span>
      </div>
    );
  }
  return (
    <div className="opt" data-testid={`opt-${id}`} data-status="on">
      {children}
      <span id={`${id}-sub`} className="opt-sub">{onSub}</span>
    </div>
  );
}

function PhoneOtp() {
  const { lang } = useApp();
  const [open, setOpen] = useState(false);
  const [phone, setPhone] = useState("");
  const [err, setErr] = useState<unknown>(null);
  if (!open) {
    return (
      <button type="button" className="opt-btn" aria-describedby="phone-sub" onClick={() => setOpen(true)}>
        <PhoneIcon color="var(--trust)" /><span className="opt-label">{t("phoneButton", lang)}</span>
      </button>
    );
  }
  const send = async (e: React.FormEvent) => {
    e.preventDefault(); setErr(null);
    try { await api("/auth/phone/otp/send", { body: { phone: phone.replace(/\D/g, "") } }); } catch (x) { setErr(x); }
  };
  return (
    <form className="opt-phone" onSubmit={send}>
      <label htmlFor="si-phone">{t("phoneLabel", lang)}</label>
      <div className="row">
        <span className="opt-cc">+91</span>
        <input id="si-phone" type="tel" inputMode="numeric" autoComplete="tel-national" value={phone} onChange={(e) => setPhone(e.target.value)} style={{ flex: "1 1 160px", width: "auto" }} />
        <button className="btn primary" type="submit">{t("sendCode", lang)}</button>
      </div>
      <ErrorNote error={err} />
    </form>
  );
}

export default function SignIn() {
  const { lang, mode, setMode, resetCitizen } = useApp();
  const nav = useNavigate();
  const { loading, config } = useFeatureConfig();
  const kiosk = mode === "kiosk"; // shared device: verified and phone sign-in are never offered
  const tt = (k: Key) => t(k, lang);
  const anonymous = () => { resetCitizen(); setMode(kiosk ? "kiosk" : "personal"); nav(kiosk ? "/kiosk" : "/citizen"); };
  const anyVerified = loading || config.digilocker_status !== "off" || config.phone_otp_status !== "off";

  return (
    <div className="signin">
      <h1>{tt("signInTitle")}</h1>
      <p className="muted">{tt("signInSub")}</p>
      <div className="card stack">
        <button type="button" className="btn primary signin-anon" onClick={anonymous}>{tt("continueAnon")}</button>
      </div>
      {!kiosk && anyVerified && (
        <section className="signin-options" aria-busy={loading} aria-label={tt("orSignIn")}>
          <div className="signin-or"><span />{tt("orSignIn")}<span /></div>
          {loading ? (
            <div aria-hidden="true" data-testid="signin-skeleton">
              <div className="opt"><div className="skel btn-skel" /><div className="skel line-skel" /></div>
              <div className="opt"><div className="skel btn-skel" /><div className="skel line-skel short" /></div>
            </div>
          ) : (
            <>
              <FeatureOption id="digilocker" status={config.digilocker_status} label={tt("dlButton")} icon={(c) => <IdCardIcon color={c} />}
                soonSub={tt("dlSoonSub")} onSub={tt("dlOnSub")}>
                {/* Full-page navigation: the backend starts the OIDC flow and redirects to the provider. */}
                <a className="opt-btn" href="/api/v1/auth/digilocker/start" aria-describedby="digilocker-sub">
                  <IdCardIcon color="var(--trust)" /><span className="opt-label">{tt("dlButton")}</span>
                </a>
              </FeatureOption>
              <FeatureOption id="phone" status={config.phone_otp_status} label={tt("phoneButton")} icon={(c) => <PhoneIcon color={c} />}
                soonSub={tt("phoneSoonSub")} onSub={tt("phoneOnSub")}>
                <PhoneOtp />
              </FeatureOption>
            </>
          )}
        </section>
      )}
      {kiosk && <p className="notice info small" data-testid="kiosk-note">{tt("kioskVerifiedOff")}</p>}
      <p className="notice small">{tt("notApproval")}</p>
    </div>
  );
}
