import os
from pathlib import Path

from .llm.providers import load_providers

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BACKEND_DIR.parent

# Problems found while reading the environment (bad numbers, unset demo passwords). Logged once at startup and shown
# on /ready; they never stop the app. Messages name the variable only, never its value.
CONFIG_WARNINGS: list[str] = []


def _num(name: str, default, cast=float):
    raw = os.environ.get(name, "")
    if not raw.strip():
        return default
    try:
        return cast(raw)
    except ValueError:
        CONFIG_WARNINGS.append(f"{name} is not a valid number; using the default {default}")
        return default


def _flag(name: str, default: bool, on=("1", "true", "on", "yes")) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    return default if not raw else raw in on


# Seeded staff accounts: username -> (password env var, role, display name, demo password used only when unset).
STAFF_ACCOUNTS = {
    "reviewer": ("ANVAYA_REVIEWER_PASSWORD", "reviewer", "Demo Reviewer", "reviewer123"),
    "operator": ("ANVAYA_OPERATOR_PASSWORD", "operator", "Demo Kiosk Operator", "operator123"),
    "admin": ("ANVAYA_ADMIN_PASSWORD", "admin", "Demo Data Steward", "admin123"),
}


class Config:
    # DATABASE_URL set → PostgreSQL (e.g. Supabase through its Session pooler); unset → the SQLite file DB_PATH.
    # The URL holds a password: it is never logged or returned (/ready shows only "sqlite" / "postgres").
    DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
    DB_PATH = os.environ.get("ANVAYA_DB", str(BACKEND_DIR / "instance" / "anvaya.db"))
    DB_SCHEMA = ""  # Postgres schema; empty = the connection's default (public). Tests use one schema per app.
    DB_POOL_MAX = _num("ANVAYA_DB_POOL_MAX", 5, int)
    # In-memory copies of read-mostly data (rules, catalogue facets, TTS index) re-check their version row at most
    # this often, so most requests read them with no database round trip.
    DB_CACHE_CHECK_S = _num("ANVAYA_DB_CACHE_CHECK_S", 5.0)
    DATASET_CSV = os.environ.get(
        "ANVAYA_DATASET",
        str(PROJECT_DIR / "data" / "raw" / "structured_govt_schemes_converted.csv"),
    )
    GOLDEN_RULES = str(Path(__file__).resolve().parent / "data" / "golden_rules.json")

    # Bumped whenever golden_rules.json changes in a way that can change outcomes.
    RULE_BUNDLE_VERSION = os.environ.get("ANVAYA_RULE_BUNDLE_VERSION", "rules-2026.10.1")

    # Per-rule freshness is configured in golden_rules.json; this is only the fallback.
    DEFAULT_FRESHNESS_DAYS = _num("ANVAYA_DEFAULT_FRESHNESS_DAYS", 180, int)

    # When set, GET /metrics requires "Authorization: Bearer <token>" (used in Kubernetes behind an Ingress).
    METRICS_TOKEN = os.environ.get("ANVAYA_METRICS_TOKEN", "")

    SESSION_TTL_HOURS = _num("ANVAYA_SESSION_TTL_HOURS", 12, int)
    CASE_CODE_TTL_HOURS = _num("ANVAYA_CASE_CODE_TTL_HOURS", 72, int)
    AUTH_TOKEN_TTL_HOURS = _num("ANVAYA_AUTH_TOKEN_TTL_HOURS", 8, int)
    CODE_LOOKUP_LIMIT_PER_MIN = _num("ANVAYA_CODE_LOOKUP_LIMIT", 10, int)

    # Running or resetting the official scenarios (POST /test-runs/*) needs an admin token unless demo mode is on.
    DEMO_TEST_RUNS = os.environ.get("ANVAYA_DEMO_TEST_RUNS", "off").lower() == "on"

    # VerbX speech (STT/TTS) and translation; contract in docs/vendor/verbx.md. Unset => voice endpoints return
    # VOICE_UNAVAILABLE (frontend falls back to browser speech, then text) and scheme names stay in English.
    VERBX_BASE_URL = os.environ.get("VERBX_BASE_URL", "")
    VERBX_API_KEY = os.environ.get("VERBX_API_KEY", "")
    VERBX_SHELL = os.environ.get("VERBX_SHELL", "saas")
    VERBX_TTS_VOICE = os.environ.get("VERBX_TTS_VOICE", "verbx-female")
    VERBX_TIMEOUT_S = _num("VERBX_TIMEOUT_S", 15.0)
    # A read-aloud request waits at most this long; slower syntheses finish in the background and land in the
    # audio cache, so the next request for the same text is instant.
    TTS_WAIT_S = _num("ANVAYA_TTS_WAIT_S", 8.0)

    # Optional LLM fact extraction (anvaya/llm). Deterministic extraction always runs and stays primary; the LLM only
    # adds or cross-checks candidate facts, which are validated, merged and never confirmed automatically.
    LLM_EXTRACTION = os.environ.get("ANVAYA_LLM_EXTRACTION", "off").lower() == "on"
    LLM_PROVIDERS = load_providers(os.environ, CONFIG_WARNINGS)
    LLM_CALL_TIMEOUT_S = _num("LLM_CALL_TIMEOUT_S", 6.0)
    LLM_TURN_BUDGET_S = _num("LLM_TURN_BUDGET_S", 7.0)
    LLM_CIRCUIT_FAILURES = _num("LLM_CIRCUIT_FAILURES", 5, int)
    LLM_CIRCUIT_OPEN_S = _num("LLM_CIRCUIT_OPEN_S", 60.0)
    # Free-tier providers may only see demo/test data: real citizen utterances are sent only when this is true.
    LLM_ALLOW_REAL_DATA = _flag("LLM_ALLOW_REAL_DATA", False)

    # Optional Langfuse tracing of LLM extraction (anvaya/llm/tracing.py). Off unless all three are set; then the SDK
    # is imported and turns that used the LLM are traced (input/output for demo/test data only, metadata otherwise).
    LANGFUSE_PUBLIC_KEY = os.environ.get("LANGFUSE_PUBLIC_KEY", "")
    LANGFUSE_SECRET_KEY = os.environ.get("LANGFUSE_SECRET_KEY", "")
    LANGFUSE_BASE_URL = os.environ.get("LANGFUSE_BASE_URL", "") or os.environ.get("LANGFUSE_HOST", "")
    LANGFUSE_TIMEOUT_S = _num("LANGFUSE_TIMEOUT_S", 2, int)  # export HTTP timeout; export runs in the background
    # 1 = `manage eval-extraction` also pushes the eval utterances as a Langfuse dataset and each run as an experiment.
    LANGFUSE_TRACE_EVAL = _flag("LANGFUSE_TRACE_EVAL", False)
    LANGFUSE_SPAN_EXPORTER = None  # tests only: a fake OpenTelemetry exporter in place of OTLP/HTTP
