"""Database-backed rate limits, scheduled jobs (/internal/jobs/run, job_runs, locks) and cache headers."""
import pytest

from anvaya import create_app, jobs, ratelimit
from anvaya.db import connect
from conftest import db_config, staff

TOKEN = "job-token-for-tests"


@pytest.fixture(autouse=True)
def no_storage(monkeypatch):
    """Other tests leave uploads behind and Supabase Storage is not reachable from tests: retention would fail on them."""
    monkeypatch.setattr("anvaya.documents.delete_uploads", lambda db, uploads: 0)


@pytest.fixture()
def job_app(app, config):
    config(INTERNAL_JOBS_TOKEN=TOKEN)
    return app


def call(client, token=TOKEN, job="retention"):
    h = {"X-Internal-Token": token} if token is not None else {}
    return client.post("/internal/jobs/run", json={"job": job}, headers=h)


# ---------------------------------------------------------------- jobs endpoint

def test_jobs_endpoint_404_when_token_unset(client, config):
    config(INTERNAL_JOBS_TOKEN="")
    assert call(client, TOKEN).status_code == 404


def test_jobs_endpoint_requires_the_token_not_user_auth(client, job_app):
    assert call(client, None).status_code == 401
    assert call(client, "wrong").status_code == 401
    assert client.post("/internal/jobs/run", json={"job": "all"}, headers=staff("admin")).status_code == 401
    assert call(client, job="nope").status_code == 422


def test_jobs_run_is_recorded_and_visible_to_admin(client, job_app):
    r = call(client, job="all")
    assert r.status_code == 200 and [x["job"] for x in r.json["runs"]] == ["retention", "cleanup"]
    assert {x["status"] for x in r.json["runs"]} == {"success"}
    runs = client.get("/api/v1/admin/jobs", headers=staff("admin")).json["runs"]
    assert {"retention", "cleanup"} <= {x["job"] for x in runs}
    assert runs[0]["finished_at"] and runs[0]["trigger"] == "http"
    assert client.get("/api/v1/admin/jobs", headers=staff("reviewer")).status_code == 403
    metrics = client.get("/metrics").data
    assert b'anvaya_job_runs_total{job="retention",status="success"}' in metrics
    assert b'anvaya_job_last_success_timestamp{job="retention"}' in metrics


def test_jobs_are_idempotent(client, job_app):
    first, second = call(client).json["runs"][0], call(client).json["runs"][0]
    assert first["status"] == second["status"] == "success" and second["counts"].get("unsaved_sessions") == 0


def test_overlapping_run_is_skipped(app, client, job_app):
    db, other = connect(app.config), connect(app.config)
    try:
        assert jobs._acquire(db, "retention")          # another run holds the lock
        assert not jobs._acquire(other, "retention")
        assert call(client).json["runs"][0]["status"] == "skipped"
        jobs._release(db, "retention")
    finally:
        db.close()
        other.close()
    assert call(client).json["runs"][0]["status"] == "success"


def test_ready_warns_when_retention_is_stale(app, client):
    db = connect(app.config)
    try:
        db.execute("DELETE FROM job_runs")
        db.commit()
        assert any("never succeeded" in x for x in client.get("/api/v1/ready").json["warnings"])
        db.execute("INSERT INTO job_runs(run_id, job, trigger, started_at, finished_at, status, counts_json)"
                   " VALUES ('JOB_old','retention','http','2020-01-01T00:00:00+00:00','2020-01-01T00:00:01+00:00',"
                   "'success','{}')")
        db.commit()
        assert any("not succeeded in 26 hours" in x for x in client.get("/api/v1/ready").json["warnings"])
    finally:
        db.close()
    jobs.run(app, "retention", "test")
    assert not any("retention" in x for x in client.get("/api/v1/ready").json["warnings"])


# ---------------------------------------------------------------- rate limits in the database

def _statuses(app, path, body, ip, n):
    c = app.test_client()
    return [c.post(path, json=body, environ_base={"REMOTE_ADDR": ip}).status_code for _ in range(n)]


def test_limit_survives_an_app_restart(tmp_path):
    overrides = {**db_config(tmp_path / "restart.db"), "TESTING": True, "SESSION_CREATE_LIMIT_PER_MIN": 2}
    body = {"mode": "personal"}
    assert _statuses(create_app(overrides), "/api/v1/sessions", body, "192.0.2.90", 3) == [201, 201, 429]
    restarted = create_app(overrides)  # a new process: nothing in memory
    assert _statuses(restarted, "/api/v1/sessions", body, "192.0.2.90", 1) == [429]


def test_two_instances_share_one_limit(tmp_path):
    overrides = {**db_config(tmp_path / "shared.db"), "TESTING": True, "SESSION_CREATE_LIMIT_PER_MIN": 4}
    a, b = create_app(overrides), create_app(overrides)
    out = []
    for i in range(6):
        out += _statuses(a if i % 2 == 0 else b, "/api/v1/sessions", {"mode": "personal"}, "192.0.2.91", 1)
    assert out == [201, 201, 201, 201, 429, 429]


def test_failed_pin_attempts_survive_restart(tmp_path):
    overrides = {**db_config(tmp_path / "pin.db"), "TESTING": True, "SESSION_CREATE_LIMIT_PER_MIN": 1000}
    body = {"code": "PSP-AAAA-AAAA", "pin": "4826"}
    assert _statuses(create_app(overrides), "/api/v1/passport/resume", body, "192.0.2.92", 5) == [401] * 5
    assert _statuses(create_app(overrides), "/api/v1/passport/resume", body, "192.0.2.92", 1) == [429]


def test_expired_counters_are_deleted_by_retention(app):
    db = connect(app.config)
    try:
        db.execute("INSERT INTO rate_limits(bucket, window_start, hits, expires_at) VALUES ('x:old', 1, 3, 60)")
        now = ratelimit.now_s()
        db.execute("INSERT INTO rate_limits(bucket, window_start, hits, expires_at) VALUES ('x:new', ?, 3, ?)",
                   (now, now + 600))
        db.commit()
    finally:
        db.close()
    jobs.run(app, "retention", "test")
    db = connect(app.config)
    try:
        left = {r[0] for r in db.execute("SELECT bucket FROM rate_limits WHERE bucket LIKE 'x:%'")}
    finally:
        db.close()
    assert left == {"x:new"}


# ---------------------------------------------------------------- cache headers

def test_cache_headers(client, tmp_path, monkeypatch):
    assert client.get("/api/v1/health").headers["Cache-Control"] == "no-store"
    assert client.post("/internal/jobs/run", json={}).headers["Cache-Control"] == "no-store"
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>x</title>" + "x" * 2000)
    (dist / "assets" / "index-abc123.js").write_text("console.log(1);" * 200)
    (dist / "sw.js").write_text("//")
    monkeypatch.setenv("ANVAYA_FRONTEND_DIST", str(dist))
    web = create_app({**db_config(tmp_path / "web.db"), "TESTING": True}).test_client()
    assert web.get("/assets/index-abc123.js").headers["Cache-Control"] == "public, max-age=31536000, immutable"
    assert web.get("/").headers["Cache-Control"] == "no-cache"
    assert web.get("/sw.js").headers["Cache-Control"] == "no-cache"
    assert web.get("/assets/missing-0000.js").status_code == 404
    zipped = web.get("/assets/index-abc123.js", headers={"Accept-Encoding": "gzip"})
    assert zipped.headers.get("Content-Encoding") == "gzip" and zipped.headers["Cache-Control"].endswith("immutable")


def test_service_worker_never_caches_api_or_documents():
    from pathlib import Path
    sw = (Path(__file__).parents[2] / "frontend" / "public" / "sw.js").read_text(encoding="utf-8")
    assert '"/api/"' in sw and "url.origin !== self.location.origin" in sw and "no-store" in sw
