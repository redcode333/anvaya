"""Schema and numbered migrations, applied at startup on SQLite and Postgres.

Each migration runs once and is recorded in schema_migrations; every step is also idempotent on its own (IF NOT EXISTS,
column checks), so a database created before schema_migrations existed is brought up to date safely. On Postgres the
migrations run under an advisory lock (several processes may start at once), and afterwards Row Level Security is
enabled on every table with no policies: Supabase's public REST API (anon / authenticated roles) can then read or
write nothing, while this backend connects as the tables' owner, which RLS does not restrict.

DDL is written for SQLite and translated for Postgres: TEXT → TEXT COLLATE "C" (byte order, as SQLite sorts),
REAL → DOUBLE PRECISION, BLOB → BYTEA, and "{seq}" → an identity column standing in for SQLite's implicit rowid.
"""
import re

from .db import Database, iso

SCHEMA_V1 = [
    """CREATE TABLE IF NOT EXISTS source_artifacts (
        artifact_id TEXT PRIMARY KEY,
        filename TEXT NOT NULL,
        sha256 TEXT NOT NULL,
        row_count INTEGER NOT NULL,
        imported_at TEXT NOT NULL,
        report_json TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS schemes (
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
    )""",
    "CREATE INDEX IF NOT EXISTS idx_schemes_state ON schemes(state)",
    "CREATE INDEX IF NOT EXISTS idx_schemes_level ON schemes(level)",
    """CREATE TABLE IF NOT EXISTS kg_nodes (
        node_id TEXT PRIMARY KEY,
        node_type TEXT NOT NULL,
        label TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS kg_edges (
        src TEXT NOT NULL,
        rel TEXT NOT NULL,
        dst TEXT NOT NULL,
        PRIMARY KEY (src, rel, dst)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_kg_edges_dst ON kg_edges(dst, rel)",
    """CREATE TABLE IF NOT EXISTS rules (
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
    )""",
    """CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL,
        display_name TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS auth_tokens (
        token_hash TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        expires_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS sessions (
        session_id TEXT PRIMARY KEY,
        mode TEXT NOT NULL,
        language TEXT NOT NULL,
        workflow_state TEXT NOT NULL,
        device_id TEXT,
        operator_id TEXT,
        is_test INTEGER NOT NULL DEFAULT 0,
        is_demo INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        ended_at TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS facts (
        {seq}
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
        superseded_by TEXT,
        confusable INTEGER NOT NULL DEFAULT 0,
        alternatives_json TEXT
    )""",
    "CREATE INDEX IF NOT EXISTS idx_facts_session ON facts(session_id, attribute)",
    """CREATE TABLE IF NOT EXISTS turns (
        turn_id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        language TEXT NOT NULL,
        utterance TEXT NOT NULL,
        channel TEXT NOT NULL,
        extracted_json TEXT NOT NULL,
        reply TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS doc_marks (
        session_id TEXT NOT NULL,
        doc_key TEXT NOT NULL,
        status TEXT NOT NULL,
        marked_by TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        PRIMARY KEY (session_id, doc_key)
    )""",
    """CREATE TABLE IF NOT EXISTS evaluations (
        {seq}
        eval_id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        bundle_version TEXT NOT NULL,
        created_at TEXT NOT NULL,
        fact_ids_json TEXT NOT NULL,
        results_json TEXT NOT NULL,
        origin TEXT NOT NULL DEFAULT 'online'
    )""",
    """CREATE TABLE IF NOT EXISTS drafts (
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
    )""",
    """CREATE TABLE IF NOT EXISTS cases (
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
    )""",
    """CREATE TABLE IF NOT EXISTS idempotency (
        scope TEXT NOT NULL,
        idem_key TEXT NOT NULL,
        response_json TEXT NOT NULL,
        status_code INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        PRIMARY KEY (scope, idem_key)
    )""",
    """CREATE TABLE IF NOT EXISTS sync_events (
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
    )""",
    """CREATE TABLE IF NOT EXISTS audit_events (
        {seq}
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
    )""",
    "CREATE INDEX IF NOT EXISTS idx_audit_case ON audit_events(case_id)",
    """CREATE TABLE IF NOT EXISTS test_runs (
        {seq}
        run_id TEXT PRIMARY KEY,
        tc_id TEXT NOT NULL,
        ran_at TEXT NOT NULL,
        passed INTEGER NOT NULL,
        evidence_json TEXT NOT NULL
    )""",
    # Machine translations from VerbX, so each text is translated once.
    """CREATE TABLE IF NOT EXISTS translations (
        source_lang TEXT NOT NULL,
        target_lang TEXT NOT NULL,
        source_text TEXT NOT NULL,
        translated_text TEXT NOT NULL,
        provider TEXT NOT NULL,
        model TEXT,
        created_at TEXT NOT NULL,
        PRIMARY KEY (source_lang, target_lang, source_text)
    )""",
    # Synthesized speech keyed by sha256(text, language, voice); the text itself is not stored. pinned=1 rows are the
    # prerendered fixed prompts (manage prerender-audio) and are kept; other rows may hold profile details read back
    # to a citizen and are removed by `manage cleanup` after ANVAYA_SESSION_TTL_HOURS.
    """CREATE TABLE IF NOT EXISTS tts_cache (
        cache_key TEXT PRIMARY KEY,
        language TEXT NOT NULL,
        voice TEXT NOT NULL,
        mime_type TEXT NOT NULL,
        audio BLOB NOT NULL,
        synth_ms INTEGER,
        pinned INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL
    )""",
    # LLM provider quota state, so an exhausted free tier stays skipped across restarts until its reset.
    """CREATE TABLE IF NOT EXISTS llm_provider_state (
        provider TEXT PRIMARY KEY,
        exhausted_until TEXT,
        day TEXT,
        requests_today INTEGER NOT NULL DEFAULT 0,
        last_result TEXT,
        updated_at TEXT NOT NULL
    )""",
    # Validated LLM extraction results keyed by sha256(provider + model + prompt); the prompt itself is not stored.
    """CREATE TABLE IF NOT EXISTS llm_cache (
        cache_key TEXT PRIMARY KEY,
        provider TEXT NOT NULL,
        model TEXT NOT NULL,
        prompt_version TEXT NOT NULL,
        response_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""",
]

# Columns added after the first release, for SQLite databases created before them: (table, column, DDL).
LATE_COLUMNS = [("facts", "confusable", "ALTER TABLE facts ADD COLUMN confusable INTEGER NOT NULL DEFAULT 0"),
                ("facts", "alternatives_json", "ALTER TABLE facts ADD COLUMN alternatives_json TEXT"),
                ("sessions", "is_demo", "ALTER TABLE sessions ADD COLUMN is_demo INTEGER NOT NULL DEFAULT 0")]

# Names of the in-memory caches' version rows (db.cached / db.bump).
CACHE_VERSIONS = ("catalogue", "tts")


def ddl(sql: str, dialect: str) -> str:
    if dialect == "sqlite":
        return sql.replace("{seq}", "")
    sql = sql.replace("{seq}", "seq BIGINT GENERATED ALWAYS AS IDENTITY,")
    sql = re.sub(r"\bTEXT\b", 'TEXT COLLATE "C"', sql)
    sql = re.sub(r"\bREAL\b", "DOUBLE PRECISION", sql)
    return re.sub(r"\bBLOB\b", "BYTEA", sql)


def _m1_initial_schema(db: Database) -> None:
    db.query_many([(ddl(s, db.dialect), ()) for s in SCHEMA_V1])


def _m2_late_columns(db: Database) -> None:
    if db.dialect == "postgres":
        db.query_many([(ddl(sql.replace("ADD COLUMN", "ADD COLUMN IF NOT EXISTS"), "postgres"), ())
                       for _, _, sql in LATE_COLUMNS])
        return
    tables = {t for t, _, _ in LATE_COLUMNS}
    have = {t: {r[1] for r in db.execute(f"PRAGMA table_info({t})")} for t in tables}
    for table, column, sql in LATE_COLUMNS:
        if column not in have[table]:
            db.execute(sql)


def _m3_lookup_indexes_and_versions(db: Database) -> None:
    """Indexes for per-session lookups, unique case codes, and the cache version table."""
    db.query_many([(s, ()) for s in (
        "CREATE INDEX IF NOT EXISTS idx_evaluations_session ON evaluations(session_id, created_at)",
        "CREATE INDEX IF NOT EXISTS idx_turns_session ON turns(session_id)",
        "CREATE INDEX IF NOT EXISTS idx_audit_session ON audit_events(session_id)",
        "CREATE INDEX IF NOT EXISTS idx_cases_session ON cases(session_id)",
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_cases_code_hash ON cases(code_hash)",
        ddl("CREATE TABLE IF NOT EXISTS data_versions (name TEXT PRIMARY KEY, version INTEGER NOT NULL)", db.dialect),
    )])
    db.executemany("INSERT INTO data_versions(name, version) VALUES (?, 1) ON CONFLICT DO NOTHING",
                   [(n,) for n in CACHE_VERSIONS])


MIGRATIONS = [
    (1, "initial schema", _m1_initial_schema),
    (2, "late columns: facts.confusable, facts.alternatives_json, sessions.is_demo", _m2_late_columns),
    (3, "lookup indexes, unique case codes, cache versions", _m3_lookup_indexes_and_versions),
]

ENABLE_RLS = """DO $$
DECLARE t record;
BEGIN
  FOR t IN SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
           WHERE n.nspname = current_schema() AND c.relkind IN ('r', 'p') AND NOT c.relrowsecurity LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t.relname);
  END LOOP;
END $$"""

TABLES_WITHOUT_RLS = """SELECT COUNT(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = current_schema() AND c.relkind IN ('r', 'p') AND NOT c.relrowsecurity"""


def migrate(db: Database) -> list[int]:
    """Apply pending migrations; returns the versions applied now. Safe to run from several processes at once."""
    applied_now = []
    with db.transaction():
        setup = [(ddl("CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, name TEXT NOT NULL,"
                      " applied_at TEXT NOT NULL)", db.dialect), ()),
                 ("SELECT version FROM schema_migrations", ())]
        if db.dialect == "postgres":
            schema = getattr(db.backend, "schema", None)
            setup = ([(f'CREATE SCHEMA IF NOT EXISTS "{schema}"', ())] if schema else []) + [
                ("SELECT pg_advisory_xact_lock(hashtext('anvaya.migrations'))", ())] + setup
        done = {r[0] for r in db.query_many(setup)[-1]}
        for version, name, step in MIGRATIONS:
            if version in done:
                continue
            step(db)
            db.execute("INSERT INTO schema_migrations(version, name, applied_at) VALUES (?,?,?)", (version, name, iso()))
            applied_now.append(version)
        if db.dialect == "postgres":
            db.execute(ENABLE_RLS)
    return applied_now


def rls_missing(db: Database) -> int:
    """Postgres: how many tables in our schema do not have Row Level Security enabled (0 = all protected)."""
    return db.execute(TABLES_WITHOUT_RLS).fetchone()[0]
