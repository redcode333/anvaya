// Hands-free conversation: one tap opens the microphone and it stays open, like a phone call. Each time the person
// finishes a sentence it is transcribed and handed to the caller; the bot's reply is spoken; if the person starts
// talking while the bot is speaking, the bot goes quiet at once and listens. A second tap ends the call.
//
// VerbX path: one microphone stream, loudness read 25×/s (see vad.ts), a MediaRecorder segment per sentence (silence-only
// segments are never uploaded). Browser path: continuous Web Speech recognition, restarted whenever the browser ends it.
import { api, ApiError } from "./api";
import { LANGS, type Lang } from "./i18n";
import { botSpeaking, noteVerbxError, stopSpeaking, type Provider } from "./speech";
import { Vad } from "./vad";

export type CallState = "listening" | "hearing" | "thinking" | "speaking";

export type CallHandlers = {
  provider: Provider;
  sessionId: string;
  lang: () => Lang;               // read at each sentence, so a language switch mid-call applies at once
  busy: () => boolean;            // the app is waiting for the server's reply (shown as "thinking")
  onText: (text: string) => void; // one finished sentence, transcribed
  onState: (s: CallState) => void;
  onError: (msg: string) => void;
  onEnd: () => void;              // the call ended, whether by the person, an error or a lost microphone
};
export type Call = { stop: () => void };

const FRAME_MS = 40;
const IDLE_ROTATE_MS = 4000;      // a segment with no speech in it is thrown away and restarted, so none grows without bound
const speechCode = (l: Lang) => LANGS.find((x) => x.code === l)!.speech;

export function callSupported(provider: Provider): boolean {
  if (provider === "verbx") return !!navigator.mediaDevices?.getUserMedia && typeof MediaRecorder !== "undefined";
  if (provider === "browser") { const w = window as any; return !!(w.SpeechRecognition || w.webkitSpeechRecognition); }
  return false;
}

export async function startCall(h: CallHandlers): Promise<Call | null> {
  if (!callSupported(h.provider)) {
    h.onError("Voice input is not available on this device. Please type."); h.onEnd(); return null;
  }
  return h.provider === "verbx" ? startVerbx(h) : startBrowser(h);
}

async function startVerbx(h: CallHandlers): Promise<Call | null> {
  let stream: MediaStream;
  try {
    // Echo cancellation matters most: it keeps the bot's own voice out of the microphone.
    stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
  } catch { h.onError("Microphone not available. Allow it in the browser, or type."); h.onEnd(); return null; }

  const AC = window.AudioContext || (window as any).webkitAudioContext;
  const ctx: AudioContext = new AC();
  void ctx.resume();
  const analyser = ctx.createAnalyser();
  analyser.fftSize = 1024;
  ctx.createMediaStreamSource(stream).connect(analyser);
  const samples = new Float32Array(analyser.fftSize);
  const vad = new Vad();

  type Segment = { rec: MediaRecorder; chunks: BlobPart[]; spoke: boolean; startedAt: number };
  let seg: Segment;
  let stopped = false;
  let transcribing = 0;

  const upload = (blob: Blob) => {
    transcribing++;
    const fd = new FormData();
    fd.append("audio", blob, "speech.webm");
    fd.append("language", h.lang());
    api<{ transcript: string }>(`/sessions/${h.sessionId}/voice/transcribe`, { body: fd })
      .then((r) => { const t = r.transcript?.trim(); if (t && !stopped) h.onText(t); })
      .catch((e: any) => {
        // A clip with no words in it is just the room: stay quiet and keep listening.
        if (e instanceof ApiError && (e.details?.reason === "no_speech" || e.details?.reason === "unintelligible")) return;
        const down = noteVerbxError(e);
        const w = window as any;
        h.onError(down && (w.SpeechRecognition || w.webkitSpeechRecognition)
          ? `${e.message} Switched to browser speech — tap the mic again.` : e.message);
        if (down) stop();
      })
      .finally(() => { transcribing--; });
  };

  const newSegment = (): Segment => {
    const rec = new MediaRecorder(stream);
    const s: Segment = { rec, chunks: [], spoke: false, startedAt: performance.now() };
    rec.ondataavailable = (e) => { if (e.data.size) s.chunks.push(e.data); };
    rec.onstop = () => { if (s.spoke && s.chunks.length && !stopped) upload(new Blob(s.chunks, { type: rec.mimeType })); };
    rec.start();
    return s;
  };
  const rotate = () => {
    const old = seg;
    seg = newSegment();  // the new one starts first, so no audio falls between them
    if (old.rec.state === "recording") old.rec.stop();
  };
  seg = newSegment();

  let last: CallState | null = null;
  const tick = setInterval(() => {
    if (stopped) return;
    analyser.getFloatTimeDomainData(samples);
    let sum = 0;
    for (let i = 0; i < samples.length; i++) sum += samples[i] * samples[i];
    const level = Math.sqrt(sum / samples.length);
    for (const ev of vad.push(level, performance.now(), botSpeaking())) {
      if (ev === "start") seg.spoke = true;
      else if (ev === "barge") stopSpeaking();           // the person talked over the bot: it stops at once
      else if (ev === "end") rotate();                   // a finished sentence goes to the server
      else if (ev === "discard") { seg.spoke = false; rotate(); }
    }
    if (!vad.speaking && !seg.spoke && performance.now() - seg.startedAt > IDLE_ROTATE_MS) rotate();
    const s: CallState = vad.speaking ? "hearing" : botSpeaking() ? "speaking" : transcribing > 0 || h.busy() ? "thinking" : "listening";
    if (s !== last) { last = s; h.onState(s); }
  }, FRAME_MS);

  // The microphone being unplugged or revoked ends the call instead of leaving it silently deaf.
  stream.getAudioTracks().forEach((t) => { t.onended = () => { if (!stopped) { h.onError("The microphone stopped. Tap the mic to start again."); stop(); } }; });

  function stop() {
    if (stopped) return;
    stopped = true;
    clearInterval(tick);
    try { if (seg.rec.state === "recording") seg.rec.stop(); } catch { /* already stopped */ }
    stream.getTracks().forEach((t) => t.stop());
    void ctx.close().catch(() => undefined);
    h.onEnd();
  }
  return { stop };
}

function startBrowser(h: CallHandlers): Call | null {
  const w = window as any;
  const Rec = w.SpeechRecognition || w.webkitSpeechRecognition;
  let stopped = false;
  let rec: any = null;
  let last: CallState | null = null;
  let heardAt = 0;

  const begin = () => {
    rec = new Rec();
    rec.lang = speechCode(h.lang());
    rec.continuous = true;
    rec.interimResults = true;
    rec.onresult = (e: any) => {
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const r = e.results[i];
        const t = String(r[0].transcript || "").trim();
        if (!t) continue;
        heardAt = performance.now();
        if (botSpeaking()) stopSpeaking();  // any words while the bot speaks: it goes quiet
        if (r.isFinal) h.onText(t);
      }
    };
    rec.onerror = (e: any) => {
      if (e.error === "no-speech" || e.error === "aborted") return;  // normal in a long call; onend restarts it
      if (e.error === "not-allowed" || e.error === "service-not-allowed") {
        h.onError("Microphone permission is blocked. Allow it in the browser, or type."); stop();
      } else h.onError(`Browser speech error: ${e.error}. Please type instead.`);
    };
    // The browser ends a recognition session every so often; start the next one at once.
    rec.onend = () => { if (!stopped) setTimeout(() => { if (!stopped) try { begin(); } catch { /* retried on the next end */ } }, 250); };
    rec.start();
  };
  try { begin(); } catch { h.onError("Could not start the microphone. Please try again or type."); h.onEnd(); return null; }

  const tick = setInterval(() => {
    const s: CallState = performance.now() - heardAt < 800 ? "hearing" : botSpeaking() ? "speaking" : h.busy() ? "thinking" : "listening";
    if (s !== last) { last = s; h.onState(s); }
  }, 150);

  function stop() {
    if (stopped) return;
    stopped = true;
    clearInterval(tick);
    try { rec?.stop(); } catch { /* already stopped */ }
    h.onEnd();
  }
  return { stop };
}
