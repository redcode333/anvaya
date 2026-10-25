import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, ApiError } from "../api";
import { t, type Key } from "../i18n";
import { useApp } from "../state";

export type CallbackState = "loading" | "cancelled" | "invalid" | "conflict" | "unavailable";

/** Maps the provider redirect (?error / ?code&state) and our backend's answer to one screen state. */
export function stateForError(e: unknown): CallbackState {
  if (e instanceof ApiError) {
    if (e.status === 409) return "conflict";
    if (e.status === 400 || e.status === 401 || e.status === 410 || /STATE|CODE|EXPIRED|INVALID/.test(e.code)) return "invalid";
  }
  return "unavailable"; // 5xx, 501, 503 FEATURE_NOT_AVAILABLE, network
}

const COPY: Record<Exclude<CallbackState, "loading">, [Key, Key]> = {
  cancelled: ["cbCancelled", "cbCancelledSub"],
  invalid: ["cbInvalid", "cbInvalidSub"],
  conflict: ["cbConflict", "cbConflictSub"],
  unavailable: ["cbUnavailable", "cbUnavailableSub"],
};

export default function DigiLockerCallback() {
  const { lang } = useApp();
  const nav = useNavigate();
  // Read the redirect once (before the URL is cleaned) and send the one-time code at most once, even when React
  // StrictMode runs effects twice in development.
  const [params] = useState(() => {
    const q = new URLSearchParams(window.location.search);
    return { error: q.get("error"), code: q.get("code"), st: q.get("state") };
  });
  const initial: CallbackState = params.error ? (params.error === "access_denied" ? "cancelled" : "invalid")
    : !params.code || !params.st ? "invalid" : "loading";
  const [state, setState] = useState<CallbackState>(initial);
  const req = useRef<Promise<unknown> | null>(null);

  useEffect(() => {
    // Never leave the one-time code and state in the address bar or history.
    if (window.location.search) window.history.replaceState(null, "", window.location.pathname);
    if (initial !== "loading" || !params.code || !params.st) return;
    let live = true;
    if (!req.current) req.current = api(`/auth/digilocker/callback?${new URLSearchParams({ code: params.code, state: params.st })}`);
    req.current
      .then(() => { if (live) nav("/profile", { replace: true }); })
      .catch((e) => { if (live) setState(stateForError(e)); });
    return () => { live = false; };
  }, [nav, params, initial]);

  return (
    <div className="signin">
      <div className="card stack cb" role="status" aria-live="polite" data-state={state}>
        {state === "loading" ? (
          <>
            <span className="spin-ring cb-spin" aria-hidden="true" />
            <h1>{t("cbLoading", lang)}</h1>
            <p className="muted">{t("cbLoadingSub", lang)}</p>
          </>
        ) : (
          <>
            <h1>{t(COPY[state][0], lang)}</h1>
            <p className="muted">{t(COPY[state][1], lang)}</p>
            <div className="row">
              <Link className="btn primary" to="/signin">{t("tryAgain", lang)}</Link>
              <Link className="btn" to="/signin">{t("anotherWay", lang)}</Link>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
