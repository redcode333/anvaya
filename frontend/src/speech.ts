// Voice path: VerbX (via backend adapter) → browser Web Speech API → text only.
// The UI always shows which provider is active, and text input is always available.
import { api } from "./api";
import { LANGS, type Lang } from "./i18n";

export type Provider = "verbx" | "browser" | "none";

let verbx: boolean | null = null;
export async function voiceProvider(): Promise<Provider> {
  if (verbx === null) {
    try { verbx = (await api<{ verbx_configured: boolean }>("/voice/status")).verbx_configured; } catch { verbx = false; }
  }
  if (verbx) return "verbx";
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
    rec.onresult = (e: any) => onText(e.results[0][0].transcript);
    rec.onerror = (e: any) => onError(`Browser speech error: ${e.error}. Please type instead.`);
    rec.onend = onEnd;
    rec.start();
    return { stop: () => rec.stop() };
  }
  if (provider === "verbx") {
    let mr: MediaRecorder | null = null;
    const chunks: BlobPart[] = [];
    navigator.mediaDevices.getUserMedia({ audio: true }).then((stream) => {
      mr = new MediaRecorder(stream);
      mr.ondataavailable = (e) => chunks.push(e.data);
      mr.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        const fd = new FormData();
        fd.append("audio", new Blob(chunks, { type: mr!.mimeType }), "speech.webm");
        fd.append("language", lang);
        try {
          const r = await api<{ transcript: string }>(`/sessions/${sessionId}/voice/transcribe`, { body: fd });
          onText(r.transcript);
        } catch (e: any) { onError(e.message); }
        onEnd();
      };
      mr.start();
    }).catch(() => { onError("Microphone not available. Please type instead."); onEnd(); });
    return { stop: () => mr?.state === "recording" && mr.stop() };
  }
  onError("Voice input is not available on this device. Please type.");
  onEnd();
  return null;
}

export async function speak(provider: Provider, sessionId: string | null, text: string, lang: Lang): Promise<string> {
  if (provider === "verbx" && sessionId) {
    try {
      const r = await api<{ audio_base64: string; mime_type: string }>(`/sessions/${sessionId}/voice/speak`, { body: { text, language: lang } });
      await new Audio(`data:${r.mime_type};base64,${r.audio_base64}`).play();
      return "verbx";
    } catch { /* fall through to browser TTS */ }
  }
  if ("speechSynthesis" in window) {
    const u = new SpeechSynthesisUtterance(text);
    u.lang = speechCode(lang);
    const voice = speechSynthesis.getVoices().find((v) => v.lang === u.lang);
    if (voice) u.voice = voice;
    speechSynthesis.cancel();
    speechSynthesis.speak(u);
    return voice ? "browser" : "browser (no native voice for this language — may sound accented)";
  }
  return "none";
}
