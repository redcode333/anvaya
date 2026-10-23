"""Provider health: quota exhaustion and daily request counts persisted in the DB; a per-process circuit breaker
(N consecutive failures → skip the provider for a while)."""
import threading
import time
from datetime import datetime, timezone

from flask import current_app

from ..db import get_db, iso, parse_iso
from .client import next_daily_reset

_lock = threading.Lock()
_failures: dict[str, int] = {}
_open_until: dict[str, float] = {}  # time.monotonic() deadline


def _row(name: str):
    return get_db().execute("SELECT * FROM llm_provider_state WHERE provider=?", (name,)).fetchone()


def _upsert(name: str, **cols) -> None:
    db = get_db()
    if not _row(name):
        db.execute("INSERT INTO llm_provider_state(provider, updated_at) VALUES (?,?)", (name, iso()))
    sets = ", ".join(f"{k}=?" for k in cols)
    db.execute(f"UPDATE llm_provider_state SET {sets}, updated_at=? WHERE provider=?", (*cols.values(), iso(), name))
    db.commit()


def _today(name: str) -> str:
    """Quota day label: the date of the provider's next daily reset."""
    return next_daily_reset(name).date().isoformat()


def exhausted_until(name: str) -> datetime | None:
    row = _row(name)
    until = parse_iso(row["exhausted_until"]) if row else None
    return until if until and until > datetime.now(timezone.utc) else None


def mark_exhausted(name: str, until: datetime) -> None:
    _upsert(name, exhausted_until=iso(until), last_result="exhausted")


def count_request(p: dict) -> None:
    """Count one request against the provider's soft daily cap; reaching the cap marks it exhausted until reset."""
    name, day = p["name"], _today(p["name"])
    row = _row(name)
    n = (row["requests_today"] if row and row["day"] == day else 0) + 1
    _upsert(name, day=day, requests_today=n)
    if p["daily_requests"] and n >= p["daily_requests"]:
        mark_exhausted(name, next_daily_reset(name))


def record(name: str, ok: bool) -> None:
    with _lock:
        if ok:
            _failures[name] = 0
            _open_until.pop(name, None)
        else:
            _failures[name] = _failures.get(name, 0) + 1
            if _failures[name] >= current_app.config["LLM_CIRCUIT_FAILURES"]:
                _open_until[name] = time.monotonic() + current_app.config["LLM_CIRCUIT_OPEN_S"]
                _failures[name] = 0
    _upsert(name, last_result="ok" if ok else "error")


def circuit_open(name: str) -> bool:
    with _lock:
        until = _open_until.get(name)
        if until and time.monotonic() >= until:
            _open_until.pop(name, None)  # half-open: the next call decides
            return False
        return bool(until)


def reset_memory() -> None:
    """Tests: forget circuit-breaker state."""
    with _lock:
        _failures.clear()
        _open_until.clear()


def status(p: dict) -> str:
    """configured | ok | error | exhausted | open-circuit (never anything secret)."""
    if exhausted_until(p["name"]):
        return "exhausted"
    if circuit_open(p["name"]):
        return "open-circuit"
    row = _row(p["name"])
    return row["last_result"] if row and row["last_result"] in ("ok", "error") else "configured"
