import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { ErrorNote } from "../components";
import { useFeatureConfig } from "../featureConfig";
import { ATTR, t } from "../i18n";
import { useApp } from "../state";
import { FeatureOption, IdCardIcon } from "./SignIn";

/** Facts DigiLocker can verify. The Aadhaar number is never requested, stored or shown. */
export type VerifiedFacts = { name?: string; dob?: string; gender?: string };
type Me = { linked: boolean; facts: VerifiedFacts };

/** Read-only rows for DigiLocker-verified facts. To change one, the citizen has to unlink first. */
export function VerifiedFactsView({ facts }: { facts: VerifiedFacts }) {
  const { lang } = useApp();
  const rows: [string, string | undefined][] = [[t("nameLabel", lang), facts.name], [t("dobLabel", lang), facts.dob], [ATTR.gender[lang], facts.gender]];
  return (
    <dl className="verified">
      {rows.map(([k, v]) => (
        <div key={k} data-testid="verified-fact">
          <dt><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><rect x="5" y="11" width="14" height="10" rx="2" /><path d="M8 11V8a4 4 0 0 1 8 0v3" /></svg>{k}</dt>
          <dd>{v ?? "—"}</dd>
        </div>
      ))}
    </dl>
  );
}

function ConfirmUnlink({ onCancel, onConfirm }: { onCancel: () => void; onConfirm: () => void }) {
  const { lang } = useApp();
  const cancel = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    cancel.current?.focus();
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") onCancel(); };
    document.addEventListener("keydown", esc);
    return () => document.removeEventListener("keydown", esc);
  }, [onCancel]);
  return (
    <div className="modal-back">
      <div className="card stack modal" role="dialog" aria-modal="true" aria-labelledby="unlink-t" aria-describedby="unlink-b">
        <h2 id="unlink-t">{t("unlinkTitle", lang)}</h2>
        <p id="unlink-b" className="muted">{t("unlinkBody", lang)}</p>
        <div className="row" style={{ justifyContent: "flex-end" }}>
          <button ref={cancel} type="button" className="btn" onClick={onCancel}>{t("cancel", lang)}</button>
          <button type="button" className="btn danger" onClick={onConfirm}>{t("unlinkConfirm", lang)}</button>
        </div>
      </div>
    </div>
  );
}

export default function Profile() {
  const { lang, mode } = useApp();
  const { loading, config } = useFeatureConfig();
  const [me, setMe] = useState<Me | null>(null);
  const [confirm, setConfirm] = useState(false);
  const [err, setErr] = useState<unknown>(null);
  const dlOn = config.digilocker_status === "on";
  const kiosk = mode === "kiosk";

  // Only ask the backend about a DigiLocker link when the feature is on; otherwise its routes answer 503 anyway.
  useEffect(() => {
    if (loading || !dlOn || kiosk) return;
    api<Me>("/auth/digilocker/me").then(setMe).catch(() => setMe({ linked: false, facts: {} }));
  }, [loading, dlOn, kiosk]);

  const unlink = async () => {
    setConfirm(false); setErr(null);
    try { await api("/auth/digilocker/link", { method: "DELETE" }); setMe({ linked: false, facts: {} }); } catch (e) { setErr(e); }
  };

  return (
    <div className="signin">
      <h1>{t("profileTitle", lang)}</h1>
      <section className="card stack" aria-labelledby="pf-id">
        <div className="row spread">
          <h2 id="pf-id">{t("identity", lang)}</h2>
          {me?.linked && <span className="chip verified-chip">{t("verifiedChip", lang)}</span>}
        </div>
        {me?.linked ? (
          <>
            <VerifiedFactsView facts={me.facts} />
            <div className="row spread">
              <span className="small muted">{t("lockedNote", lang)}</span>
              <button type="button" className="btn danger" onClick={() => setConfirm(true)}>{t("unlinkDl", lang)}</button>
            </div>
          </>
        ) : (
          <>
            <p className="muted small">{t("noVerifiedYet", lang)}</p>
            {!kiosk && !loading && (
              <FeatureOption id="link-digilocker" status={config.digilocker_status} label={t("linkDl", lang)} icon={(c) => <IdCardIcon color={c} />}
                soonSub={t("dlSoonSub", lang)} onSub={t("linkDlSub", lang)}>
                <a className="opt-btn" href="/api/v1/auth/digilocker/start?intent=link" aria-describedby="link-digilocker-sub">
                  <IdCardIcon color="var(--trust)" /><span className="opt-label">{t("linkDl", lang)}</span>
                </a>
              </FeatureOption>
            )}
          </>
        )}
        <ErrorNote error={err} />
      </section>
      {confirm && <ConfirmUnlink onCancel={() => setConfirm(false)} onConfirm={unlink} />}
    </div>
  );
}
