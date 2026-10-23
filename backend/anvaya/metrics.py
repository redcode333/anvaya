"""Prometheus metrics. Labels are low-cardinality enums only — never profile values or IDs."""
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

HTTP_REQUESTS = Counter("anvaya_http_requests_total", "API requests", ["method", "route", "status"])
HTTP_LATENCY = Histogram("anvaya_http_request_duration_seconds", "API request latency", ["method", "route"],
                         buckets=(.005, .01, .025, .05, .1, .25, .5, 1, 2.5, 5))

EVALUATIONS = Counter("anvaya_eligibility_evaluations_total", "Screening runs", ["origin"])
OUTCOMES = Counter("anvaya_eligibility_outcomes_total", "Per-scheme screening outcomes", ["rule_id", "outcome"])
RULE_EVAL_SECONDS = Histogram("anvaya_rule_evaluation_seconds", "Deterministic rule evaluation time per screening",
                              buckets=(.0001, .0005, .001, .0025, .005, .01, .025, .05, .1))
CONFIRMATION_BLOCKS = Counter("anvaya_screening_blocked_total", "Screenings blocked until high-impact facts are confirmed")

TURNS = Counter("anvaya_conversation_turns_total", "Conversation turns", ["channel", "language"])
FACTS_EXTRACTED = Counter("anvaya_facts_extracted_total", "Candidate facts extracted", ["attribute"])
FACT_CORRECTIONS = Counter("anvaya_fact_corrections_total", "Citizen corrections of extracted facts", ["attribute"])

DRAFTS = Counter("anvaya_drafts_total", "Draft saves", ["action"])
CASE_TRANSITIONS = Counter("anvaya_case_transitions_total", "Case lifecycle transitions", ["action"])
IDEMPOTENT_REPLAYS = Counter("anvaya_idempotent_replays_total", "Requests answered from an idempotency key", ["scope"])
SYNC_EVENTS = Counter("anvaya_sync_events_total", "Offline outbox events received", ["status"])
SYNC_RESULT_CHANGED = Counter("anvaya_sync_result_changed_total", "Offline results that changed on online re-check")

LLM_CALLS = Counter("anvaya_llm_calls_total", "LLM extraction calls by provider and result", ["provider", "result"])
LLM_LATENCY = Histogram("anvaya_llm_latency_seconds", "LLM extraction call latency", ["provider"],
                        buckets=(.1, .25, .5, 1, 2, 3, 4, 5, 6, 8))
LLM_FALLBACKS = Counter("anvaya_llm_fallbacks_total", "Moves from one LLM provider to the next", ["from", "to"])
LLM_MERGE = Counter("anvaya_llm_merge_total", "LLM facts by merge outcome against deterministic extraction",
                    ["outcome"])

VOICE = Counter("anvaya_voice_requests_total", "Voice adapter calls", ["op", "result"])
AUTH = Counter("anvaya_auth_events_total", "Auth events", ["result"])
RATE_LIMITED = Counter("anvaya_code_lookups_rate_limited_total", "Case-code lookups rejected by rate limit", ["bucket"])
TEST_RUNS = Counter("anvaya_test_runs_total", "Official scenario runs", ["tc", "result"])

CASES_BY_STATUS = Gauge("anvaya_cases", "Cases by status (excludes test-runner cases)", ["status"])
CATALOGUE = Gauge("anvaya_catalogue_records", "Catalogue size", ["kind"])
ACTIVE_SESSIONS = Gauge("anvaya_active_sessions", "Sessions not ended or expired", ["mode"])


def refresh_gauges(db, now_iso: str) -> None:
    for status in ("PENDING_REVIEW", "CORRECTION_REQUESTED", "REVIEWED"):
        CASES_BY_STATUS.labels(status).set(0)
    for status, n in db.execute(
        "SELECT c.status, COUNT(*) FROM cases c JOIN sessions s ON s.session_id=c.session_id WHERE s.is_test=0 GROUP BY c.status"):
        CASES_BY_STATUS.labels(status).set(n)
    CATALOGUE.labels("schemes").set(db.execute("SELECT COUNT(*) FROM schemes").fetchone()[0])
    CATALOGUE.labels("curated_rules").set(db.execute("SELECT COUNT(*) FROM rules WHERE active=1").fetchone()[0])
    CATALOGUE.labels("rules_source_verified").set(
        db.execute("SELECT COUNT(*) FROM rules WHERE active=1 AND source_verified_at IS NOT NULL").fetchone()[0])
    for mode in ("personal", "kiosk"):
        ACTIVE_SESSIONS.labels(mode).set(db.execute(
            "SELECT COUNT(*) FROM sessions WHERE mode=? AND is_test=0 AND ended_at IS NULL AND expires_at > ?",
            (mode, now_iso)).fetchone()[0])


def render(db, now_iso: str) -> tuple[bytes, str]:
    refresh_gauges(db, now_iso)
    return generate_latest(), CONTENT_TYPE_LATEST
