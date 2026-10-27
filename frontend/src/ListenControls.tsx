import { useState, useSyncExternalStore, type ReactNode } from "react";
import { copyText } from "./clipboard";
import { t } from "./i18n";
import { isSpeaking, stopSpeaking, subscribeSpeaking } from "./speech";
import { useApp } from "./state";

/** True while anything is being read aloud (the chat, a summary, a code, the steps). */
export const useSpeaking = () => useSyncExternalStore(subscribeSpeaking, isSpeaking, () => false);

/** A read-aloud button that turns into *Stop* while audio plays, so the citizen can cut it off whenever they like. */
export function ListenButton({ label, onPlay, className = "btn" }: { label: ReactNode; onPlay: () => void | Promise<unknown>; className?: string }) {
  const { lang } = useApp();
  const speaking = useSpeaking();
  return (
    <button type="button" className={`${className}${speaking ? " is-stop" : ""}`} aria-pressed={speaking}
      onClick={() => { if (speaking) stopSpeaking(); else void onPlay(); }}>
      {speaking ? <>⏹ {t("stopListening", lang)}</> : <>🔊 {label}</>}
    </button>
  );
}

/** A floating Stop while audio plays on any page (a chat reply read out at a kiosk, a spoken code): it is the same
 *  control everywhere, and it disappears when the audio ends. */
export function StopAudioPill() {
  const { lang } = useApp();
  const speaking = useSpeaking();
  if (!speaking) return null;
  return (
    <button type="button" className="stop-pill" onClick={() => stopSpeaking()} aria-label={t("stopListening", lang)}>
      <span className="stop-bars" aria-hidden="true"><i /><i /><i /></span>⏹ {t("stopListening", lang)}
    </button>
  );
}

/** Copies `text` and says so for a moment ("Copied ✓"). */
export function CopyButton({ text, label, className = "btn" }: { text: string; label?: string; className?: string }) {
  const { lang } = useApp();
  const [done, setDone] = useState<"ok" | "fail" | null>(null);
  const copy = async () => {
    setDone((await copyText(text)) ? "ok" : "fail");
    setTimeout(() => setDone(null), 1800);
  };
  return (
    <button type="button" className={className} onClick={copy} aria-live="polite">
      {done === "ok" ? `✓ ${t("copied", lang)}` : done === "fail" ? t("copyFailed", lang) : `⧉ ${label ?? t("copy", lang)}`}
    </button>
  );
}
