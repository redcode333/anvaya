"""VerbX speech + translation adapter, and deterministic localized result summaries.

The VerbX contract (endpoints, headers, payloads, errors) is in docs/vendor/verbx.md; every call here was observed
against the live API. When VerbX is not configured or fails, speech returns VOICE_UNAVAILABLE (speech input falls back to
browser speech, then text; read-aloud shows the text with an "audio unavailable" note) and translation returns
TRANSLATION_UNAVAILABLE (callers show the original text).
Logs carry only endpoint, status, latency and VerbX's correlation id — never text, audio or the API key.
"""
import base64
import hashlib
import logging
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout

import requests
from flask import current_app

from . import i18n, metrics
from .common import ApiError
from .db import get_db, iso

log = logging.getLogger(__name__)

LANGS = ("en", "hi", "te")  # VerbX takes plain ISO 639-1 codes (GET /v1/language/supported)
BATCH_MAX = 50  # BatchTranslateRequest.items maxItems in the VerbX spec


class VerbXError(Exception):
    """A VerbX call failed; the message is a short reason code that is safe to log and show."""


def configured() -> bool:
    c = current_app.config
    return bool(c["VERBX_BASE_URL"] and c["VERBX_API_KEY"])


def status() -> dict:
    on = configured()
    return {"verbx_configured": on, "stt": on, "tts": on, "translation": on, "languages": list(LANGS)}


def _lang(language: str) -> str:
    if language not in LANGS:
        raise ApiError("UNSUPPORTED_LANGUAGE", "Supported languages: en, hi, te.", 422)
    return language


def _post(path: str, payload: dict, timeout: float | None = None, attempts: int = 2) -> requests.Response:
    """POST to VerbX with one retry on 5xx, timeout or connection error. The retry reuses the Idempotency-Key.
    Callers on a latency budget (LLM extraction input) pass their own timeout and attempts=1."""
    if not configured():
        raise VerbXError("not_configured")
    c = current_app.config
    url = c["VERBX_BASE_URL"].rstrip("/") + path
    headers = {"x-api-key": c["VERBX_API_KEY"], "X-VerbX-Shell": c["VERBX_SHELL"],
               "Content-Type": "application/json", "Idempotency-Key": str(uuid.uuid4())}
    for attempt in range(1, attempts + 1):
        t0 = time.perf_counter()
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=timeout or c["VERBX_TIMEOUT_S"])
        except (requests.Timeout, requests.ConnectionError) as e:
            log.warning("verbx %s attempt=%d %s after %dms", path, attempt, type(e).__name__,
                        (time.perf_counter() - t0) * 1000)
            if attempt == attempts:
                raise VerbXError(type(e).__name__.lower())
            continue
        except requests.RequestException as e:
            raise VerbXError(type(e).__name__.lower())
        log.info("verbx %s attempt=%d status=%d %dms correlation=%s", path, attempt, r.status_code,
                 (time.perf_counter() - t0) * 1000, r.headers.get("x-correlation-id"))
        if r.status_code >= 500 and attempt < attempts:
            continue
        if not r.ok:
            raise VerbXError(f"http_{r.status_code}")
        return r
    raise AssertionError("unreachable")


def _json(r: requests.Response):
    try:
        return r.json()
    except ValueError:
        raise VerbXError("invalid_json")


# ---------------------------------------------------------------- speech

def transcribe(audio: bytes, mimetype: str, language: str) -> dict:
    """POST /v1/stt with base64 audio (wav/mp3/ogg/webm). An empty transcript counts as a failure:
    VerbX answers 200 with empty text and degraded=true for unusable audio."""
    lang = _lang(language)
    try:
        body = _json(_post("/v1/stt", {"audio_base64": base64.b64encode(audio).decode(), "language": lang}))
    except VerbXError as e:
        metrics.VOICE.labels("stt", "not_configured" if str(e) == "not_configured" else "error").inc()
        raise ApiError("VOICE_UNAVAILABLE", f"Speech recognition is unavailable ({e}); please type instead.", 503,
                       {"reason": str(e)})
    text = (body.get("text") or "").strip() if isinstance(body, dict) else ""
    if not text:
        metrics.VOICE.labels("stt", "empty").inc()
        raise ApiError("VOICE_UNAVAILABLE", "No speech was recognised in that recording; please try again or type.", 503,
                       {"reason": "no_speech"})
    metrics.VOICE.labels("stt", "ok").inc()
    return {"transcript": text, "language": lang, "provider": "verbx", "confidence": body.get("confidence"),
            "model": body.get("model")}


# Read-aloud audio is cached in the DB (tts_cache) keyed by sha256(text, language, voice). A request waits at most
# TTS_WAIT_S (8 s); a slower synthesis keeps running here and is cached when it finishes, so asking again is instant.
# Identical texts requested together share one VerbX call.
_TTS_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="tts")
_inflight: dict[str, Future] = {}
_inflight_lock = threading.Lock()


def tts_key(text: str, language: str, voice_id: str) -> str:
    return hashlib.sha256("".join((text, language, voice_id)).encode("utf-8")).hexdigest()


def _cached_audio(key: str) -> tuple[str, bytes] | None:
    row = get_db().execute("SELECT mime_type, audio FROM tts_cache WHERE cache_key=?", (key,)).fetchone()
    return (row[0], bytes(row[1])) if row else None


def _store_audio(key: str, lang: str, voice_id: str, mime: str, audio: bytes, ms: int, pinned: bool) -> None:
    db = get_db()
    db.execute("INSERT INTO tts_cache(cache_key, language, voice, mime_type, audio, synth_ms, pinned, created_at)"
               " VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(cache_key) DO UPDATE SET pinned=MAX(pinned, excluded.pinned)",
               (key, lang, voice_id, mime, audio, ms, int(pinned), iso()))
    db.commit()


def _synthesize(text: str, lang: str, voice_id: str) -> tuple[str, bytes, int]:
    """POST /v1/tts; the live API returns raw audio bytes (audio/wav)."""
    t0 = time.perf_counter()
    r = _post("/v1/tts", {"text": text, "options": {"language": lang, "format": "wav", "voice_id": voice_id}})
    mime = r.headers.get("Content-Type", "").split(";")[0]
    if not mime.startswith("audio/") or not r.content:
        raise VerbXError("unexpected_response")
    return mime, r.content, round((time.perf_counter() - t0) * 1000)


def _synth_job(app, key: str, text: str, lang: str, voice_id: str, pinned: bool) -> tuple[str, bytes, int]:
    with app.app_context():
        try:
            mime, audio, ms = _synthesize(text, lang, voice_id)
            _store_audio(key, lang, voice_id, mime, audio, ms, pinned)
            return mime, audio, ms
        finally:
            with _inflight_lock:
                _inflight.pop(key, None)


def _synth_future(key: str, text: str, lang: str, voice_id: str, pinned: bool = False) -> Future:
    with _inflight_lock:
        fut = _inflight.get(key)
        if fut is None:
            fut = _TTS_POOL.submit(_synth_job, current_app._get_current_object(), key, text, lang, voice_id, pinned)
            _inflight[key] = fut
        return fut


def speak(text: str, language: str) -> dict:
    """Audio for one piece of text: from the cache, else from VerbX within TTS_WAIT_S. Raises VOICE_UNAVAILABLE
    (reason not_configured / timeout / VerbX error code); the frontend then shows the text only."""
    lang = _lang(language)
    text = (text or "").strip()
    if not text:
        raise ApiError("INVALID_TEXT", "Nothing to read aloud.", 422)
    c = current_app.config
    key = tts_key(text, lang, c["VERBX_TTS_VOICE"])
    hit = _cached_audio(key)
    if hit:
        metrics.VOICE.labels("tts", "cache_hit").inc()
        return {"audio_base64": base64.b64encode(hit[1]).decode(), "mime_type": hit[0], "provider": "verbx",
                "cached": True}
    if not configured():
        metrics.VOICE.labels("tts", "not_configured").inc()
        raise ApiError("VOICE_UNAVAILABLE", "Speech synthesis is unavailable (not_configured).", 503,
                       {"reason": "not_configured"})
    try:
        mime, audio, ms = _synth_future(key, text, lang, c["VERBX_TTS_VOICE"]).result(timeout=c["TTS_WAIT_S"])
    except FutureTimeout:
        metrics.VOICE.labels("tts", "timeout").inc()
        log.warning("verbx /v1/tts slower than %gs; answering without audio, caching when it finishes", c["TTS_WAIT_S"])
        raise ApiError("VOICE_UNAVAILABLE", f"Speech synthesis took longer than {c['TTS_WAIT_S']:g} s.", 503,
                       {"reason": "timeout"})
    except VerbXError as e:
        metrics.VOICE.labels("tts", "error").inc()
        raise ApiError("VOICE_UNAVAILABLE", f"Speech synthesis is unavailable ({e}).", 503, {"reason": str(e)})
    metrics.VOICE.labels("tts", "ok").inc()
    return {"audio_base64": base64.b64encode(audio).decode(), "mime_type": mime, "provider": "verbx", "cached": False,
            "synth_ms": ms}


class _Pacer:
    """Spaces request starts at least 60/per_minute seconds apart across threads (VerbX rate-limits per key)."""

    def __init__(self, per_minute: float):
        self.gap, self.next, self.lock = 60.0 / per_minute if per_minute > 0 else 0.0, 0.0, threading.Lock()

    def wait(self) -> None:
        with self.lock:
            now = time.monotonic()
            start = max(now, self.next)
            self.next = start + self.gap
        if start > now:
            time.sleep(start - now)


RATE_LIMIT_BACKOFF_S = (10, 20, 40, 60)  # waits before each retry after HTTP 429


def prerender(items: list[tuple[str, str]], concurrency: int = 3, on_result=None, per_minute: float = 40,
              backoff=RATE_LIMIT_BACKOFF_S) -> list[dict]:
    """Synthesize and pin every (text, language) not yet cached; already-cached ones are only pinned. Waits for
    VerbX without the TTS_WAIT_S cap, starts at most `per_minute` requests a minute and retries on HTTP 429 after
    each `backoff` wait. `on_result(row)` is called as each item finishes."""
    c = current_app.config
    app = current_app._get_current_object()
    voice_id = c["VERBX_TTS_VOICE"]
    db = get_db()
    pacer = _Pacer(per_minute)

    def one(text, lang):
        key = tts_key(text, lang, voice_id)
        with app.app_context():
            hit = get_db().execute("SELECT synth_ms FROM tts_cache WHERE cache_key=?", (key,)).fetchone()
        if hit:
            return {"text": text, "language": lang, "result": "cached", "ms": None}
        transient_retry = True
        for wait in (*backoff, None):
            pacer.wait()
            try:
                mime, audio, ms = _synth_job(app, key, text, lang, voice_id, True)
            except VerbXError as e:
                if str(e) == "http_429" and wait is not None:
                    time.sleep(wait)
                    continue
                if transient_retry and not str(e).startswith("http_4"):  # dropped connection, 5xx, timeout
                    transient_retry = False
                    time.sleep(2)
                    continue
                return {"text": text, "language": lang, "result": f"error:{e}", "ms": None}
            return {"text": text, "language": lang, "result": "synthesized", "ms": ms, "bytes": len(audio)}

    out = []
    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        todo = list(dict.fromkeys((t.strip(), _lang(lang)) for t, lang in items if t.strip()))
        for row in pool.map(lambda it: one(*it), todo):
            out.append(row)
            if on_result:
                on_result(row)
    keys = [tts_key(r["text"], r["language"], voice_id) for r in out if r["result"] != "synthesized"]
    db.executemany("UPDATE tts_cache SET pinned=1 WHERE cache_key=?", [(k,) for k in keys])
    db.commit()
    return out


def purge_audio(conn, older_than_hours: float) -> int:
    """Delete live-synthesized clips (they can read back a citizen's details) older than the session lifetime;
    prerendered (pinned) prompts stay."""
    cutoff = iso(datetime.now(timezone.utc) - timedelta(hours=older_than_hours))
    n = conn.execute("DELETE FROM tts_cache WHERE pinned=0 AND created_at < ?", (cutoff,)).rowcount
    conn.commit()
    return n


def cache_stats() -> dict:
    n, pinned = get_db().execute("SELECT COUNT(*), COALESCE(SUM(pinned), 0) FROM tts_cache").fetchone()
    return {"entries": n, "prerendered": pinned}


# ---------------------------------------------------------------- translation

def _translated(body) -> dict:
    if not isinstance(body, dict) or body.get("translation_failed") or not (body.get("text") or "").strip():
        raise VerbXError("translation_failed")
    return {"text": body["text"].strip(), "degraded": bool(body.get("degraded")),
            "model": (body.get("diagnostics") or {}).get("model")}


def translate(text: str, source: str, target: str, timeout: float | None = None) -> dict:
    """POST /v1/translate → {text, degraded, model}. Raises VerbXError. With a timeout: one attempt only."""
    try:
        res = _translated(_json(_post("/v1/translate", {"text": text, "source_lang": _lang(source),
                                                        "target_lang": _lang(target)},
                                      timeout=timeout, attempts=1 if timeout else 2)))
    except VerbXError:
        metrics.VOICE.labels("translate", "error").inc()
        raise
    metrics.VOICE.labels("translate", "ok").inc()
    return res


def translate_batch(texts: list[str], source: str, target: str) -> list[dict]:
    """POST /v1/translate/batch (≤50 items per call) → one {text, degraded, model} per input, in order."""
    out = []
    for i in range(0, len(texts), BATCH_MAX):
        chunk = texts[i:i + BATCH_MAX]
        try:
            body = _json(_post("/v1/translate/batch", {"items": [{"source": _lang(source), "target": _lang(target),
                                                                  "text": t} for t in chunk]}))
            if not isinstance(body, list) or len(body) != len(chunk):
                raise VerbXError("unexpected_response")
            out += [_translated(b) for b in body]
        except VerbXError:
            metrics.VOICE.labels("translate", "error").inc()
            raise
    metrics.VOICE.labels("translate", "ok").inc()
    return out


# ---------------------------------------------------------------- summaries

def summarize(evaluation: dict, lang: str, doc_marks: dict, names: dict[str, str] | None = None) -> str:
    return " ".join(summary_parts(evaluation, lang, doc_marks, names))


def summary_parts(evaluation: dict, lang: str, doc_marks: dict, names: dict[str, str] | None = None) -> list[str]:
    """Localized voice summary generated only from the deterministic trace, one sentence per part (each part is
    synthesized and cached on its own, so fixed sentences come from the prerendered audio). `names` maps English
    scheme names to (machine-)translated ones; templates are curated per language."""
    names = names or {}
    results = evaluation["results"]
    prov = [r for r in results if r["outcome"] in ("MATCH", "PROVISIONAL")]
    info = [r for r in results if r["outcome"] == "INSUFFICIENT_INFORMATION"]
    parts = [i18n.t(i18n.MESSAGES, "summary_intro", lang),
             i18n.t(i18n.MESSAGES, "summary_count", lang, n=len(prov), m=len(info))]
    for r in prov[:4]:
        parts.append(i18n.t(i18n.MESSAGES, "summary_scheme", lang, name=names.get(r["scheme_name"], r["scheme_name"]),
                            outcome=i18n.t(i18n.OUTCOMES, r["outcome"], lang)))
    gaps = sorted({e["doc_key"] for r in prov for e in r["evidence"] if doc_marks.get(e["doc_key"]) in ("missing", "expired")})
    if gaps:
        parts.append(i18n.t(i18n.MESSAGES, "summary_missing_docs", lang,
                            docs=", ".join(i18n.doc_label(g, lang)[0] for g in gaps)))
    return parts
