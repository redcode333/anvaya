// Voice input: VerbX STT (via backend adapter) → browser Web Speech API → text only.
// Read-aloud: VerbX TTS (cached on the server) when configured, else browser speech; a slow or failed VerbX clip
// leaves the text on screen with an "audio unavailable" note. Text input is always available.
import { api, ApiError } from "./api";
import { LANGS, type Lang } from "./i18n";

export type Provider = "verbx" | "browser" | "none";

let verbx: boolean | null = null;
let verbxDown = false;  // VerbX failed this visit: use browser speech from now on
export const verbxFailedOver = () => verbxDown;

/** Records a VerbX STT failure; returns true when VerbX itself is down (not just an empty clip) and browser
 *  speech should take over. */
export function noteVerbxError(e: unknown): boolean {
  // An empty or unintelligible clip is the speaker's problem (try again), not a VerbX outage.
  const down = !(e instanceof ApiError && (e.details?.reason === "no_speech" || e.details?.reason === "unintelligible"));
  if (down) verbxDown = true;
  return down;
}
export async function voiceProvider(): Promise<Provider> {
  if (verbx === null) {
    // A failed status call (backend still starting, flaky network) is not "VerbX is off": leave it unknown so the next
    // check asks again, and use browser speech meanwhile.
    try { verbx = (await api<{ verbx_configured: boolean }>("/voice/status")).verbx_configured; } catch { /* retry next time */ }
  }
  if (verbx && !verbxDown) return "verbx";
  const w = window as any;
  return w.SpeechRecognition || w.webkitSpeechRecognition ? "browser" : "none";
}

const speechCode = (l: Lang) => LANGS.find((x) => x.code === l)!.speech;

export type Recorder = { stop: () => void };

export function listen(provider: Provider, sessionId: string, lang: Lang,
  onText: (text: string) => void, onError: (msg: string) => void, onEnd: () => void): Recorder | null {
  if (provider === "browser") {
    const w = window as any;
    const Rec = w.SpeechRecognition || w.webkitSpeechRecognition;
    const rec = new Rec();
    rec.lang = speechCode(lang);
    rec.interimResults = false;
    rec.onresult = (e: any) => {
      const said = Array.from(e.results as ArrayLike<any>).map((r) => r[0].transcript).join(" ").trim();
      if (said) onText(said);
    };
    rec.onerror = (e: any) => {
      if (e.error === "aborted") return;
      onError(e.error === "no-speech" ? "I did not hear anything. Tap the mic and try again, or type."
        : e.error === "not-allowed" || e.error === "service-not-allowed" ? "Microphone permission is blocked. Allow it in the browser, or type."
        : `Browser speech error: ${e.error}. Please type instead.`);
    };
    rec.onend = onEnd;
    try { rec.start(); } catch { onError("Could not start the microphone. Please try again or type."); onEnd(); return null; }
    return { stop: () => { try { rec.stop(); } catch { /* already stopped */ } } };
  }
  if (provider === "verbx") {
    let mr: MediaRecorder | null = null;
    let cancelled = false;  // stop tapped before the microphone permission came back
    const chunks: BlobPart[] = [];
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      onError("Microphone not available. Please type instead."); onEnd(); return null;
    }
    navigator.mediaDevices.getUserMedia({ audio: true }).then((stream) => {
      if (cancelled) { stream.getTracks().forEach((t) => t.stop()); onEnd(); return; }
      mr = new MediaRecorder(stream);
      mr.ondataavailable = (e) => chunks.push(e.data);
      mr.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        if (!chunks.length) { onError("Nothing was recorded. Tap the mic and try again, or type."); onEnd(); return; }
        const fd = new FormData();
        fd.append("audio", new Blob(chunks, { type: mr!.mimeType }), "speech.webm");
        fd.append("language", lang);
        try {
          const r = await api<{ transcript: string }>(`/sessions/${sessionId}/voice/transcribe`, { body: fd });
          onText(r.transcript);
        } catch (e: any) {
          const serviceDown = noteVerbxError(e);
          const w = window as any;
          onError(serviceDown && (w.SpeechRecognition || w.webkitSpeechRecognition)
            ? `${e.message} Switched to browser speech — tap the mic again.` : e.message);
        }
        onEnd();
      };
      mr.start();
    }).catch(() => { onError("Microphone not available. Please type instead."); onEnd(); });
    return { stop: () => { cancelled = true; if (mr?.state === "recording") mr.stop(); } };
  }
  onError("Voice input is not available on this device. Please type.");
  onEnd();
  return null;
}

// Read-aloud never holds up the UI: callers show the text first and call speak() without awaiting it. Text is read
// sentence by sentence (the backend caches each sentence; fixed prompts are prerendered), all sentences are requested
// at once and played in order. Any sentence not ready within TTS_WAIT_MS, or failing, ends playback with
// "unavailable" so the caller can show a small "audio unavailable" note next to the text.
export const TTS_WAIT_MS = 8000;
export type SpeakResult = "verbx" | "browser" | "browser (no native voice for this language — may sound accented)"
  | "unavailable" | "cancelled" | "none";

// Whether anything is being read aloud right now, so any page can show a Stop control (see ListenControls.tsx).
let speakingNow = false;
const speakingSubs = new Set<() => void>();
const setSpeaking = (v: boolean) => { if (speakingNow !== v) { speakingNow = v; speakingSubs.forEach((f) => f()); } };
export const isSpeaking = () => speakingNow;
export function subscribeSpeaking(f: () => void) { speakingSubs.add(f); return () => { speakingSubs.delete(f); }; }

let playId = 0;
let playing: HTMLAudioElement | null = null;
let resolvePlay: ((ok: boolean) => void) | null = null;  // lets stopSpeaking() end a clip that will never fire "ended"
let pendingSpeak = 0;                                     // speak() calls still fetching or playing clips
let aborts: AbortController[] = [];

/** True while the bot is audibly speaking (or about to): the hands-free call raises its microphone bar for this. */
export function botSpeaking(): boolean {
  return !!playing || pendingSpeak > 0 || (typeof window !== "undefined" && "speechSynthesis" in window && speechSynthesis.speaking);
}

export function stopSpeaking() {
  playId++;
  resolvePlay?.(false);
  resolvePlay = null;
  aborts.forEach((a) => a.abort());
  aborts = [];
  playing?.pause();
  playing = null;
  if (typeof window !== "undefined" && "speechSynthesis" in window) speechSynthesis.cancel();
  setSpeaking(false);
}

function fetchClip(sessionId: string, text: string, lang: Lang): Promise<string> {
  const ctl = new AbortController();
  aborts.push(ctl);
  const timer = setTimeout(() => ctl.abort(), TTS_WAIT_MS);
  return api<{ audio_base64: string; mime_type: string }>(`/sessions/${sessionId}/voice/speak`,
    { body: { text, language: lang }, signal: ctl.signal })
    .then((r) => `data:${r.mime_type};base64,${r.audio_base64}`)
    .finally(() => clearTimeout(timer));
}

function play(src: string, id: number): Promise<boolean> {
  return new Promise((resolve) => {
    if (id !== playId) return resolve(false);
    const a = new Audio(src);
    playing = a;
    const done = (ok: boolean) => { if (playing === a) playing = null; if (resolvePlay === done) resolvePlay = null; resolve(ok); };
    resolvePlay = done;
    a.onended = () => done(true);
    a.onerror = () => done(false);
    a.play().catch(() => done(false));  // e.g. autoplay blocked
  });
}

export async function speak(provider: Provider, sessionId: string | null, text: string | string[], lang: Lang): Promise<SpeakResult> {
  pendingSpeak++;
  try { return await speakParts(provider, sessionId, text, lang); } finally { pendingSpeak--; }
}

async function speakParts(provider: Provider, sessionId: string | null, text: string | string[], lang: Lang): Promise<SpeakResult> {
  const parts = (Array.isArray(text) ? text : [text]).map((s) => s.trim()).filter(Boolean);
  stopSpeaking();
  const id = playId;
  if (!parts.length) return "none";
  if (provider === "verbx" && sessionId) {
    setSpeaking(true);
    try {
      const clips = parts.map((p) => fetchClip(sessionId, p, lang));
      clips.forEach((c) => c.catch(() => undefined));  // a rejected later clip must not surface as unhandled
      for (const clip of clips) {
        let src: string;
        try { src = await clip; } catch { return id === playId ? "unavailable" : "cancelled"; }
        if (id !== playId) return "cancelled";
        if (!(await play(src, id))) return id === playId ? "unavailable" : "cancelled";
      }
      return "verbx";
    } finally { if (id === playId) setSpeaking(false); }
  }
  if (typeof window !== "undefined" && "speechSynthesis" in window) {
    const u = new SpeechSynthesisUtterance(parts.join(" "));
    u.lang = speechCode(lang);
    const voice = speechSynthesis.getVoices().find((v) => v.lang === u.lang);
    if (voice) u.voice = voice;
    setSpeaking(true);
    u.onend = u.onerror = () => { if (id === playId) setSpeaking(false); };
    speechSynthesis.speak(u);
    return voice ? "browser" : "browser (no native voice for this language — may sound accented)";
  }
  return "none";
}
