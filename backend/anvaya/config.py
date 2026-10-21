import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BACKEND_DIR.parent


class Config:
    DB_PATH = os.environ.get("ANVAYA_DB", str(BACKEND_DIR / "instance" / "anvaya.db"))
    DATASET_CSV = os.environ.get(
        "ANVAYA_DATASET",
        str(PROJECT_DIR / "data" / "raw" / "structured_govt_schemes_converted.csv"),
    )
    GOLDEN_RULES = str(Path(__file__).resolve().parent / "data" / "golden_rules.json")

    # Bumped whenever golden_rules.json changes in a way that can change outcomes.
    RULE_BUNDLE_VERSION = os.environ.get("ANVAYA_RULE_BUNDLE_VERSION", "rules-2026.10.1")

    # Per-rule freshness is configured in golden_rules.json; this is only the fallback.
    DEFAULT_FRESHNESS_DAYS = int(os.environ.get("ANVAYA_DEFAULT_FRESHNESS_DAYS", "180"))

    # When set, GET /metrics requires "Authorization: Bearer <token>" (used in Kubernetes behind an Ingress).
    METRICS_TOKEN = os.environ.get("ANVAYA_METRICS_TOKEN", "")

    SESSION_TTL_HOURS = int(os.environ.get("ANVAYA_SESSION_TTL_HOURS", "12"))
    CASE_CODE_TTL_HOURS = int(os.environ.get("ANVAYA_CASE_CODE_TTL_HOURS", "72"))
    AUTH_TOKEN_TTL_HOURS = int(os.environ.get("ANVAYA_AUTH_TOKEN_TTL_HOURS", "8"))
    CODE_LOOKUP_LIMIT_PER_MIN = int(os.environ.get("ANVAYA_CODE_LOOKUP_LIMIT", "10"))

    # VerbX speech/translation adapter. Unset => voice endpoints return VOICE_UNAVAILABLE
    # and the frontend falls back to browser speech or text.
    VERBX_BASE_URL = os.environ.get("VERBX_BASE_URL", "")
    VERBX_API_KEY = os.environ.get("VERBX_API_KEY", "")
    VERBX_STT_PATH = os.environ.get("VERBX_STT_PATH", "/v1/stt")
    VERBX_TTS_PATH = os.environ.get("VERBX_TTS_PATH", "/v1/tts")
    VERBX_TIMEOUT_S = float(os.environ.get("VERBX_TIMEOUT_S", "15"))

    # Optional LLM fact extraction. Deterministic extraction always runs; the LLM only
    # proposes extra candidate facts, which are schema-validated and stay unconfirmed.
    ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
    ANVAYA_LLM_MODEL = os.environ.get("ANVAYA_LLM_MODEL", "claude-opus-5-5")
    LLM_EXTRACTION = os.environ.get("ANVAYA_LLM_EXTRACTION", "off").lower() == "on"
