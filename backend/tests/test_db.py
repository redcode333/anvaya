"""Database layer on both dialects: SQL translation, migrations, Row Level Security, concurrency, restarts and the number
of queries each request makes. Runs on SQLite by default and on Postgres with TEST_DATABASE_URL set."""
import logging
import re
import threading

import pytest
from conftest import TEST_DATABASE_URL, db_config, on_postgres, start

from anvaya import create_app, ingest
from anvaya.db import connect, dispose, to_postgres, to_sqlite
from anvaya.migrations import MIGRATIONS, migrate, rls_missing

TC1 = ("I am 67 years old, a farmer in a village in Guntur, Andhra Pradesh. Family of 4, yearly income 60,000 rupees. "
       "We have a BPL card, I do not get any pension, I own 2 acres of land and have a bank account.")


def test_sql_is_translated_per_dialect():
    sql = "SELECT * FROM t WHERE a=? AND b LIKE ? AND c='x?%' ORDER BY ts, rowid FOR UPDATE OF t"
    assert to_postgres(sql) == ("SELECT * FROM t WHERE a=%s AND b ILIKE %s AND c='x?%%' ORDER BY ts, seq"
                                " FOR UPDATE OF t")
    assert to_sqlite(sql) == "SELECT * FROM t WHERE a=? AND b LIKE ? AND c='x?%' ORDER BY ts, rowid"
    assert to_sqlite("BEGIN") == "BEGIN IMMEDIATE"


def test_app_runs_on_the_configured_dialect(app, client):
    r = client.get("/api/v1/ready").json
    assert r["db"]["backend"] == ("postgres" if on_postgres() else "sqlite")
    assert r["db"]["status"] == "ok" and r["ready"] is True
    if on_postgres():
        assert r["db"]["rls"] == "ok"
        assert TEST_DATABASE_URL.split("@")[-1] not in str(r)  # never the URL, not even the host


def test_migrations_are_recorded_and_idempotent(app):
    db = connect(app.config)
    try:
        assert migrate(db) == []
        assert [r[0] for r in db.execute("SELECT version FROM schema_migrations ORDER BY version")] == \
            [v for v, _, _ in MIGRATIONS]
    finally:
        db.close()


def test_manage_init_is_idempotent(app):
    """Re-running init skips the unchanged catalogue, upserts rules (keeping source verification), adds no users."""
    db = connect(app.config)
    try:
        before = db.query_many([("SELECT COUNT(*) FROM schemes", ()), ("SELECT COUNT(*) FROM rules", ()),
                                ("SELECT COUNT(*) FROM users", ()), ("SELECT COUNT(*) FROM source_artifacts", ())])
        before = [r.fetchone()[0] for r in before]
        db.execute("UPDATE rules SET source_verified_at='2026-01-01T00:00:00+00:00', source_verified_by='admin'"
                   " WHERE rule_id='R_PM_KISAN'")
        db.commit()
        res = ingest.bootstrap(db, app.config["DATASET_CSV"], app.config["GOLDEN_RULES"], app.config["RULE_BUNDLE_VERSION"])
        assert res["catalogue"]["skipped"] is True
        after = db.query_many([("SELECT COUNT(*) FROM schemes", ()), ("SELECT COUNT(*) FROM rules", ()),
                               ("SELECT COUNT(*) FROM users", ()), ("SELECT COUNT(*) FROM source_artifacts", ())])
        assert [r.fetchone()[0] for r in after] == before
        row = db.execute("SELECT source_verified_by FROM rules WHERE rule_id='R_PM_KISAN'").fetchone()
        assert row[0] == "admin"
    finally:
        db.close()


@pytest.mark.skipif(not on_postgres(), reason="Row Level Security is a Postgres feature")
def test_rls_blocks_supabase_api_roles(app):
    """Every table has RLS on and no policy: a role like Supabase's `anon`, even with table grants, sees and writes
    nothing. The backend (table owner) is not restricted."""
    import psycopg
    schema = app.config["DB_SCHEMA"]
    db = connect(app.config)
    try:
        assert rls_missing(db) == 0
        assert db.execute("SELECT COUNT(*) FROM pg_policies WHERE schemaname=?", (schema,)).fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM schemes").fetchone()[0] > 0
    finally:
        db.close()
    with psycopg.connect(TEST_DATABASE_URL, autocommit=True) as conn:
        conn.execute("DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon_test') THEN"
                     " CREATE ROLE anon_test NOLOGIN; END IF; END $$")
        conn.execute(f'GRANT USAGE ON SCHEMA "{schema}" TO anon_test')
        conn.execute(f'GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA "{schema}" TO anon_test')
        conn.execute(f'SET search_path TO "{schema}"')
        conn.execute("SET ROLE anon_test")
        try:
            assert conn.execute("SELECT COUNT(*) FROM schemes").fetchone()[0] == 0
            assert conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                conn.execute("INSERT INTO sessions(session_id, mode, language, workflow_state, created_at, expires_at)"
                             " VALUES ('x', 'personal', 'en', 'SESSION_ACTIVE', 'a', 'b')")
        finally:
            conn.execute("RESET ROLE")
            conn.execute(f'REVOKE ALL ON ALL TABLES IN SCHEMA "{schema}" FROM anon_test')
            conn.execute(f'REVOKE USAGE ON SCHEMA "{schema}" FROM anon_test')


def _draft(client, utterance=TC1):
    sid = start(client, utterance)
    ev = client.post(f"/api/v1/sessions/{sid}/eligibility/evaluate").json
    scheme = next(r["scheme_id"] for r in ev["results"] if r["outcome"] != "MISMATCH")
    d = client.post(f"/api/v1/sessions/{sid}/drafts", json={"scheme_id": scheme}, headers={"Idempotency-Key": f"d-{sid}"})
    assert d.status_code == 201, d.json
    return sid, d.json["draft_id"]


def _parallel(app, n, fn):
    """Run fn(client) in n threads that start together; returns the responses."""
    barrier, out = threading.Barrier(n), [None] * n

    def worker(i):
        c = app.test_client()
        barrier.wait()
        out[i] = fn(c)
    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(60)
    return out


def _cases_for(app, draft_id):
    db = connect(app.config)
    try:
        return db.execute("SELECT case_id FROM cases WHERE draft_id=?", (draft_id,)).fetchall()
    finally:
        db.close()


def test_ten_parallel_identical_handoffs_create_exactly_one_case(app, client):
    sid, draft_id = _draft(client)
    body = {"consent": {"share_with_reviewer": True}}
    res = _parallel(app, 10, lambda c: c.post(f"/api/v1/drafts/{draft_id}/handoff", json=body,
                                               headers={"Idempotency-Key": "same-key", "X-Session-Id": sid}))
    assert [r.status_code for r in res] == [201] * 10, [r.json for r in res]
    assert len({r.json["case_id"] for r in res}) == 1
    assert len({r.json["code"] for r in res}) == 1  # replays return the first response, so the code stays valid
    assert sum(1 for r in res if r.json.get("idempotent_replay")) == 9
    assert len(_cases_for(app, draft_id)) == 1
    assert client.post("/api/v1/cases/status", json={"code": res[0].json["code"]}).status_code == 200


def test_parallel_handoffs_with_different_keys_still_make_one_case(app, client):
    sid, draft_id = _draft(client)
    body = {"consent": {"share_with_reviewer": True}}
    res = _parallel(app, 6, lambda c: c.post(f"/api/v1/drafts/{draft_id}/handoff", json=body,
                                              headers={"Idempotency-Key": f"k-{threading.get_ident()}",
                                                       "X-Session-Id": sid}))
    assert [r.status_code for r in res] == [201] * 6, [r.json for r in res]
    assert len({r.json["case_id"] for r in res}) == 1 and len(_cases_for(app, draft_id)) == 1


def test_parallel_identical_draft_requests_make_one_draft(app, client):
    sid = start(client, TC1)
    ev = client.post(f"/api/v1/sessions/{sid}/eligibility/evaluate").json
    scheme = next(r["scheme_id"] for r in ev["results"] if r["outcome"] != "MISMATCH")
    res = _parallel(app, 8, lambda c: c.post(f"/api/v1/sessions/{sid}/drafts", json={"scheme_id": scheme},
                                              headers={"Idempotency-Key": "one-draft"}))
    assert [r.status_code for r in res] == [201] * 8
    assert len({r.json["draft_id"] for r in res}) == 1 and {r.json["version"] for r in res} == {1}


def test_parallel_identical_sync_events_apply_once(app, client):
    event = {"event_id": "EVT-par-1", "idempotency_key": "IDEM-par-1", "type": "offline_draft", "schema_version": 1,
             "bundle_version": app.config["RULE_BUNDLE_VERSION"],
             "payload": {"language": "en", "scheme_id": "680a02cb41f9fb65ecb3453f",
                         "facts": {"state": "Punjab", "age": 70, "bpl": True, "receives_other_pension": False},
                         "documents": {"bpl_card": "available"}, "local_result": {"outcome": "PROVISIONAL"},
                         "consent": {"share_with_reviewer": True}}}
    res = _parallel(app, 5, lambda c: c.post("/api/v1/sync/events", json={"device_id": "kiosk-par", "events": [event]}))
    statuses = sorted(r.json["results"][0]["status"] for r in res)
    assert statuses.count("duplicate") == 4 and len(set(statuses)) == 2, statuses
    db = connect(app.config)
    try:
        assert db.execute("SELECT COUNT(*) FROM sessions WHERE device_id='kiosk-par'").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM sync_events WHERE event_id='EVT-par-1'").fetchone()[0] == 1
    finally:
        db.close()


def test_data_survives_an_app_restart(tmp_path):
    """A case created before a restart is found after it (on Postgres: a new process and pool on the same schema)."""
    cfg = {**db_config(tmp_path / "restart.db"), "TESTING": True, "LLM_EXTRACTION": False, "LLM_PROVIDERS": [],
           "LANGFUSE_PUBLIC_KEY": "", "LANGFUSE_SECRET_KEY": "", "LANGFUSE_BASE_URL": ""}
    first = create_app(dict(cfg))
    db = connect(first.config)
    ingest.bootstrap(db, first.config["DATASET_CSV"], first.config["GOLDEN_RULES"], first.config["RULE_BUNDLE_VERSION"])
    db.close()
    c = first.test_client()
    sid, draft_id = _draft(c)
    code = c.post(f"/api/v1/drafts/{draft_id}/handoff", json={"consent": {"share_with_reviewer": True}},
                  headers={"Idempotency-Key": "restart", "X-Session-Id": sid}).json["code"]
    dispose(first.config)  # closes the pool: nothing is kept in memory across the "restart"

    second = create_app(dict(cfg))
    r = second.test_client().post("/api/v1/cases/status", json={"code": code})
    assert r.status_code == 200 and r.json["status"] == "PENDING_REVIEW"
    dispose(second.config)


# ---------------------------------------------------------------- queries per request

def _counts(caplog, fn):
    caplog.clear()
    with caplog.at_level(logging.INFO, logger="anvaya.http"):
        r = fn()
    line = [rec.getMessage() for rec in caplog.records if rec.name == "anvaya.http"][-1]
    q, rt = re.search(r"db_queries=(\d+) db_roundtrips=(\d+) db_ms=[\d.]+", line).groups()
    return r, int(q), int(rt)


def test_queries_per_request_stay_within_budget(app, client, caplog, monkeypatch):
    """Budgets for the main citizen path on a warm server (queries = statements without BEGIN/COMMIT; a batched
    insert counts once). Right after a catalogue change, the next request also re-checks versions and reloads rules."""
    from anvaya.db import backend
    monkeypatch.setattr(backend(app.config), "cache_check_s", 3600)  # no periodic version check mid-test
    client.get("/api/v1/schemes/facets")  # warm the in-memory caches
    client.get("/api/v1/sync/bundle")

    r, q, rt = _counts(caplog, lambda: client.post("/api/v1/sessions", json={"mode": "personal", "language": "en"}))
    sid = r.json["session_id"]
    assert (q, rt) == (2, 1)
    r, q, rt = _counts(caplog, lambda: client.post(f"/api/v1/sessions/{sid}/turns", json={"utterance": TC1}))
    assert r.status_code == 200 and q <= 6 and rt <= 2, (q, rt)
    pending = client.post(f"/api/v1/sessions/{sid}/profile/confirm-all").json["needs_confirmation"]
    for fid in pending:
        client.patch(f"/api/v1/sessions/{sid}/profile/facts/{fid}", json={"confirmed": True})
    r, q, rt = _counts(caplog, lambda: client.post(f"/api/v1/sessions/{sid}/eligibility/evaluate"))
    assert r.status_code == 200 and q <= 7 and rt <= 2, (q, rt)
    scheme = next(x["scheme_id"] for x in r.json["results"] if x["outcome"] != "MISMATCH")
    r, q, rt = _counts(caplog, lambda: client.post(f"/api/v1/sessions/{sid}/drafts", json={"scheme_id": scheme},
                                                   headers={"Idempotency-Key": "budget-d"}))
    assert r.status_code == 201 and q <= 10 and rt <= 4, (q, rt)
    r, q, rt = _counts(caplog, lambda: client.post(f"/api/v1/drafts/{r.json['draft_id']}/handoff",
                                                   json={"consent": {"share_with_reviewer": True}},
                                                   headers={"Idempotency-Key": "budget-h", "X-Session-Id": sid}))
    assert r.status_code == 201 and q <= 11 and rt <= 3, (q, rt)
