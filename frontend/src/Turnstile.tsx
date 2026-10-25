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

export const Turnstile = forwardRef<TurnstileHandle, { onToken: (token: string | null) => void; lang?: string }>(
  function Turnstile({ onToken, lang }, ref) {
    const box = useRef<HTMLDivElement>(null);
    const widget = useRef<string | null>(null);
    useImperativeHandle(ref, () => ({ reset: () => { onToken(null); if (widget.current) window.turnstile?.reset(widget.current); } }));
    useEffect(() => {
      if (!turnstileSiteKey) return;
      let cancelled = false;
      loadScript().then(() => {
        if (cancelled || !box.current || !window.turnstile) return;
        widget.current = window.turnstile.render(box.current, {
          sitekey: turnstileSiteKey, language: lang || "auto", appearance: "interaction-only",
          callback: (t: string) => onToken(t), "expired-callback": () => onToken(null), "error-callback": () => onToken(null),
        });
      }).catch(() => onToken(null));
      return () => { cancelled = true; if (widget.current) window.turnstile?.remove(widget.current); widget.current = null; };
    }, []); // eslint-disable-line react-hooks/exhaustive-deps
    if (!turnstileSiteKey) return null;
    return <div ref={box} className="turnstile" aria-label="Security check" />;
  });

/** { widget, token, ready, used } — `ready` is true once a token exists (always true without a site key); call
 *  used() after the request that consumed the token. */
export function useCaptcha(lang?: string) {
  const [token, setToken] = useState<string | null>(null);
  const ref = useRef<TurnstileHandle>(null);
  const widget = <Turnstile ref={ref} onToken={setToken} lang={lang} />;
  return { widget, token, ready: !captchaEnabled() || !!token, used: () => ref.current?.reset() };
}
