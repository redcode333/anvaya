import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { api } from "../api";
import { formatCode } from "../account";
import { RetentionNote } from "../AccountUI";
import { ErrorNote } from "../components";
import { t } from "../i18n";
import { useApp } from "../state";

/** Passport code + PIN → a new session from the saved profile (works without email, on a phone or at a kiosk). */
export default function Resume() {
  const { lang, mode, setSessionId } = useApp();
  const nav = useNavigate();
  const prefill = (useLocation().state as { code?: string } | null)?.code;  // handed over from Case status when a Passport code was typed there
  const [code, setCode] = useState(prefill ? formatCode(prefill) : ""), [pin, setPin] = useState("");
  const [err, setErr] = useState<unknown>(null);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault(); setErr(null);
    try {
      const r = await api<{ session_id: string; mode: string; expires_at: string }>("/passport/resume", { body: { code, pin, language: lang } });
      setSessionId(r.session_id, r.expires_at);
      nav(r.mode === "kiosk" ? "/kiosk" : "/citizen");
    } catch (x) { setErr(x); }
  };
  return (
    <form className="card stack" style={{ maxWidth: 520 }} onSubmit={submit}>
      <h1>{t("resume", lang)}</h1>
      <label className="field">{t("passportCode", lang)}
        <input type="text" className={mode === "kiosk" ? "code-big mono" : "mono"} value={code} placeholder="PSP-XXXX-XXXX"
          autoComplete="off" autoCapitalize="characters" autoFocus={!!prefill} onChange={(e) => setCode(formatCode(e.target.value))} />
      </label>
      <label className="field">{t("pin", lang)}
        <input type="password" className="pin" inputMode="numeric" maxLength={4} value={pin} autoComplete="off"
          onChange={(e) => setPin(e.target.value.replace(/\D/g, "").slice(0, 4))} />
      </label>
      <ErrorNote error={err} />
      <button className="btn primary" type="submit" disabled={code.length !== 13 || pin.length !== 4}>{t("open", lang)}</button>
      <RetentionNote />
    </form>
  );
}
