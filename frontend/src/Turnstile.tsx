// Cloudflare Turnstile: the token goes to Supabase as captchaToken (anonymous sign-in, email OTP, staff password
// sign-in) and Supabase verifies it server-side. A token is single use: after each attempt call reset().
// Without VITE_TURNSTILE_SITE_KEY (local dev) nothing is rendered and the token stays null.
import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react";
import { turnstileSiteKey } from "./auth";

declare global {
  interface Window {
    turnstile?: {
      render: (el: HTMLElement, opts: Record<string, unknown>) => string;
      reset: (id?: string) => void;
      remove: (id?: string) => void;
    };
  }
}

const SCRIPT = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";
let loading: Promise<void> | null = null;
function loadScript(): Promise<void> {
  if (window.turnstile) return Promise.resolve();
  loading ??= new Promise((resolve, reject) => {
    const s = Object.assign(document.createElement("script"), { src: SCRIPT, async: true, defer: true });
    s.onload = () => resolve();
    s.onerror = () => { loading = null; reject(new Error("turnstile")); };
    document.head.appendChild(s);
  });
  return loading;
}

export const captchaEnabled = () => !!turnstileSiteKey;
export type TurnstileHandle = { reset: () => void };
/** off: no site key in this build · checking: Cloudflare is deciding (usually invisible) · challenge: it needs the visitor · passed · failed */
export type CaptchaStatus = "off" | "checking" | "challenge" | "passed" | "failed";

const STATUS_TEXT: Record<CaptchaStatus, Record<"en" | "hi" | "te", string>> = {
  off: { en: "Security check (Cloudflare Turnstile) is not enabled in this build.", hi: "सुरक्षा जाँच (Cloudflare Turnstile) इस बिल्ड में चालू नहीं है।", te: "భద్రతా తనిఖీ (Cloudflare Turnstile) ఈ బిల్డ్‌లో ఆన్‌లో లేదు." },
  checking: { en: "Security check in progress…", hi: "सुरक्षा जाँच चल रही है…", te: "భద్రతా తనిఖీ జరుగుతోంది…" },
  challenge: { en: "Please complete the security check above.", hi: "कृपया ऊपर की सुरक्षा जाँच पूरी कीजिए।", te: "దయచేసి పైన ఉన్న భద్రతా తనిఖీని పూర్తి చేయండి." },
  passed: { en: "Security check passed", hi: "सुरक्षा जाँच पूरी हुई", te: "భద్రతా తనిఖీ పూర్తయింది" },
  failed: { en: "The security check could not finish. Check your connection and try again.", hi: "सुरक्षा जाँच पूरी नहीं हो सकी। कनेक्शन जाँचकर फिर कोशिश कीजिए।", te: "భద్రతా తనిఖీ పూర్తి కాలేదు. కనెక్షన్ చూసి మళ్ళీ ప్రయత్నించండి." },
};
const RETRY = { en: "Try again", hi: "फिर कोशिश करें", te: "మళ్ళీ ప్రయత్నించండి" };
const textLang = (l?: string) => (l === "hi" || l === "te" ? l : "en");

export const Turnstile = forwardRef<TurnstileHandle, { onToken: (token: string | null) => void; onStatus?: (s: CaptchaStatus) => void; lang?: string }>(
  function Turnstile({ onToken, onStatus, lang }, ref) {
    const box = useRef<HTMLDivElement>(null);
    const widget = useRef<string | null>(null);
    const status = (s: CaptchaStatus) => onStatus?.(s);
    useImperativeHandle(ref, () => ({ reset: () => { onToken(null); status("checking"); if (widget.current) window.turnstile?.reset(widget.current); } }));
    useEffect(() => {
      if (!turnstileSiteKey) return;
      let cancelled = false;
      loadScript().then(() => {
        if (cancelled || !box.current || !window.turnstile) return;
        widget.current = window.turnstile.render(box.current, {
          sitekey: turnstileSiteKey, language: lang || "auto", appearance: "interaction-only",
          callback: (t: string) => { onToken(t); status("passed"); },
          "expired-callback": () => { onToken(null); status("checking"); },
          "error-callback": () => { onToken(null); status("failed"); },
          "before-interactive-callback": () => status("challenge"),  // Cloudflare decided this visitor must act: the widget is shown
          "after-interactive-callback": () => status("checking"),
        });
      }).catch(() => { onToken(null); status("failed"); });
      return () => { cancelled = true; if (widget.current) window.turnstile?.remove(widget.current); widget.current = null; };
    }, []); // eslint-disable-line react-hooks/exhaustive-deps
    if (!turnstileSiteKey) return null;
    return <div ref={box} className="turnstile" aria-label="Security check" />;
  });

/** The line that makes the check visible even when Cloudflare needs no action from the visitor. */
export function CaptchaStatusLine({ status, lang, onRetry }: { status: CaptchaStatus; lang?: string; onRetry?: () => void }) {
  const l = textLang(lang);
  return (
    <p className={`cap-status cap-${status}`} role="status" aria-live="polite" data-testid="captcha-status">
      <span className="cap-dot" aria-hidden="true">{status === "passed" ? "✓" : status === "failed" ? "!" : status === "off" ? "–" : ""}</span>
      <span>{STATUS_TEXT[status][l]}</span>
      {status === "failed" && onRetry && <button type="button" className="btn small" onClick={onRetry}>{RETRY[l]}</button>}
    </p>
  );
}

/** { widget, token, ready, used, status } — `ready` is true once a token exists (always true without a site key); call
 *  used() after the request that consumed the token. `widget` is the Cloudflare widget (invisible unless it needs the
 *  visitor) followed by a status line, so the check is always visible: in progress, passed, failed (with a retry), or off. */
export function useCaptcha(lang?: string) {
  const [token, setToken] = useState<string | null>(null);
  const [status, setStatus] = useState<CaptchaStatus>(captchaEnabled() ? "checking" : "off");
  const ref = useRef<TurnstileHandle>(null);
  const widget = (
    <div className="captcha">
      <Turnstile ref={ref} onToken={setToken} onStatus={setStatus} lang={lang} />
      <CaptchaStatusLine status={status} lang={lang} onRetry={() => ref.current?.reset()} />
    </div>
  );
  return { widget, token, status, ready: !captchaEnabled() || !!token, used: () => ref.current?.reset() };
}
