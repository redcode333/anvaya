"""Prometheus metrics. Labels are low-cardinality enums only — never profile values or IDs."""
from datetime import datetime

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

HTTP_REQUESTS = Counter("anvaya_http_requests_total", "API requests", ["method", "route", "status"])
HTTP_LATENCY = Histogram("anvaya_http_request_duration_seconds", "API request latency", ["method", "route"],
                         buckets=(.005, .01, .025, .05, .1, .25, .5, 1, 2.5, 5))

# Statements per API request (BEGIN/COMMIT not counted; a batched insert counts once) and network round trips per
# request (queued writes, several reads, or writes + COMMIT travel together in one round trip).
DB_QUERIES = Histogram("anvaya_db_queries_per_request", "Database queries per API request", ["method", "route"],
                       buckets=(0, 1, 2, 3, 4, 5, 6, 8, 10, 15, 20, 30, 50))
DB_ROUNDTRIPS = Histogram("anvaya_db_roundtrips_per_request", "Database round trips per API request",
                          ["method", "route"], buckets=(0, 1, 2, 3, 4, 5, 6, 8, 10, 15, 20))

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
UPLOADS = Counter("anvaya_document_uploads_total", "Document uploads by result", ["result"])
RATE_LIMITED = Counter("anvaya_code_lookups_rate_limited_total", "Case-code lookups rejected by rate limit", ["bucket"])
JOB_RUNS = Counter("anvaya_job_runs_total", "Background job runs", ["job", "status"])
JOB_LAST_SUCCESS = Gauge("anvaya_job_last_success_timestamp", "Unix time of the last successful run of a job", ["job"])
TEST_RUNS = Counter("anvaya_test_runs_total", "Official scenario runs", ["tc", "result"])

CASES_BY_STATUS = Gauge("anvaya_cases", "Cases by status (excludes test-runner cases)", ["status"])
CATALOGUE = Gauge("anvaya_catalogue_records", "Catalogue size", ["kind"])
ACTIVE_SESSIONS = Gauge("anvaya_active_sessions", "Sessions not ended or expired", ["mode"])


def refresh_gauges(db, now_iso: str) -> None:
    cases, schemes, rules, verified, active, last_ok = db.query_many([
        ("SELECT c.status, COUNT(*) FROM cases c JOIN sessions s ON s.session_id=c.session_id WHERE s.is_test=0"
         " GROUP BY c.status", ()),
        ("SELECT COUNT(*) FROM schemes", ()),
        ("SELECT COUNT(*) FROM rules WHERE active=1", ()),
        ("SELECT COUNT(*) FROM rules WHERE active=1 AND source_verified_at IS NOT NULL", ()),
        ("SELECT mode, COUNT(*) FROM sessions WHERE is_test=0 AND ended_at IS NULL AND expires_at > ? GROUP BY mode",
         (now_iso,)),
        # The server sleeps and restarts, so the gauge is rebuilt from the job_runs table rather than kept in memory.
        ("SELECT job, MAX(finished_at) FROM job_runs WHERE status='success' GROUP BY job", ()),
    ])
    for job, finished in last_ok.fetchall():
        JOB_LAST_SUCCESS.labels(job).set(datetime.fromisoformat(finished).timestamp())
    for status in ("PENDING_REVIEW", "CORRECTION_REQUESTED", "REVIEWED"):
        CASES_BY_STATUS.labels(status).set(0)
    for status, n in cases:
        CASES_BY_STATUS.labels(status).set(n)
    CATALOGUE.labels("schemes").set(schemes.fetchone()[0])
    CATALOGUE.labels("curated_rules").set(rules.fetchone()[0])
    CATALOGUE.labels("rules_source_verified").set(verified.fetchone()[0])
    by_mode = dict(active.fetchall())
    for mode in ("personal", "kiosk"):
        ACTIVE_SESSIONS.labels(mode).set(by_mode.get(mode, 0))


def render(db, now_iso: str) -> tuple[bytes, str]:
    refresh_gauges(db, now_iso)
    return generate_latest(), CONTENT_TYPE_LATEST
