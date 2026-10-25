import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api } from "./api";
import { finishPendingConsent, type StaffUser } from "./account";
import { supabase } from "./auth";
import type { Lang } from "./i18n";
import { stopSpeaking } from "./speech";

type Mode = "personal" | "kiosk";
type Staff = StaffUser | null;
export type Citizen = { user_id: string; is_anonymous: boolean; email: string | null } | null;
export type AuthConfig = {
  supabase_configured: boolean; google_enabled: boolean; kiosk_idle_seconds: number; kiosk_warning_seconds: number;
  retention: { unsaved_hours: number; passport_days: number; stale_fact_days: number; consent_version: string };
};

type Ctx = {
  lang: Lang; setLang: (l: Lang) => void;
  mode: Mode; setMode: (m: Mode) => void;
  sessionId: string | null; setSessionId: (s: string | null) => void;
  staff: Staff; citizen: Citizen; refreshAuth: () => Promise<void>; signOut: () => Promise<void>;
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

export function AppProvider({ children }: { children: ReactNode }) {
  const [lang, setLangS] = useState<Lang>((ss.get("anvaya.lang") as Lang) || "te");
  const [mode, setModeS] = useState<Mode>((ss.get("anvaya.mode") as Mode) || "personal");
  const [sessionId, setSid] = useState<string | null>(ss.get("anvaya.session"));
  const [staff, setStaff] = useState<Staff>(null);
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
  useEffect(() => { api<AuthConfig>("/auth/config", { auth: false }).then(setConfig).catch(() => undefined); }, []);

  // Who is signed in comes from the server (it verifies the token and reads the role from app_metadata).
  const refreshAuth = useCallback(async () => {
    if (!supabase) { setStaff(null); setCitizen(null); return; }
    const { data } = await supabase.auth.getSession();
    if (!data.session) { setStaff(null); setCitizen(null); return; }
    try {
      const me = await api<{ user?: StaffUser; citizen?: Citizen }>("/auth/me");
      setStaff(me.user ?? null); setCitizen(me.citizen ?? null);
    } catch { setStaff(null); setCitizen(null); }
  }, []);
  useEffect(() => {
    if (!supabase) return;
    refreshAuth().then(() => finishPendingConsent(supabase!.auth as any).catch(() => false));
    const { data } = supabase.auth.onAuthStateChange((event) => {
      if (event === "SIGNED_IN" || event === "SIGNED_OUT" || event === "USER_UPDATED") setTimeout(() => { refreshAuth(); }, 0);
    });
    return () => data.subscription.unsubscribe();
  }, [refreshAuth]);
  const signOut = useCallback(async () => {
    if (supabase) await supabase.auth.signOut({ scope: "local" });
    setStaff(null); setCitizen(null);
  }, []);

  const setLang = (l: Lang) => { setLangS(l); ss.set("anvaya.lang", l); };
  const setMode = (m: Mode) => { setModeS(m); ss.set("anvaya.mode", m); };
  const setSessionId = useCallback((s: string | null) => { setSid(s); ss.set("anvaya.session", s); }, []);

  const resetCitizen = useCallback(() => {
    setSessionId(null);
    try { Object.keys(sessionStorage).filter((k) => k.startsWith("anvaya.citizen.")).forEach((k) => sessionStorage.removeItem(k)); } catch { /* */ }
  }, [setSessionId]);

  // End session (button or kiosk idle timeout): the server deletes everything nobody consented to keep.
  const endCitizenSession = useCallback(async (reason: "user" | "idle" = "user") => {
    stopSpeaking();
    const sid = ss.get("anvaya.session");
    if (sid) await api(`/sessions/${sid}/end`, { body: { reason } }).catch(() => undefined);
    resetCitizen();
  }, [resetCitizen]);

  const value = useMemo(() => ({
    lang, setLang, mode, setMode, sessionId, setSessionId, staff, citizen, refreshAuth, signOut, config,
    online: netOnline && !simulateOffline, simulateOffline, setSimulateOffline, resetCitizen, endCitizenSession,
  }), [lang, mode, sessionId, setSessionId, staff, citizen, refreshAuth, signOut, config, netOnline, simulateOffline, resetCitizen, endCitizenSession]);
  return <AppCtx.Provider value={value}>{children}</AppCtx.Provider>;
}
