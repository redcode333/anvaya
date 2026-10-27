"""VerbX adapter with mocked HTTP: every call shape from docs/vendor/verbx.md and every failure path."""
import base64
import io
import json
import logging
import uuid

import pytest
import requests

from anvaya import translation, voice
from anvaya.common import ApiError
from anvaya.db import get_db, reset_caches
from conftest import start

KEY = "vx_test_key_never_logged"
BASE = "https://verbx.test"
BIHAR = "I am 62 years old, BPL household, I do not get any pension. I live in Bihar."


class Resp:
    def __init__(self, status=200, body=None, content=None, ctype="application/json"):
        self.status_code, self.ok = status, status < 400
        self._body = body
        self.content = content if content is not None else json.dumps(body).encode()
        self.headers = {"Content-Type": ctype, "x-correlation-id": "api_ver_test"}

    def json(self):
        if self._body is None:
            raise ValueError("not json")
        return self._body


class FakeVerbX:
    """Records every request; answers from a queue of Resp objects or exceptions."""

    def __init__(self):
        self.calls, self.queue, self.responder = [], [], None

    def __call__(self, url, headers=None, json=None, timeout=None):
        self.calls.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
        item = self.responder(json) if self.responder else self.queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def tr(text, degraded=False, failed=False):
    return {"text": text, "confidence": 0.99, "diagnostics": {"provider": "verbx", "model": "verbx-langshift"},
            "usage": {"characters": 5}, "degraded": degraded, **({"translation_failed": True} if failed else {})}


@pytest.fixture()
def verbx(app, monkeypatch):
    fake = FakeVerbX()
    monkeypatch.setattr(voice.requests, "post", fake)
    app.config.update(VERBX_BASE_URL=BASE, VERBX_API_KEY=KEY)
    with app.app_context():
        get_db().execute("DELETE FROM translations")
        get_db().execute("DELETE FROM tts_cache")
        get_db().commit()
        reset_caches(get_db())
    yield fake
    app.config.update(VERBX_BASE_URL="", VERBX_API_KEY="")


@pytest.fixture()
def ctx(app):
    with app.test_request_context():
        yield


# ---------------------------------------------------------------- request shape

def test_headers_and_stt_payload(verbx, ctx):
    verbx.queue = [Resp(body={"text": "मेरी उम्र साठ साल है और मैं बिहार में रहता हूँ", "language": "hi", "confidence": 0.9, "model": "verbx-vocaline"})]
    r = voice.transcribe(b"RIFFfake", "audio/wav", "hi")
    assert r == {"transcript": "मेरी उम्र साठ साल है और मैं बिहार में रहता हूँ", "language": "hi", "provider": "verbx", "confidence": 0.9,
                 "model": "verbx-vocaline"}
    call = verbx.calls[0]
    assert call["url"] == f"{BASE}/v1/stt" and call["timeout"] == 15
    assert call["json"] == {"audio_base64": base64.b64encode(b"RIFFfake").decode(), "language": "hi"}
    h = call["headers"]
    assert h["x-api-key"] == KEY and h["X-VerbX-Shell"] == "saas" and h["Content-Type"] == "application/json"
    uuid.UUID(h["Idempotency-Key"])


def test_tts_payload_and_binary_audio(verbx, ctx):
    verbx.queue = [Resp(content=b"RIFF....WAVE", ctype="audio/wav")]
    r = voice.speak("నమస్కారం", "te")
    assert {k: r[k] for k in ("audio_base64", "mime_type", "provider", "cached")} == {
        "audio_base64": base64.b64encode(b"RIFF....WAVE").decode(), "mime_type": "audio/wav", "provider": "verbx",
        "cached": False}
    assert verbx.calls[0]["url"] == f"{BASE}/v1/tts"
    assert verbx.calls[0]["json"] == {"text": "నమస్కారం", "options": {"language": "te", "format": "wav", "voice_id": "verbx-female"}}


def test_translate_payload(verbx, ctx):
    verbx.queue = [Resp(body=tr("हैलो वर्ल्ड"))]
    assert voice.translate("Hello world", "en", "hi") == {"text": "हैलो वर्ल्ड", "degraded": False, "model": "verbx-langshift"}
    assert verbx.calls[0]["url"] == f"{BASE}/v1/translate"
    assert verbx.calls[0]["json"] == {"text": "Hello world", "source_lang": "en", "target_lang": "hi"}


def test_batch_payload_and_chunking(verbx, ctx):
    texts = [f"scheme {i}" for i in range(51)]
    verbx.queue = [Resp(body=[tr(f"योजना {i}") for i in range(50)]), Resp(body=[tr("योजना 50")])]
    out = voice.translate_batch(texts, "en", "hi")
    assert [o["text"] for o in out] == [f"योजना {i}" for i in range(51)]
    assert [len(c["json"]["items"]) for c in verbx.calls] == [50, 1]
    assert verbx.calls[0]["url"] == f"{BASE}/v1/translate/batch"
    assert verbx.calls[0]["json"]["items"][0] == {"source": "en", "target": "hi", "text": "scheme 0"}


def test_each_request_gets_a_new_idempotency_key(verbx, ctx):
    verbx.queue = [Resp(body=tr("a")), Resp(body=tr("b"))]
    voice.translate("a", "en", "hi")
    voice.translate("b", "en", "hi")
    assert verbx.calls[0]["headers"]["Idempotency-Key"] != verbx.calls[1]["headers"]["Idempotency-Key"]


# ---------------------------------------------------------------- retries

@pytest.mark.parametrize("first", [Resp(503, {"error": {"code": "ERR_HTTP"}}), requests.Timeout(), requests.ConnectionError()])
def test_one_retry_on_5xx_or_timeout_reuses_idempotency_key(verbx, ctx, first):
    verbx.queue = [first, Resp(body=tr("ok"))]
    assert voice.translate("x", "en", "te")["text"] == "ok"
    assert len(verbx.calls) == 2
    assert verbx.calls[0]["headers"]["Idempotency-Key"] == verbx.calls[1]["headers"]["Idempotency-Key"]


def test_gives_up_after_one_retry(verbx, ctx):
    verbx.queue = [Resp(500, {}), requests.Timeout()]
    with pytest.raises(voice.VerbXError, match="timeout"):
        voice.translate("x", "en", "hi")
    assert len(verbx.calls) == 2


@pytest.mark.parametrize("status", [401, 422, 429])
def test_no_retry_on_4xx(verbx, ctx, status):
    verbx.queue = [Resp(status, {"error": {"code": "unauthorized.key_invalid"}})]
    with pytest.raises(voice.VerbXError, match=f"http_{status}"):
        voice.translate("x", "en", "hi")
    assert len(verbx.calls) == 1


# ---------------------------------------------------------------- failure → clean fallback

def test_not_configured_makes_no_http_call(app, monkeypatch, ctx):
    fake = FakeVerbX()
    monkeypatch.setattr(voice.requests, "post", fake)
    for call in (lambda: voice.transcribe(b"x", "audio/wav", "hi"), lambda: voice.speak("hi", "hi")):
        with pytest.raises(ApiError) as e:
            call()
        assert e.value.code == "VOICE_UNAVAILABLE" and e.value.status == 503
    assert fake.calls == [] and voice.status()["verbx_configured"] is False


def test_stt_empty_degraded_transcript_is_unavailable(verbx, ctx):
    verbx.queue = [Resp(body={"text": "", "language": None, "degraded": True, "degraded_reason": "provider_outage",
                              "served_by_tier": "refuse"})]
    with pytest.raises(Exception) as e:
        voice.transcribe(b"junk", "audio/webm", "hi")
    assert e.value.code == "VOICE_UNAVAILABLE" and e.value.details == {"reason": "no_speech"}


@pytest.mark.parametrize("resp", [Resp(500, {}), Resp(body={"oops": 1}, ctype="application/json"), Resp(content=b"", ctype="audio/wav")])
def test_tts_failures_are_voice_unavailable(verbx, ctx, resp):
    verbx.queue = [resp, resp]
    with pytest.raises(Exception) as e:
        voice.speak("text", "en")
    assert e.value.code == "VOICE_UNAVAILABLE"


def test_stt_invalid_json_is_voice_unavailable(verbx, ctx):
    verbx.queue = [Resp(content=b"<html>", ctype="text/html")]
    with pytest.raises(Exception) as e:
        voice.transcribe(b"x", "audio/wav", "te")
    assert e.value.code == "VOICE_UNAVAILABLE" and "invalid_json" in e.value.message


@pytest.mark.parametrize("body", [tr("", failed=False), tr("x", failed=True), {"error": "nope"}])
def test_failed_translation_raises(verbx, ctx, body):
    verbx.queue = [Resp(body=body)]
    with pytest.raises(voice.VerbXError):
        voice.translate("x", "en", "hi")


def test_batch_length_mismatch_raises(verbx, ctx):
    verbx.queue = [Resp(body=[tr("one")])]
    with pytest.raises(voice.VerbXError, match="unexpected_response"):
        voice.translate_batch(["a", "b"], "en", "hi")


def test_unsupported_language_rejected_before_any_call(verbx, ctx):
    with pytest.raises(Exception) as e:
        voice.speak("x", "fr")
    assert e.value.code == "UNSUPPORTED_LANGUAGE" and verbx.calls == []


def test_logs_never_contain_key_text_or_audio(verbx, ctx, caplog):
    caplog.set_level(logging.DEBUG, logger="anvaya")
    verbx.queue = [Resp(body={"text": "मेरी उम्र साठ साल है और मैं बिहार में रहता हूँ"}), Resp(500, {}), Resp(500, {})]
    voice.transcribe(b"SECRETAUDIO", "audio/wav", "hi")
    with pytest.raises(voice.VerbXError):
        voice.translate("private sentence", "en", "hi")
    logged = " ".join(r.getMessage() for r in caplog.records)
    assert "/v1/stt" in logged and "status=500" in logged
    for secret in (KEY, "साठ", "private sentence", base64.b64encode(b"SECRETAUDIO").decode()):
        assert secret not in logged


# ---------------------------------------------------------------- cache

def test_translate_many_caches_and_skips_degraded(verbx, ctx):
    verbx.queue = [Resp(body=[tr("वृद्धावस्था पेंशन"), tr("खराब", degraded=True)])]
    assert translation.translate_many(["Old age pension", "Widow pension"], "en", "hi") == \
        {"Old age pension": "वृद्धावस्था पेंशन", "Widow pension": "खराब"}
    verbx.queue = [Resp(body=[tr("विधवा पेंशन")])]
    again = translation.translate_many(["Old age pension", "Widow pension"], "en", "hi")
    assert again == {"Old age pension": "वृद्धावस्था पेंशन", "Widow pension": "विधवा पेंशन"}
    assert [c["json"]["items"] for c in verbx.calls][1] == [{"source": "en", "target": "hi", "text": "Widow pension"}]
    translation.translate_many(["Old age pension", "Widow pension"], "en", "hi")
    assert len(verbx.calls) == 2, "everything cached now"


def test_translate_many_failure_returns_what_is_cached(verbx, ctx):
    verbx.queue = [Resp(401, {})]
    assert translation.translate_many(["Old age pension"], "en", "te") == {}


# ---------------------------------------------------------------- API

def test_translate_endpoint_labels_and_caches(client, verbx):
    sid = client.post("/api/v1/sessions", json={"mode": "personal", "language": "te"}).json["session_id"]
    verbx.queue = [Resp(body=tr("వృద్ధాప్య పింఛను"))]
    r = client.post(f"/api/v1/sessions/{sid}/translate", json={"text": "Old age pension"}).json
    assert r == {"text": "వృద్ధాప్య పింఛను", "source_text": "Old age pension", "source_lang": "en", "target_lang": "te",
                 "machine_translated": True, "provider": "verbx", "cached": False}
    again = client.post(f"/api/v1/sessions/{sid}/translate", json={"text": "Old age pension"}).json
    assert again["cached"] is True and len(verbx.calls) == 1
    same = client.post(f"/api/v1/sessions/{sid}/translate", json={"text": "నమస్తే", "source_lang": "te"}).json
    assert same["machine_translated"] is False and len(verbx.calls) == 1


def test_translate_endpoint_errors(client, verbx, app):
    sid = client.post("/api/v1/sessions", json={"mode": "personal", "language": "hi"}).json["session_id"]
    url = f"/api/v1/sessions/{sid}/translate"
    assert client.post(url, json={"text": ""}).json["error"]["code"] == "INVALID_TEXT"
    assert client.post(url, json={"text": "x", "target_lang": "fr"}).json["error"]["code"] == "UNSUPPORTED_LANGUAGE"
    verbx.queue = [Resp(503, {}), Resp(503, {})]
    r = client.post(url, json={"text": "Hello"})
    assert r.status_code == 503 and r.json["error"]["code"] == "TRANSLATION_UNAVAILABLE"
    app.config["VERBX_API_KEY"] = ""
    assert client.post(url, json={"text": "Hello"}).json["error"]["code"] == "TRANSLATION_UNAVAILABLE"


def test_evaluation_localizes_scheme_names_and_summary(client, verbx):
    sid = start(client, BIHAR, lang="hi")
    verbx.responder = lambda body: Resp(body=[tr(f"[hi] {i['text']}") for i in body["items"]])
    ev = client.post(f"/api/v1/sessions/{sid}/eligibility/evaluate").json
    pj = next(r for r in ev["results"] if r["rule_id"] == "R_IGNOAPS_BIHAR")
    assert pj["scheme_name_localized"] == f"[hi] {pj['scheme_name']}" and pj["scheme_name_machine_translated"]
    assert f"[hi] {pj['scheme_name']}" in ev["voice_summary"] and ev["voice_summary_machine_translated"]
    latest = client.get(f"/api/v1/sessions/{sid}/eligibility/latest").json
    assert latest["voice_summary"] == ev["voice_summary"]
    assert len(verbx.calls) == 1, "names are translated once and then served from the cache"


def test_evaluation_falls_back_to_english_names_when_verbx_fails(client, verbx):
    sid = start(client, BIHAR, lang="hi")
    verbx.queue = [Resp(500, {}), Resp(500, {})]
    r = client.post(f"/api/v1/sessions/{sid}/eligibility/evaluate")
    assert r.status_code == 200
    assert all(x["scheme_name_localized"] is None and not x["scheme_name_machine_translated"] for x in r.json["results"])
    assert r.json["voice_summary_machine_translated"] is False


def test_english_session_never_calls_verbx_for_names(client, verbx):
    sid = start(client, BIHAR)
    assert client.post(f"/api/v1/sessions/{sid}/eligibility/evaluate").status_code == 200
    assert verbx.calls == []


def test_transcribe_and_speak_endpoints(client, verbx):
    sid = client.post("/api/v1/sessions", json={"mode": "personal", "language": "te"}).json["session_id"]
    verbx.queue = [Resp(body={"text": "నా వయసు అరవై అయిదు సంవత్సరాలు, నేను ఆంధ్రప్రదేశ్ లో ఉంటాను", "confidence": 0.9, "model": "verbx-vocaline"})]
    r = client.post(f"/api/v1/sessions/{sid}/voice/transcribe",
                    data={"audio": (io.BytesIO(b"RIFFclip"), "speech.webm", "audio/webm")}, content_type="multipart/form-data")
    assert r.status_code == 200 and r.json["transcript"] == "నా వయసు అరవై అయిదు సంవత్సరాలు, నేను ఆంధ్రప్రదేశ్ లో ఉంటాను"
    assert verbx.calls[0]["json"]["language"] == "te"
    verbx.queue = [Resp(content=b"RIFFwav", ctype="audio/wav")]
    s = client.post(f"/api/v1/sessions/{sid}/voice/speak", json={"text": "నమస్కారం"}).json
    assert base64.b64decode(s["audio_base64"]) == b"RIFFwav"
    assert client.get("/api/v1/voice/status").json == {"verbx_configured": True, "stt": True, "tts": True,
                                                       "translation": True, "languages": ["en", "hi", "te"]}


# ---------------------------------------------------------------- TTS cache

def test_tts_is_cached_by_text_language_and_voice(verbx, ctx, app):
    verbx.responder = lambda body: Resp(content=b"RIFF" + body["text"].encode(), ctype="audio/wav")
    first = voice.speak("  Namaste!  ", "en")
    again = voice.speak("Namaste!", "en")
    assert (first["cached"], again["cached"]) == (False, True) and first["audio_base64"] == again["audio_base64"]
    assert len(verbx.calls) == 1
    voice.speak("Namaste!", "hi")  # other language: another clip
    app.config["VERBX_TTS_VOICE"] = "verbx-male"
    try:
        voice.speak("Namaste!", "en")  # other voice: another clip
    finally:
        app.config["VERBX_TTS_VOICE"] = "verbx-female"
    assert len(verbx.calls) == 3
    row = get_db().execute("SELECT * FROM tts_cache WHERE cache_key=?",
                           (voice.tts_key("Namaste!", "en", "verbx-female"),)).fetchone()
    assert row["pinned"] == 0 and "Namaste" not in " ".join(str(v) for v in dict(row).values() if not isinstance(v, bytes))


def test_cached_audio_plays_without_verbx(verbx, ctx, app):
    verbx.queue = [Resp(content=b"RIFFx", ctype="audio/wav")]
    voice.speak("Which state do you live in?", "en")
    app.config.update(VERBX_BASE_URL="", VERBX_API_KEY="")
    assert voice.speak("Which state do you live in?", "en")["cached"] is True


def test_slow_tts_answers_unavailable_and_finishes_into_the_cache(verbx, ctx, app):
    import threading
    release = threading.Event()

    def slow(body):
        release.wait(5)
        return Resp(content=b"RIFFslow", ctype="audio/wav")
    verbx.responder = slow
    app.config["TTS_WAIT_S"] = 0.05
    try:
        with pytest.raises(ApiError) as e:
            voice.speak("A slow sentence.", "te")
        assert e.value.code == "VOICE_UNAVAILABLE" and e.value.details == {"reason": "timeout"}
        release.set()
        pending = voice._inflight.get(voice.tts_key("A slow sentence.", "te", "verbx-female"))
        if pending:  # None = the background synthesis already finished (it is stored before leaving _inflight)
            pending.result(5)
        r = voice.speak("A slow sentence.", "te")
        assert r["cached"] is True and len(verbx.calls) == 1
    finally:
        app.config["TTS_WAIT_S"] = 8.0


def test_prerender_covers_fixed_prompts_and_pins_them(verbx, ctx):
    from anvaya import i18n, prerender
    # scheme-name translation fails (names stay English); every TTS call succeeds
    verbx.responder = lambda body: Resp(500, {"detail": "x"}) if "items" in body else Resp(content=b"RIFF", ctype="audio/wav")
    items = prerender.texts(max_count=1)
    texts = {(t, lang) for t, lang, _ in items}
    for lang in ("en", "hi", "te"):
        assert (i18n.t(i18n.MESSAGES, "greeting", lang), lang) in texts
        assert (i18n.t(i18n.MESSAGES, "please_confirm", lang), lang) in texts
        assert all((i18n.t(i18n.QUESTIONS, q, lang), lang) in texts for q in i18n.QUESTIONS)
        assert (i18n.t(i18n.MESSAGES, "summary_count", lang, n=1, m=0), lang) in texts
    sample = [(i18n.t(i18n.MESSAGES, "ready", lang), lang) for lang in ("en", "hi", "te")]
    rows = voice.prerender(sample + sample, concurrency=2)
    assert [r["result"] for r in rows] == ["synthesized"] * 3  # duplicates collapsed
    assert [r["result"] for r in voice.prerender(sample)] == ["cached"] * 3
    assert voice.cache_stats()["prerendered"] == 3


def test_turn_reply_and_summary_come_in_speakable_sentences(client):
    sid = client.post("/api/v1/sessions", json={"mode": "personal", "language": "hi"}).json["session_id"]
    r = client.post(f"/api/v1/sessions/{sid}/turns", json={"utterance": BIHAR, "channel": "voice"}).json
    from anvaya import i18n
    assert r["reply"] == " ".join(r["reply_segments"])
    # By voice the important facts are read back with one spoken question, not sent to the profile card.
    assert i18n.t(i18n.MESSAGES, "confirm_question", "hi") in r["reply_segments"]
    assert i18n.t(i18n.MESSAGES, "please_confirm", "hi") not in r["reply_segments"]


def test_cleanup_keeps_prerendered_audio(verbx, ctx):
    db = get_db()
    db.executemany("INSERT INTO tts_cache(cache_key, language, voice, mime_type, audio, synth_ms, pinned, created_at)"
                   " VALUES (?,?,?,?,?,?,?,?)", [(key, "en", "v", "audio/wav", b"\x00", 1, pinned, "2000-01-01T00:00:00+00:00")
                                                 for key, pinned in (("old", 0), ("pin", 1))])
    db.commit()
    assert voice.purge_audio(db, older_than_hours=12) == 1
    assert {r[0] for r in get_db().execute("SELECT cache_key FROM tts_cache")} == {"pin"}


def test_prerender_retries_after_rate_limit(verbx, ctx):
    answers = [Resp(429, {"detail": "rate"}), Resp(429, {"detail": "rate"}), Resp(content=b"RIFF", ctype="audio/wav")]
    verbx.responder = lambda body: answers.pop(0)
    rows = voice.prerender([("Namaste!", "hi")], concurrency=1, per_minute=0, backoff=(0, 0))
    assert rows[0]["result"] == "synthesized" and len(verbx.calls) == 3
    verbx.responder = lambda body: Resp(429, {"detail": "rate"})
    assert voice.prerender([("Again.", "hi")], per_minute=0, backoff=(0,))[0]["result"] == "error:http_429"


# ---------------------------------------------------------------- the person speaks a different language than the screen

EN = "I am 22 years old and I live in Bihar."
HI_TRANSLITERATION = "आईम टवटी टू इयर्स ल् एंड आईिव इन बिहार"  # what VerbX returns for English audio when told "hi"


def stt(text, lang="hi"):
    return Resp(body={"text": text, "language": lang, "confidence": 0.9, "model": "verbx-vocaline"})


def test_stage_direction_placeholder_is_retried_in_other_languages(verbx, ctx):
    verbx.queue = [stt("(speaking in foreign language)"), stt(EN, "en")]
    r = voice.transcribe(b"audio", "audio/webm", "hi")
    assert r["transcript"] == EN and r["language"] == "en" and r["requested_language"] == "hi" and r["tried"] == ["hi", "en"]
    assert [c["json"]["language"] for c in verbx.calls] == ["hi", "en"]


def test_english_transliterated_into_devanagari_loses_to_the_real_english(verbx, ctx):
    # The transliteration still contains "बिहार" (one fact); English gives age and state.
    verbx.queue = [stt(HI_TRANSLITERATION), stt(EN, "en")]
    r = voice.transcribe(b"audio", "audio/webm", "hi")
    assert r["transcript"] == EN and r["language"] == "en"


def test_a_convincing_first_answer_costs_one_call(verbx, ctx):
    verbx.queue = [stt("मेरी उम्र साठ साल है और मैं बिहार में रहता हूँ")]
    r = voice.transcribe(b"audio", "audio/webm", "hi")
    assert r["language"] == "hi" and "tried" not in r and len(verbx.calls) == 1


def test_a_short_reply_is_accepted_without_retries(verbx, ctx):
    verbx.queue = [stt("हाँ")]
    assert voice.transcribe(b"audio", "audio/webm", "hi")["transcript"] == "हाँ" and len(verbx.calls) == 1


def test_noise_hallucination_and_wrong_script_are_not_believable(verbx, ctx):
    verbx.queue = [stt("বো " * 12), stt("[BLANK_AUDIO]", "en"), stt(EN.replace("Bihar", "बिहार"), "te")]
    with pytest.raises(Exception) as e:
        voice.transcribe(b"audio", "audio/webm", "hi")
    assert e.value.code == "VOICE_UNAVAILABLE" and e.value.details["reason"] == "unintelligible"


def test_a_failing_alternate_keeps_the_first_usable_answer(verbx, ctx):
    verbx.queue = [stt(HI_TRANSLITERATION), Resp(500, {}), ]
    r = voice.transcribe(b"audio", "audio/webm", "hi")
    assert r["transcript"] == HI_TRANSLITERATION and r["language"] == "hi"


def test_site_language_is_not_the_only_one_tried_for_english_screens(verbx, ctx):
    verbx.queue = [stt("(inaudible)", "en"), stt("मेरी उम्र साठ साल है और मैं बिहार में रहता हूँ")]
    r = voice.transcribe(b"audio", "audio/webm", "en")
    assert r["language"] == "hi" and [c["json"]["language"] for c in verbx.calls] == ["en", "hi"]


# ---------------------------------------------------------------- the bot just asked a question; pauses and thinking sounds

def test_a_doubtful_short_reply_to_a_question_is_checked_in_the_other_languages(verbx, ctx):
    # English speech recognition hears "Telangana" as "The Londoner"; the Telugu reading names the state.
    verbx.queue = [stt("The Londoner", "en"), stt("द लंडनर", "hi"), stt("తెలంగాణ", "te")]
    r = voice.transcribe(b"audio", "audio/webm", "en", asked="state")
    assert r["transcript"] == "తెలంగాణ" and r["language"] == "te" and r["tried"] == ["en", "hi", "te"]


def test_without_a_question_a_short_reply_still_costs_one_call(verbx, ctx):
    verbx.queue = [stt("The Londoner", "en")]
    assert voice.transcribe(b"audio", "audio/webm", "en")["transcript"] == "The Londoner" and len(verbx.calls) == 1


def test_a_short_reply_that_answers_the_question_costs_one_call(verbx, ctx):
    verbx.queue = [stt("Bihar", "en")]
    assert voice.transcribe(b"audio", "audio/webm", "en", asked="state")["transcript"] == "Bihar" and len(verbx.calls) == 1
    verbx.calls.clear()
    verbx.queue = [stt("no", "en")]
    assert voice.transcribe(b"audio", "audio/webm", "en", asked="bpl")["transcript"] == "no" and len(verbx.calls) == 1


@pytest.mark.parametrize("text", ["umm", "Uh", "hmm", "aa", "अ", "उम्म", "हम्म", "ఆ", "um, uh", "Er..."])
def test_thinking_sounds_are_dropped_as_no_speech(verbx, ctx, text):
    verbx.queue = [stt(text, "en")]
    with pytest.raises(Exception) as e:
        voice.transcribe(b"audio", "audio/webm", "en")
    assert e.value.details["reason"] == "no_speech" and len(verbx.calls) == 1  # no retries spent on a pause


@pytest.mark.parametrize("text", ["uh-huh", "uh-uh", "hmm yes", "yes", "no", "okay", "हाँ", "Bihar", "umm Bihar", "हम पाँच लोग हैं"])
def test_real_answers_are_not_fillers(text):
    from anvaya import extraction
    assert not extraction.is_filler(text)
