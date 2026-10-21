import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import current_app, g

SCHEMA = """
CREATE TABLE IF NOT EXISTS source_artifacts (
    artifact_id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    row_count INTEGER NOT NULL,
    imported_at TEXT NOT NULL,
    report_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS schemes (
    scheme_id TEXT PRIMARY KEY,
    slug TEXT,
    name TEXT NOT NULL,
    short_title TEXT,
    state_raw TEXT,
    state TEXT,
    level_raw TEXT,
    level TEXT,
    department TEXT,
    categories TEXT,
    subcategories TEXT,
    tags TEXT,
    beneficiaries TEXT,
    brief_description TEXT,
    description TEXT,
    benefits TEXT,
    eligibility_text TEXT,
    application_process TEXT,
    documents_text TEXT,
    source_urls_json TEXT,
    source_url TEXT,
    faqs TEXT,
    source_artifact_id TEXT,
    imported_at TEXT,
    retrieved_at TEXT,
    verified_at TEXT,
    review_status TEXT NOT NULL,
    confidence TEXT NOT NULL,
    quality_flags_json TEXT NOT NULL,
    search_text TEXT
);
CREATE INDEX IF NOT EXISTS idx_schemes_state ON schemes(state);
CREATE INDEX IF NOT EXISTS idx_schemes_level ON schemes(level);

CREATE TABLE IF NOT EXISTS kg_nodes (
    node_id TEXT PRIMARY KEY,
    node_type TEXT NOT NULL,
    label TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS kg_edges (
    src TEXT NOT NULL,
    rel TEXT NOT NULL,
    dst TEXT NOT NULL,
    PRIMARY KEY (src, rel, dst)
);
CREATE INDEX IF NOT EXISTS idx_kg_edges_dst ON kg_edges(dst, rel);

CREATE TABLE IF NOT EXISTS rules (
    rule_id TEXT PRIMARY KEY,
    scheme_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    bundle_version TEXT NOT NULL,
    rule_json TEXT NOT NULL,
    review_status TEXT NOT NULL,
    reviewed_at TEXT,
    source_verified_at TEXT,
    source_verified_by TEXT,
    active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL,
    display_name TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS auth_tokens (
    token_hash TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    mode TEXT NOT NULL,
    language TEXT NOT NULL,
    workflow_state TEXT NOT NULL,
    device_id TEXT,
    operator_id TEXT,
    is_test INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    ended_at TEXT
);

CREATE TABLE IF NOT EXISTS facts (
    fact_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    attribute TEXT NOT NULL,
    value_json TEXT NOT NULL,
    raw_text TEXT,
    source TEXT NOT NULL,
    confidence REAL NOT NULL,
    confirmed INTEGER NOT NULL DEFAULT 0,
    inferred INTEGER NOT NULL DEFAULT 0,
    note TEXT,
    captured_at TEXT NOT NULL,
    confirmed_at TEXT,
    superseded_by TEXT
);
CREATE INDEX IF NOT EXISTS idx_facts_session ON facts(session_id, attribute);

CREATE TABLE IF NOT EXISTS turns (
    turn_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    language TEXT NOT NULL,
    utterance TEXT NOT NULL,
    channel TEXT NOT NULL,
    extracted_json TEXT NOT NULL,
    reply TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS doc_marks (
    session_id TEXT NOT NULL,
    doc_key TEXT NOT NULL,
    status TEXT NOT NULL,
    marked_by TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (session_id, doc_key)
);

CREATE TABLE IF NOT EXISTS evaluations (
    eval_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    bundle_version TEXT NOT NULL,
    created_at TEXT NOT NULL,
    fact_ids_json TEXT NOT NULL,
    results_json TEXT NOT NULL,
    origin TEXT NOT NULL DEFAULT 'online'
);

CREATE TABLE IF NOT EXISTS drafts (
    draft_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    scheme_id TEXT NOT NULL,
    eval_id TEXT,
    version INTEGER NOT NULL,
    fields_json TEXT NOT NULL,
    status TEXT NOT NULL,
    origin TEXT NOT NULL DEFAULT 'online',
    bundle_version TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (session_id, scheme_id)
);

CREATE TABLE IF NOT EXISTS cases (
    case_id TEXT PRIMARY KEY,
    draft_id TEXT UNIQUE NOT NULL,
    session_id TEXT NOT NULL,
    code_hash TEXT,
    code_expires_at TEXT,
    consent_json TEXT NOT NULL,
    status TEXT NOT NULL,
    review_outcome TEXT,
    reviewer_note TEXT,
    language TEXT NOT NULL,
    origin TEXT NOT NULL DEFAULT 'online',
    recheck_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS idempotency (
    scope TEXT NOT NULL,
    idem_key TEXT NOT NULL,
    response_json TEXT NOT NULL,
    status_code INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (scope, idem_key)
);

CREATE TABLE IF NOT EXISTS sync_events (
    event_id TEXT PRIMARY KEY,
    device_id TEXT NOT NULL,
    idempotency_key TEXT UNIQUE NOT NULL,
    session_id TEXT,
    event_type TEXT NOT NULL,
    local_created_at TEXT,
    bundle_version TEXT,
    rule_version TEXT,
    schema_version INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    server_result_json TEXT NOT NULL,
    received_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_events (
    event_id TEXT PRIMARY KEY,
    actor_id TEXT NOT NULL,
    actor_role TEXT NOT NULL,
    case_id TEXT,
    session_id TEXT,
    action TEXT NOT NULL,
    ts TEXT NOT NULL,
    request_id TEXT,
    object_version INTEGER,
    details_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_case ON audit_events(case_id);

CREATE TABLE IF NOT EXISTS test_runs (
    run_id TEXT PRIMARY KEY,
    tc_id TEXT NOT NULL,
    ran_at TEXT NOT NULL,
    passed INTEGER NOT NULL,
    evidence_json TEXT NOT NULL
);
"""


def now() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime | None = None) -> str:
    return (dt or now()).isoformat(timespec="seconds")


def iso_in(hours: float) -> str:
    return iso(now() + timedelta(hours=hours))


def parse_iso(s: str | None) -> datetime | None:
    return datetime.fromisoformat(s) if s else None


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True)


def connect(path: str) -> sqlite3.Connection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = connect(current_app.config["DB_PATH"])
    return g.db


def close_db(_exc=None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def row_to_dict(row: sqlite3.Row | None) -> dict | None:
    return dict(row) if row is not None else None
