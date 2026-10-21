"""VerbX speech adapter + deterministic localized result summaries.

The VerbX request/response shape is configurable through env vars because the exact
organizer contract was not available while building; reconcile VERBX_* settings with
the VerbX documentation before the demo. When VerbX is not configured or fails, the API
returns VOICE_UNAVAILABLE and the frontend falls back to browser speech, then to text.
"""
import base64

import requests
from flask import current_app

from . import i18n, metrics
from .common import ApiError

VERBX_LANG = {"en": "en-IN", "hi": "hi-IN", "te": "te-IN"}


def _cfg():
    c = current_app.config
    if not c["VERBX_BASE_URL"] or not c["VERBX_API_KEY"]:
        metrics.VOICE.labels("any", "not_configured").inc()
        raise ApiError("VOICE_UNAVAILABLE", "VerbX speech service is not configured; use text or browser speech.", 503)
    return c


def status() -> dict:
    c = current_app.config
    return {"verbx_configured": bool(c["VERBX_BASE_URL"] and c["VERBX_API_KEY"]),
            "languages": list(VERBX_LANG)}


def transcribe(audio: bytes, mimetype: str, language: str) -> dict:
    c = _cfg()
    try:
        r = requests.post(
            c["VERBX_BASE_URL"].rstrip("/") + c["VERBX_STT_PATH"],
            headers={"Authorization": f"Bearer {c['VERBX_API_KEY']}"},
            files={"audio": ("speech", audio, mimetype or "audio/webm")},
            data={"language": VERBX_LANG.get(language, language)},
            timeout=c["VERBX_TIMEOUT_S"],
        )
        r.raise_for_status()
        body = r.json()
    except (requests.RequestException, ValueError) as e:
        metrics.VOICE.labels("stt", "error").inc()
        raise ApiError("VOICE_UNAVAILABLE", f"VerbX transcription failed ({type(e).__name__}); please type instead.", 503)
    metrics.VOICE.labels("stt", "ok").inc()
    text = body.get("text") or body.get("transcript") or ""
    return {"transcript": text, "language": language, "provider": "verbx", "confidence": body.get("confidence")}


def speak(text: str, language: str) -> dict:
    c = _cfg()
    try:
        r = requests.post(
            c["VERBX_BASE_URL"].rstrip("/") + c["VERBX_TTS_PATH"],
            headers={"Authorization": f"Bearer {c['VERBX_API_KEY']}"},
            json={"text": text, "language": VERBX_LANG.get(language, language)},
            timeout=c["VERBX_TIMEOUT_S"],
        )
        r.raise_for_status()
    except requests.RequestException as e:
        metrics.VOICE.labels("tts", "error").inc()
        raise ApiError("VOICE_UNAVAILABLE", f"VerbX speech synthesis failed ({type(e).__name__}).", 503)
    metrics.VOICE.labels("tts", "ok").inc()
    if r.headers.get("Content-Type", "").startswith("audio/"):
        audio_b64, mime = base64.b64encode(r.content).decode(), r.headers["Content-Type"]
    else:
        body = r.json()
        audio_b64, mime = body.get("audio"), body.get("mime_type", "audio/mpeg")
    return {"audio_base64": audio_b64, "mime_type": mime, "provider": "verbx"}


def summarize(evaluation: dict, lang: str, doc_marks: dict) -> str:
    """Localized voice summary generated only from the deterministic trace."""
    results = evaluation["results"]
    prov = [r for r in results if r["outcome"] in ("MATCH", "PROVISIONAL")]
    info = [r for r in results if r["outcome"] == "INSUFFICIENT_INFORMATION"]
    parts = [i18n.t(i18n.MESSAGES, "summary_intro", lang),
             i18n.t(i18n.MESSAGES, "summary_count", lang, n=len(prov), m=len(info))]
    for r in prov[:4]:
        parts.append(i18n.t(i18n.MESSAGES, "summary_scheme", lang, name=r["scheme_name"],
                            outcome=i18n.t(i18n.OUTCOMES, r["outcome"], lang)))
    gaps = sorted({e["doc_key"] for r in prov for e in r["evidence"] if doc_marks.get(e["doc_key"]) in ("missing", "expired")})
    if gaps:
        parts.append(i18n.t(i18n.MESSAGES, "summary_missing_docs", lang,
                            docs=", ".join(i18n.doc_label(g, lang)[0] for g in gaps)))
    return " ".join(parts)
