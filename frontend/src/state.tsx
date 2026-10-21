import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { getStaffToken, setStaffToken } from "./api";
import type { Lang } from "./i18n";

type Mode = "personal" | "kiosk";
type Staff = { username: string; role: string; display_name: string } | null;

type Ctx = {
  lang: Lang; setLang: (l: Lang) => void;
  mode: Mode; setMode: (m: Mode) => void;
  sessionId: string | null; setSessionId: (s: string | null) => void;
  staff: Staff; setStaff: (s: Staff, token?: string | null) => void;
  online: boolean; simulateOffline: boolean; setSimulateOffline: (b: boolean) => void;
  resetCitizen: () => void;
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
  const [staff, setStaffS] = useState<Staff>(() => { try { return JSON.parse(ss.get("anvaya.staff") || "null"); } catch { return null; } });
  const [netOnline, setNetOnline] = useState(navigator.onLine);
  const [simulateOffline, setSimulateOffline] = useState(false);

  useEffect(() => {
    const on = () => setNetOnline(true), off = () => setNetOnline(false);
    window.addEventListener("online", on); window.addEventListener("offline", off);
    return () => { window.removeEventListener("online", on); window.removeEventListener("offline", off); };
  }, []);
  useEffect(() => { document.documentElement.lang = lang; }, [lang]);
  useEffect(() => { document.body.classList.toggle("kiosk", mode === "kiosk"); }, [mode]);

  const setLang = (l: Lang) => { setLangS(l); ss.set("anvaya.lang", l); };
  const setMode = (m: Mode) => { setModeS(m); ss.set("anvaya.mode", m); };
  const setSessionId = (s: string | null) => { setSid(s); ss.set("anvaya.session", s); };
  const setStaff = (s: Staff, token?: string | null) => {
    setStaffS(s); ss.set("anvaya.staff", s ? JSON.stringify(s) : null);
    if (token !== undefined) setStaffToken(token);
  };
  useEffect(() => { if (staff && !getStaffToken()) setStaff(null); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const resetCitizen = useCallback(() => {
    setSessionId(null);
    try { Object.keys(sessionStorage).filter((k) => k.startsWith("anvaya.citizen.")).forEach((k) => sessionStorage.removeItem(k)); } catch { /* */ }
  }, []);

  const value = useMemo(() => ({
    lang, setLang, mode, setMode, sessionId, setSessionId, staff, setStaff,
    online: netOnline && !simulateOffline, simulateOffline, setSimulateOffline, resetCitizen,
  }), [lang, mode, sessionId, staff, netOnline, simulateOffline, resetCitizen]);
  return <AppCtx.Provider value={value}>{children}</AppCtx.Provider>;
}
