import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { api, setKioskDeviceProvider, setRevokedHandler } from "./api";
import { finishPendingConsent, signOutEverywhere, type AuthLike, type StaffUser } from "./account";
import { supabase } from "./auth";
import { clearPersistedAuth } from "./authStorage";
import type { Lang } from "./i18n";
import { stopSpeaking } from "./speech";

type Mode = "personal" | "kiosk";
type Staff = StaffUser | null;
export type Citizen = { user_id: string; is_anonymous: boolean; email: string | null; phone?: string | null } | null;
export type AuthConfig = {
  supabase_configured: boolean; google_enabled: boolean; kiosk_idle_seconds: number; kiosk_warning_seconds: number;
  kiosk_max_session_minutes: number; staff_mfa_required: boolean; phone_otp_enabled: boolean; digilocker_enabled: boolean;
  retention: { unsaved_hours: number; passport_days: number; stale_fact_days: number; consent_version: string };
};

type Ctx = {
  lang: Lang; setLang: (l: Lang) => void;
  mode: Mode; setMode: (m: Mode) => void;
  sessionId: string | null; setSessionId: (s: string | null, expiresAt?: string | null) => void;
  sessionExpiresAt: string | null;
  // staff = a staff member whose sign-in passed the TOTP step (aal2); staffPendingMfa = signed in with the password
  // only: every staff API call is refused until the code is verified.
  staff: Staff; staffPendingMfa: Staff; citizen: Citizen; refreshAuth: () => Promise<void>;
  signOut: () => Promise<void>; signOutAll: () => Promise<void>;
  config: AuthConfig | null;
  online: boolean; simulateOffline: boolean; setSimulateOffline: (b: boolean) => void;
  resetCitizen: () => void;
  endCitizenSession: (reason?: "user" | "idle") => Promise<void>;
};

const AppCtx = createContext<Ctx>(null as any);
export const useApp = () => useContext(AppCtx);

const ss = {
  get: (k: string) => { try { return sessionStorage.getItem(k); } catch { return null; } },
  set: (k: string, v: string | null) => { try { v === null ? sessionStorage.removeItem(k) : sessionStorage.setItem(k, v); } catch { /* blocked */ } },
};

/** This kiosk's device id: random, kept in localStorage (it names the device, not a person). Kiosk sessions are
 *  bound to it on the server. */
export function kioskDeviceId(): string {
  try {
    let id = localStorage.getItem("anvaya.kioskDevice");
    if (!id || !/^[A-Za-z0-9_-]{8,64}$/.test(id)) {
      const b = crypto.getRandomValues(new Uint8Array(16));
      id = `KD-${Array.from(b, (x) => x.toString(16).padStart(2, "0")).join("")}`;
      localStorage.setItem("anvaya.kioskDevice", id);
    }
    return id;
  } catch { return "KD-unavailable-device"; }
}

/** Where the citizen session id lives: kiosk = memory only (a reload or a new tab never brings a session back);
 *  personal = sessionStorage (survives a reload of this tab only). */
export function initialSessionId(mode: Mode): string | null {
  if (mode === "kiosk") { ss.set("anvaya.session", null); return null; }
  return ss.get("anvaya.session");
}

export function AppProvider({ children }: { children: ReactNode }) {
  const [lang, setLangS] = useState<Lang>((ss.get("anvaya.lang") as Lang) || "te");
  const [mode, setModeS] = useState<Mode>((ss.get("anvaya.mode") as Mode) || "personal");
  const [sessionId, setSid] = useState<string | null>(() => initialSessionId((ss.get("anvaya.mode") as Mode) || "personal"));
  const [sessionExpiresAt, setExpires] = useState<string | null>(null);
  const sidRef = useRef<string | null>(sessionId);
  const [staff, setStaff] = useState<Staff>(null);
  const [staffPendingMfa, setPending] = useState<Staff>(null);
  const [citizen, setCitizen] = useState<Citizen>(null);
  const [config, setConfig] = useState<AuthConfig | null>(null);
  const [netOnline, setNetOnline] = useState(navigator.onLine);
  const [simulateOffline, setSimulateOffline] = useState(false);

  useEffect(() => {
    const on = () => setNetOnline(true), off = () => setNetOnline(false);
    window.addEventListener("online", on); window.addEventListener("offline", off);
    return () => { window.removeEventListener("online", on); window.removeEventListener("offline", off); };
  }, []);
  useEffect(() => { document.documentElement.lang = lang; }, [lang]);
  useEffect(() => { document.body.classList.toggle("kiosk", mode === "kiosk"); }, [mode]);
  useEffect(() => { setKioskDeviceProvider(() => (mode === "kiosk" ? kioskDeviceId() : null)); }, [mode]);
  useEffect(() => { api<AuthConfig>("/auth/config", { auth: false }).then(setConfig).catch(() => undefined); }, []);

  const clearAuth = useCallback(() => { setStaff(null); setPending(null); setCitizen(null); }, []);
  // Who is signed in comes from the server (it verifies the token and reads the role from app_metadata).
  const refreshAuth = useCallback(async () => {
    if (!supabase) { clearAuth(); return; }
    const { data } = await supabase.auth.getSession();
    if (!data.session) { clearAuth(); return; }
    try {
      const me = await api<{ user?: StaffUser; citizen?: Citizen; mfa_required?: boolean }>("/auth/me");
      setStaff(me.user && !me.mfa_required ? me.user : null);
      setPending(me.user && me.mfa_required ? me.user : null);
      setCitizen(me.citizen ?? null);
    } catch { clearAuth(); }
  }, [clearAuth]);
  useEffect(() => {
    if (!supabase) return;
    setRevokedHandler(() => { supabase!.auth.signOut({ scope: "local" }).finally(clearAuth); });
    refreshAuth().then(() => finishPendingConsent(supabase!.auth as any).catch(() => false));
    const { data } = supabase.auth.onAuthStateChange((event) => {
      if (["SIGNED_IN", "SIGNED_OUT", "USER_UPDATED", "MFA_CHALLENGE_VERIFIED"].includes(event)) setTimeout(() => { refreshAuth(); }, 0);
    });
    return () => data.subscription.unsubscribe();
  }, [refreshAuth, clearAuth]);

  const setLang = (l: Lang) => { setLangS(l); ss.set("anvaya.lang", l); };
  const setMode = (m: Mode) => {
    if (m === "kiosk" && mode !== "kiosk") clearPersistedAuth();  // a kiosk never inherits a personal sign-in
    setModeS(m); ss.set("anvaya.mode", m);
  };
  const setSessionId = useCallback((s: string | null, expiresAt: string | null = null) => {
    sidRef.current = s;
    setSid(s); setExpires(s ? expiresAt : null);
    ss.set("anvaya.session", mode === "kiosk" ? null : s);
  }, [mode]);

  const resetCitizen = useCallback(() => {
    setSessionId(null);
    try { Object.keys(sessionStorage).filter((k) => k.startsWith("anvaya.citizen.")).forEach((k) => sessionStorage.removeItem(k)); } catch { /* */ }
  }, [setSessionId]);

  // End session (button, kiosk idle timeout or the 30-minute limit): the server deletes everything nobody consented
  // to keep, and nothing about it stays in this browser.
  const endCitizenSession = useCallback(async (reason: "user" | "idle" = "user") => {
    stopSpeaking();
    const sid = sidRef.current;
    if (sid) await api(`/sessions/${sid}/end`, { body: { reason } }).catch(() => undefined);
    resetCitizen();
  }, [resetCitizen]);

  const signOut = useCallback(async () => {
    // A kiosk operator signing out ends every citizen session on this device first.
    if (mode === "kiosk" && (staff || staffPendingMfa)) await api("/kiosk/sign-out", { body: {} }).catch(() => undefined);
    if (mode === "kiosk") resetCitizen();
    if (supabase) await supabase.auth.signOut({ scope: "local" });
    clearAuth();
  }, [mode, staff, staffPendingMfa, resetCitizen, clearAuth]);
  const signOutAll = useCallback(async () => {
    if (mode === "kiosk" && staff) await api("/kiosk/sign-out", { body: {} }).catch(() => undefined);
    if (supabase) await signOutEverywhere(supabase.auth as unknown as AuthLike);
    resetCitizen(); clearAuth();
  }, [mode, staff, resetCitizen, clearAuth]);

  const value = useMemo(() => ({
    lang, setLang, mode, setMode, sessionId, setSessionId, sessionExpiresAt, staff, staffPendingMfa, citizen, refreshAuth,
    signOut, signOutAll, config,
    online: netOnline && !simulateOffline, simulateOffline, setSimulateOffline, resetCitizen, endCitizenSession,
  }), [lang, mode, sessionId, setSessionId, sessionExpiresAt, staff, staffPendingMfa, citizen, refreshAuth, signOut, signOutAll, config, netOnline, simulateOffline, resetCitizen, endCitizenSession]); // eslint-disable-line react-hooks/exhaustive-deps
  return <AppCtx.Provider value={value}>{children}</AppCtx.Provider>;
}
