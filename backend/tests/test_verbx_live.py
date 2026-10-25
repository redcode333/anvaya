"""Live VerbX checks (pytest -m live). Reads VERBX_* from the environment or the repo-root .env; never prints the key."""
import base64
import os
import time
from pathlib import Path

import pytest

from anvaya import create_app, voice

pytestmark = pytest.mark.live


def _env() -> dict:
    env = {k: v for k, v in os.environ.items() if k.startswith("VERBX_")}
    dotenv = Path(__file__).resolve().parents[2] / ".env"
    if dotenv.exists():
        for line in dotenv.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env.setdefault(k.strip(), v.strip())
    return env


@pytest.fixture(scope="module")
def live_app(tmp_path_factory):
    env = _env()
    if not env.get("VERBX_API_KEY"):
        pytest.skip("VERBX_API_KEY not set")
    app = create_app({"DATABASE_URL": "", "DB_PATH": str(tmp_path_factory.mktemp("live") / "live.db"), "TESTING": True,
                      "VERBX_BASE_URL": env.get("VERBX_BASE_URL") or "https://api.verbxeco.com",
                      "VERBX_API_KEY": env["VERBX_API_KEY"]})
    with app.app_context():
        yield app


def timed(fn, *args):
    t0 = time.perf_counter()
    out = fn(*args)
    return out, round((time.perf_counter() - t0) * 1000)


@pytest.mark.parametrize("text,source,target,expect", [
    ("Old age pension", "en", "hi", "पेंशन"),
    ("Old age pension", "en", "te", "పింఛను"),
    ("मेरी उम्र साठ साल है", "hi", "en", "sixty"),
    ("నా వయస్సు అరవై ఐదు సంవత్సరాలు", "te", "en", "sixty"),
])
def test_live_translate(live_app, text, source, target, expect, record_property):
    out, ms = timed(voice.translate, text, source, target)
    record_property("latency_ms", ms)
    print(f"\n{source}->{target}: {len(out['text'])} chars in {ms} ms")  # text not printed: console may not be UTF-8
    assert expect in out["text"].lower(), out["text"]
    assert ms < 15000


@pytest.mark.parametrize("lang,text", [("hi", "मेरी उम्र पैंसठ साल है"), ("te", "నా వయస్సు అరవై ఐదు సంవత్సరాలు")])
def test_live_speech_round_trip(live_app, lang, text, record_property):
    """VerbX TTS makes a short real clip, VerbX STT transcribes it; latency of both is recorded."""
    audio, tts_ms = timed(voice.speak, text, lang)
    clip = base64.b64decode(audio["audio_base64"])
    stt, stt_ms = timed(voice.transcribe, clip, audio["mime_type"], lang)
    record_property("tts_ms", tts_ms)
    record_property("stt_ms", stt_ms)
    print(f"\n{lang}: TTS {len(clip)} bytes WAV in {tts_ms} ms; STT {len(stt['transcript'])} chars in {stt_ms} ms")
    assert clip[:4] == b"RIFF" and stt["transcript"]
