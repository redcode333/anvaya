// Supabase is used in the browser for sign-in ONLY (anonymous sessions, email OTP, Google, staff email + password).
// It never reads tables or storage: every data request goes to the Flask API with the access token, which the
// server verifies itself. Only the project URL and the publishable key are in the bundle.
import { createClient, type SupabaseClient } from "@supabase/supabase-js";
import { setTokenProvider } from "./api";

const url = import.meta.env.VITE_SUPABASE_URL as string | undefined;
const key = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY as string | undefined;

// Kiosks keep nothing: their sign-in lives in sessionStorage (gone when the browser closes), personal devices keep
// the (anonymous or linked) session in localStorage so a reload does not lose an unsaved passport.
const kiosk = () => { try { return sessionStorage.getItem("anvaya.mode") === "kiosk"; } catch { return false; } };
const store = (): Storage | null => { try { return kiosk() ? sessionStorage : localStorage; } catch { return null; } };
const adaptiveStorage = {
  getItem: (k: string) => store()?.getItem(k) ?? null,
  setItem: (k: string, v: string) => { try { store()?.setItem(k, v); } catch { /* storage blocked */ } },
  removeItem: (k: string) => { try { localStorage.removeItem(k); sessionStorage.removeItem(k); } catch { /* blocked */ } },
};

export const supabase: SupabaseClient | null = url && key
  ? createClient(url, key, { auth: { storage: adaptiveStorage, persistSession: true, autoRefreshToken: true, detectSessionInUrl: true } })
  : null;

export const authConfigured = () => supabase !== null;

setTokenProvider(async () => (supabase ? (await supabase.auth.getSession()).data.session?.access_token ?? null : null));
