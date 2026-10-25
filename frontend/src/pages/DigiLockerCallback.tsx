import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";
import { ErrorNote } from "../components";
import { t } from "../i18n";
import { useApp } from "../state";

/** DIGILOCKER_REDIRECT_URI points here. The code + state are read once, removed from the address bar at once, and
 *  handed to the server, which validates the state, exchanges the code (PKCE) and verifies the ID token. */
export default function DigiLockerCallback() {
  const { lang, config } = useApp();
  const nav = useNavigate();
  const [err, setErr] = useState<unknown>(null);
  const once = useRef(false);
  useEffect(() => {
    if (once.current || !config) return;
    once.current = true;
    const q = new URLSearchParams(window.location.search);
    const code = q.get("code") ?? "", state = q.get("state") ?? "";
    window.history.replaceState(null, "", window.location.pathname);  // never leave the code in history
    if (!config.digilocker_enabled) { setErr({ code: "DIGILOCKER_DISABLED", message: "DigiLocker is not enabled." }); return; }
    if (q.get("error")) { setErr({ code: "DIGILOCKER_DENIED", message: "DigiLocker sign-in was cancelled." }); return; }
    api("/auth/digilocker/callback", { body: { code, state } }).then(() => nav("/citizen")).catch(setErr);
  }, [config, nav]);
  return (
    <div className="card stack" style={{ maxWidth: 520 }}>
      <h2>DigiLocker</h2>
      {!err && <p className="small" role="status">…</p>}
      <ErrorNote error={err} />
      {!!err && <Link to="/citizen">{t("profile", lang)} →</Link>}
    </div>
  );
}
