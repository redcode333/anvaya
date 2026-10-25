"""Scheduled jobs for a server that sleeps: `retention` (expired data, files, rate-limit counters) and `cleanup`
(ended sessions, cached audio, stale sign-in state, old job records). Both are idempotent deletes.

They run from three places: the hourly in-app timer, POST /internal/jobs/run (called by the GitHub Actions cron, which
also wakes the server) and `python -m anvaya.manage cleanup`. A lock keeps two runs of a job from overlapping: a
Postgres advisory lock, or on SQLite a row in job_locks that expires after LOCK_TTL. Every run is recorded in job_runs
(counts only, never personal data)."""
import logging
import time
from datetime import timedelta

from . import metrics
from .db import connect, dumps, iso, new_id, now

log = logging.getLogger("anvaya.jobs")
JOBS = ("retention", "cleanup")
LOCK_TTL = timedelta(minutes=15)  # SQLite lock rows only: a crashed run frees its lock after this
JOB_RUN_KEEP_DAYS = 90
READY_WARN_AFTER_HOURS = 26


def _retention(db, app) -> dict:
    from .accounts import purge_expired
    return purge_expired(db, app.config)


def _cleanup(db, app) -> dict:
    from .voice import purge_audio
    ended = db.execute("UPDATE sessions SET ended_at=? WHERE ended_at IS NULL AND expires_at < ?", (iso(), iso())).rowcount
    audio = purge_audio(db, app.config["SESSION_TTL_HOURS"])
    oidc = db.execute("DELETE FROM oidc_states WHERE expires_at < ?", (iso(),)).rowcount
    old = db.execute("DELETE FROM job_runs WHERE started_at < ?", (iso(now() - timedelta(days=JOB_RUN_KEEP_DAYS)),)).rowcount
    db.commit()
    return {"sessions_expired": ended, "audio_clips_removed": audio, "oidc_states_removed": oidc,
            "job_runs_removed": old}


_FUNCS = {"retention": _retention, "cleanup": _cleanup}


def _lock_id(job: str) -> str:
    return f"anvaya.job.{job}"


def _acquire(db, job: str) -> bool:
    if db.dialect == "postgres":
        return bool(db.execute("SELECT pg_try_advisory_lock(hashtext(?))", (_lock_id(job),)).fetchone()[0])
    row = db.execute(
        "INSERT INTO job_locks(name, locked_until) VALUES (?,?) ON CONFLICT (name) DO UPDATE SET locked_until=excluded.locked_until"
        " WHERE job_locks.locked_until < ? RETURNING name", (job, iso(now() + LOCK_TTL), iso())).fetchone()
    return row is not None


def _release(db, job: str) -> None:
    if db.dialect == "postgres":
        db.execute("SELECT pg_advisory_unlock(hashtext(?))", (_lock_id(job),)).fetchone()
    else:
        db.execute("DELETE FROM job_locks WHERE name=?", (job,))
        db.commit()


def run(app, job: str, trigger: str = "manual") -> dict:
    """Run one job (own connection, own app context). Returns {job, status, counts, run_id}; status is `success`,
    `failed` or `skipped` (another run of the same job holds the lock)."""
    if job not in _FUNCS:
        raise ValueError(job)
    db = connect(app.config)
    try:
        if not _acquire(db, job):
            metrics.JOB_RUNS.labels(job, "skipped").inc()
            return {"job": job, "status": "skipped", "counts": {}, "run_id": None}
        run_id, started = new_id("JOB"), iso()
        db.execute("INSERT INTO job_runs(run_id, job, trigger, started_at, status, counts_json) VALUES (?,?,?,?,?,?)",
                   (run_id, job, trigger, started, "running", "{}"))
        db.commit()
        status, counts = "success", {}
        try:
            with app.app_context():
                counts = _FUNCS[job](db, app)
        except Exception as e:  # noqa: BLE001 - recorded; the next run retries (the jobs are idempotent)
            db.rollback()
            status, counts = "failed", {"error": type(e).__name__}
            log.warning("job %s failed (%s)", job, type(e).__name__)
        finally:
            db.execute("UPDATE job_runs SET finished_at=?, status=?, counts_json=? WHERE run_id=?",
                       (iso(), status, dumps(counts), run_id))
            db.commit()
            _release(db, job)
        metrics.JOB_RUNS.labels(job, status).inc()
        if status == "success":
            metrics.JOB_LAST_SUCCESS.labels(job).set(time.time())
            if any(v for v in counts.values()):
                log.info("job %s: %s", job, counts)  # counts only
        return {"job": job, "status": status, "counts": counts, "run_id": run_id}
    finally:
        db.close()


def run_all(app, job: str, trigger: str = "manual") -> list[dict]:
    return [run(app, j, trigger) for j in (JOBS if job == "all" else (job,))]


def recent_runs(db, limit: int = 30) -> list[dict]:
    import json
    return [{"run_id": r["run_id"], "job": r["job"], "trigger": r["trigger"], "started_at": r["started_at"],
             "finished_at": r["finished_at"], "status": r["status"], "counts": json.loads(r["counts_json"])}
            for r in db.execute("SELECT * FROM job_runs ORDER BY started_at DESC, run_id DESC LIMIT ?", (limit,))]


def last_success(db) -> dict[str, str]:
    return {r[0]: r[1] for r in db.execute(
        "SELECT job, MAX(finished_at) FROM job_runs WHERE status='success' GROUP BY job")}


def retention_warning(db) -> str | None:
    """A /ready warning when retention has not succeeded in READY_WARN_AFTER_HOURS (or never)."""
    last = last_success(db).get("retention")
    if not last:
        return "retention has never succeeded: expired data is not being deleted yet"
    from .db import parse_iso
    if now() - parse_iso(last) > timedelta(hours=READY_WARN_AFTER_HOURS):
        return f"retention has not succeeded in {READY_WARN_AFTER_HOURS} hours (last success {last})"
    return None
