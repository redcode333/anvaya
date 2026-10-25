// Supabase is used in the browser for sign-in ONLY (anonymous sessions, email OTP, Google, staff email + password +
// TOTP). It never reads tables or storage: every data request goes to the Flask API with the access token, which the
// server verifies itself. Only the project URL, the publishable key and the Turnstile site key are in the bundle.
import { createClient, type SupabaseClient } from "@supabase/supabase-js";
import { setTokenProvider } from "./api";
import { authStorage } from "./authStorage";

const url = import.meta.env.VITE_SUPABASE_URL as string | undefined;
const key = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY as string | undefined;

/** Cloudflare Turnstile site key; unset (local dev) = no widget, sign-in requests go without a captchaToken. */
export let turnstileSiteKey = (import.meta.env.VITE_TURNSTILE_SITE_KEY as string | undefined) || "";

/** When the key was not baked into the build, ask the server (GET /api/config): setting the variable on the server alone
 *  is then enough, with no rebuild. Call once before the app renders. */
export async function loadRuntimeTurnstileKey(): Promise<void> {
  if (!turnstileSiteKey) {
    try {
      const r = await fetch("/api/config", { headers: { Accept: "application/json" } });
      if (r.ok) turnstileSiteKey = ((await r.json()).turnstile_site_key as string | null) || "";
    } catch { /* offline or no server: sign-in runs without the widget */ }
  }
  if (!turnstileSiteKey) console.warn("anvaya: no Turnstile site key (build or server); sign-in runs without the CAPTCHA (local dev only).");
}

// flowType "pkce": an OAuth redirect (Google) returns a one-time code in the query, never tokens in the URL fragment.
export const supabase: SupabaseClient | null = url && key
  ? createClient(url, key, { auth: { storage: authStorage, persistSession: true, autoRefreshToken: true, detectSessionInUrl: true, flowType: "pkce" } })
  : null;

export const authConfigured = () => supabase !== null;

setTokenProvider(async () => (supabase ? (await supabase.auth.getSession()).data.session?.access_token ?? null : null));
